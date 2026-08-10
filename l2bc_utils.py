# l2bc_utils.py
# file scanning, data reading, statistics, climate calcs

import netCDF4
import numpy as np
from tqdm import tqdm
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
import multiprocessing as mp
import socket
import io
import time
import threading
from queue import Queue, Empty
import random
import warnings
from collections import defaultdict
import xarray as xr
import subprocess
import os

ROOT = Path('[path to L2BC files]')


def scan_files(root=ROOT):
    df = []
    with tqdm(root.rglob('*.nc')) as bar:
        for f in bar:
            # patmosx_v06r00_NOAA-09_asc_d19880428_c20210810.cloud_probability.nc
            stem, key, _ = f.name.split('.')
            _,_,platform,node,date,created = stem.split('_')
            date = datetime.strptime(date, 'd%Y%m%d')
            created = datetime.strptime(created, 'c%Y%m%d')
            df.append({'platform': platform, 'node': node, 'date': date, 'key': key, 'path': f, 'created': created})
    df = pd.DataFrame(df)
    return df


def pivot_files(df):
    df.sort_values('created', inplace=True)
    df = df.drop_duplicates(subset=['platform','node','date','key'], keep='last')
    files = df.pivot(index=['platform','node','date'], columns='key', values='path').sort_index(level='date')
    return files


def get_files(root=ROOT):
    df = scan_files(root=root)
    files = pivot_files(df)
    return files


def _read_worker(q, out_q):
    while True:
        try:
            args = q.get(timeout=1)
            key, f = args
            nc = netCDF4.Dataset(f)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = nc.variables[key][0]
            out_q.put(data)
            nc.close()
        except Empty:
            return

def clear_queue(q):
    while True:
        try:
            q.get_nowait()
        except Empty:
            return


def mask_any(*args):
    mask = np.zeros(args[0].shape, dtype=bool)
    for a in args:
        mask |= np.ma.getmaskarray(a)
    return mask


def iter_nc_var(files, *args, progress=True, maskany=False):
    args = list(args)
    file_subset = files[args].dropna()
    with tqdm(file_subset.iterrows(), disable=not progress, total=len(file_subset), smoothing=0) as bar:
        for i,((platform, node, date), paths) in enumerate(bar):
            key = platform, date, node
            data = []
            if i+1 < len(file_subset):
                next_row = file_subset.iloc[i+1]
                for k in args:
                    subprocess.Popen(['cat', str(next_row[k])], stdout=subprocess.DEVNULL)
            for k in args:
                nc = netCDF4.Dataset(paths[k])
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    data.append(nc.variables[k][0])
                nc.close()
                with open(paths[k]) as fp:
                    os.posix_fadvise(fp.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)

            if maskany:
                mask = mask_any(*data)
                for d in data:
                    d[mask] = np.ma.masked
                mask = ~mask
                data.append(mask)
            yield key, data



def fast_iter_nc_var(files, *args, thread=True):
    args = list(args)
    file_subset = files[args].dropna()
    task_queue = Queue()
    out_queue = Queue()
    thread = threading.Thread(target=_read_worker, args=(task_queue, out_queue))
    tasks = []
    for (platform, node, date), paths in file_subset.iterrows():
        key = platform, date, node
        tasks.append((key, args))
        for k in args:
            task_queue.put((k, paths[k]))
    thread.start()

    try:
        for key,task in tasks:
            results = [out_queue.get() for _ in task]
            yield key, results
        thread.join()
    except:
        clear_queue(task_queue)
        thread.join()
        raise


def read_file(args, from_phase=False):
    """
    read a single netcdf file
    return table of features (x,y,frac_year,year,local_hour,cloud_probability)
    """
    (platform, node, date), row = args
    if from_phase:
        nc = netCDF4.Dataset(row['ice_cloud_probability'])
        ice_v = nc.variables['ice_cloud_probability'][0]
        nc.close()
        nc = netCDF4.Dataset(row['water_cloud_probability'])
        water_v = nc.variables['water_cloud_probability'][0]
        nc.close()
        v = ice_v + water_v
    else:
        nc = netCDF4.Dataset(row['cloud_probability'])
        v = nc.variables['cloud_probability'][0]
        nc.close()
    nc = netCDF4.Dataset(row['scan_line_time'])
    slt = nc.variables['scan_line_time'][0]
    lon = nc.variables['longitude'][:]
    nc.close()
    y,x = np.meshgrid(np.arange(v.shape[0]), np.arange(v.shape[1]), indexing='ij', copy=True)
    frac_year = (date - datetime(date.year,1,1)).total_seconds() / (365.25*24*60*60)
    year = date.year
    utc_offset = lon / 360 * 24
    local_hour = (slt + utc_offset) % 24
    mask = ~(np.ma.getmaskarray(v) | np.isnan(v) | np.ma.getmaskarray(slt) | np.isnan(slt)).ravel()
    features = {}
    features['x'] = x.ravel()[mask]
    features['y'] = y.ravel()[mask]
    features['frac_year'] = np.full(x.size, frac_year, dtype=np.float32)[mask]
    features['year'] = np.full(x.size, year, dtype=np.float32)[mask]
    features['year'] += frac_year
    features['local_hour'] = local_hour.ravel()[mask].data
    features['cloud_probability'] = v.ravel()[mask].data
    return features


def send_tv(batch):
    """
    send a batch of files to the server
    """
    HOST = '127.0.0.1'
    PORT = 50007
    payload = io.BytesIO()
    #np.savez_compressed(payload, **batch)
    np.savez(payload, **batch)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        while True:
            try:
                s.connect((HOST, PORT))
                s.sendall(payload.getbuffer())
                return
            except ConnectionRefusedError:
                time.sleep(.1)
            except ConnectionResetError:
                time.sleep(random.random()*.1)


def get_features_tv():
    HOST = 'localhost'
    PORT = 50007
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        while True:
            payload = io.BytesIO()
            conn, addr = s.accept()
            with conn:
                while True:
                    data = conn.recv(2**16)
                    if not data:
                        break
                    payload.write(data)
            payload.seek(0)
            npz = np.load(payload)
            features = {k: npz[k] for k in npz.files}
            if not features:
                return
            yield features


def read_and_send(args):
    """
    read a single file and send it to the server
    """
    features = read_file(args)
    send_tv(features)


def compute_stats_index(batch, coords):
    hour_coords = coords['hour']
    season_coords = coords['season']
    year_coords = coords['year']
    
    hour_season_shape = (len(hour_coords), len(season_coords), 180, 360)
    year_anomaly_shape = (len(year_coords), 180, 360)

    hour_idx = np.digitize(batch['local_hour'], hour_coords, right=True) - 1
    season_idx = np.digitize(batch['frac_year'], season_coords, right=True) - 1
    hour_season_idx = np.ravel_multi_index((hour_idx, season_idx, batch['y'], batch['x']), hour_season_shape, mode='clip')
    year_idx = np.digitize(batch['year'], year_coords, right=True).clip(1, len(year_coords)) - 1
    year_anomaly_idx = np.ravel_multi_index((year_idx, batch['y'], batch['x']), year_anomaly_shape, mode='clip')
    return hour_season_idx, year_anomaly_idx


def update_stats(stats, hour_season_idx, year_anomaly_idx, v, mask):
    old_shapes = {k: stats[k].shape for k in stats}
    stats['hour_season_sum'] = stats['hour_season_sum'].ravel().at[hour_season_idx].add(v)
    stats['hour_season_count'] = stats['hour_season_count'].ravel().at[hour_season_idx].add(mask)
    stats['year_anomaly_sum'] = stats['year_anomaly_sum'].ravel().at[year_anomaly_idx].add(v)
    stats['year_anomaly_count'] = stats['year_anomaly_count'].ravel().at[year_anomaly_idx].add(mask)
    for k in stats:
        stats[k] = stats[k].reshape(old_shapes[k])
    return stats


def init_stats(coords):

    hour_coords = coords['hour']
    season_coords = coords['season']
    year_coords = coords['year']

    zeros = np.zeros
    stats = {}
    stats['hour_season_sum'] = zeros((len(hour_coords), len(season_coords), 180, 360), dtype=np.float32)
    stats['hour_season_count'] = zeros((len(hour_coords), len(season_coords), 180, 360), dtype=np.int32)
    stats['year_anomaly_sum'] = zeros((len(year_coords),180,360), dtype=np.float32)
    stats['year_anomaly_count'] = zeros((len(year_coords),180,360), dtype=np.int32)
    return stats


def filter_szas(v, sza, slt, ANGLE_CUTOFF=30):
    mask = sza > ANGLE_CUTOFF
    v[mask] = np.ma.masked
    return v, slt


def compute_hour_season_stats(files, *required_vars, transform=filter_szas):
    nc = netCDF4.Dataset(files.iloc[0].dropna().values[0])
    lon = nc.variables['longitude'][:]
    utc_offset = lon / 360 * 24
    nc.close()
    season_hour_sum = np.zeros((12,24,180,360), dtype=np.float64)
    season_hour_count = np.zeros((12,24,180,360), dtype=np.int32)
    i,j = np.meshgrid(np.arange(180), np.arange(360), indexing='ij')

    files = files[list(required_vars)].dropna()
    with tqdm(fast_iter_nc_var(files, *required_vars), total=len(files)) as bar:
        for (platform, date, node), data in bar:
            v, slt = transform(*data)
            idx = compute_season_hour_index(date, slt, utc_offset, i, j)
            season_hour_sum.ravel()[idx] += v.filled(0).ravel()
            season_hour_count.ravel()[idx] += 1-np.ma.getmaskarray(v.ravel())
    return season_hour_sum, season_hour_count


def compute_season_hour_index(date, slt, utc_offset, i, j):
    local_hour = (slt + utc_offset)
    hour_idx = np.floor(local_hour).astype(np.int32) % 24
    season_idx = np.full(hour_idx.shape, date.month-1, dtype=np.int32)
    idx = np.ravel_multi_index((season_idx.ravel(), hour_idx.ravel(), i.ravel(), j.ravel()), (12,24,180,360))
    return idx


def frac_month(date):
    since_month_begin = date - date.replace(day=1)
    month_duration = (date.replace(day=1)+timedelta(days=32)).replace(day=1) - date.replace(day=1)
    return since_month_begin.total_seconds() / month_duration.total_seconds()

def interp_month_coords(date):
    month_alpha = frac_month(date)
    # the proper location of the month coordinate is the middle of the month
    # so if month alpha is less than .5, we are interpolating between the previous month and the current month
    # and the month alpha should be 1 if it was .5, 0.5 if it was 0
    # if month alpha is greater than .5, we are interpolating between the current month and the next month
    # the month alpha should be 0 if it was .5, 0.5 if it was 1
    if month_alpha > .5:
        month0 = date.month-1
        month1 = date.month % 12
        month_alpha -= .5
    else:
        month0 = (date.month-2) % 12
        month1 = date.month-1
        month_alpha = month_alpha - .5 + 1
        
    return month0, month1, month_alpha

def interp_season_hour_offset(season_hour_offset, local_hour, date):
    i,j = np.meshgrid(np.arange(180), np.arange(360), indexing='ij')
    hour_idx = np.floor(local_hour).astype(np.int32) % 24

    month0, month1, month_alpha = interp_month_coords(date)

    hour_alpha = local_hour.ravel() % 1

    hour_offset = (1-month_alpha)*season_hour_offset[month0] + month_alpha*season_hour_offset[month1]
    
    idx0 = np.ravel_multi_index((hour_idx.ravel(), i.ravel(), j.ravel()), hour_offset.shape)
    idx1 = np.ravel_multi_index((hour_idx.ravel()+1, i.ravel(), j.ravel()), hour_offset.shape, mode='wrap')

    offset = (1-hour_alpha)*hour_offset.ravel()[idx0] + hour_alpha*hour_offset.ravel()[idx1]
    return offset.reshape(local_hour.shape)



def correct_hour_season(files, season_hour_offset, *required_vars, floor_date=None, transform=filter_szas):
    def init_stats():
        return {'sum':np.zeros((180,360), dtype=np.float64), 'count':np.zeros((180,360), dtype=np.int32)}
    stats = defaultdict(init_stats)

    if floor_date is None:
        floor_date = lambda x: x.replace(day=1)

    nc = netCDF4.Dataset(files.iloc[0].iloc[0])
    lon = nc.variables['longitude'][:]
    utc_offset = lon / 360 * 24
    nc.close()
    files = files[list(required_vars)].dropna()
    with tqdm(fast_iter_nc_var(files, *required_vars), total=len(files)) as bar:
        for (platform, date, node), data in bar:
            key = platform, floor_date(date), node
            v, slt = transform(*data)
            
            local_hour = (slt + utc_offset) - .5
            offset = interp_season_hour_offset(season_hour_offset, local_hour, date)
            
            v_full = (v - offset.reshape(v.shape))
            
            stats[key]['sum'] += v_full.filled(0)
            stats[key]['count'] += (1-np.ma.getmaskarray(v_full))
            
    stats = dict(stats.items())
    return stats

def get_mean_from_stats(stat, lat, lon, min_count=1):
    mean = []
    platforms = []
    start_times = []
    nodes = []
    with tqdm(stat) as bar:
        for k in bar:
            (platform, start_time, node) = k
            mean.append((stat[k]['sum'] / np.ma.masked_less(stat[k]['count'], min_count)).astype(np.float32))
            platforms.append(platform)
            start_times.append(start_time)
            nodes.append(node)
    mean = np.ma.stack(mean)

    mean = xr.DataArray(mean, dims=['group','lat','lon'],
                        coords={
                            'platform':(['group'], platforms),
                            'start_time':(['group'], start_times),
                            'node':(['group'], nodes),
                            'lat':(['lat'], lat),
                            'lon':(['lon'], lon)
                        }
                        )
    mean = mean.ffill('group').bfill('group')
    return mean


PLATFORM_COLORS = {'noaa-06': 'C0',
 'noaa-07': 'C1',
 'noaa-08': 'C2',
 'noaa-09': 'C3',
 'noaa-10': 'C4',
 'noaa-11': 'C5',
 'noaa-12': 'C6',
 'noaa-14': 'C7',
 'noaa-15': 'C8',
 'noaa-16': 'C9',
 'noaa-17': 'C10',
 'noaa-18': 'C11',
 'metop-a': 'C12',
 'noaa-19': 'C13',
 'metop-b': 'C14',
 'metop-c': 'C15',
}

def plot_mean(mean):
    import matplotlib.pyplot as plt
    global_mean = mean.mean(dim=['lat','lon']).set_index(group=['platform','start_time','node']).to_pandas()
    for (platform,node), s in global_mean.groupby(['platform','node']):
        s = s.droplevel(['platform','node'])
        s.plot(label=f'{platform} {node}', color=PLATFORM_COLORS[platform.lower()])
    global_mean.groupby('start_time').mean().plot(label='mean', color='k')
    plt.xlabel('')
    plt.ylabel('Lower Cloud Coverage Anomaly (ACHA)')
    plt.grid()
