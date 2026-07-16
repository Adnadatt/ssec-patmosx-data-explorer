# l3_utils.py

import io
import base64
import numpy as np
import netCDF4
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from collections import defaultdict
import tempfile

def fig_to_b64(fig):
    # convert a matplotlib figure to a base64 PNG data url
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return 'data:image/png;base64,' + base64.b64encode(buf.read()).decode()

def filter_files(df, product, platforms, start, end):
    # subset the l3 file index by product, platform list, and date range
    # returns a filtered dataframe sorted by date
    mask = df['key'] == product
    if platforms:
        mask &= df['platform'].isin(platforms)
    if start:
        mask &= df['date'] >= pd.Timestamp(start)
    if end:
        mask &= df['date'] <= pd.Timestamp(end)
    return df[mask].sort_values('date').reset_index(drop=True)

DIM_LON = 0
DIM_LAT = 1
DIM_CTYPE = 2
DIM_ANGLE = 3
DIM_SURF = 4
DIM_NODE = 5
NODE_IDX = {'asc': 0, 'des': 1}
SURFACE_IDX = {'ocean': 0, 'land': 1}
ANGLE_IDX = {'nadir': 0, 'all': 1}
CLOUDY_IDX = [1,2,3]
TOTAL_IDX = [0,1,2,3]

def read_l3_file(path, nodes, surface='all', angle='all', lat_idx=None, lon_idx=None):
    # reads a l3 netCDF file
    # returns (lat, lon, data_2d) - arrays optionally sliced to bbox
    with netCDF4.Dataset(path) as nc:
        lat = nc.variables['latitude'][:]
        lon = nc.variables['longitude'][:]
        raw = nc.variables['counts_all'][:] # product (eg cloud_fraction)

    # select node(s) along last axis
    node_indices = [NODE_IDX[n] for n in nodes]
    raw = raw[..., node_indices].sum(axis=-1) # -> (lon, lat, ctype, angle, surf)

    #select surface type
    if surface == 'ocean':
        raw = raw[..., [SURFACE_IDX['ocean']]].sum(axis=-1)
    elif surface == 'land':
        raw = raw[..., [SURFACE_IDX['land']]].sum(axis=-1)
    else:
        raw = raw.sum(axis=-1)

    # select viewing angle
    if angle == 'nadir':
        raw = raw[..., [ANGLE_IDX['nadir']]].sum(axis=-1)
    else:
        raw = raw.sum(axis=-1)

    total = raw[..., TOTAL_IDX].sum(axis=-1).astype(float)
    cloudy = raw[..., CLOUDY_IDX].sum(axis=-1).astype(float)
    with np.errstate(invalid='ignore', divide='ignore'):
        cf = np.where(total > 0, cloudy / total, np.nan)
    cf = np.ma.masked_invalid(cf)

    # transpose to (lat,lon) for pcolormesh
    cf = cf.T
    lat_out = lat
    lon_out = lon

    if lat_idx is not None:
        lat = lat[lat_idx]
        cf = cf[lat_idx]
    if lon_idx is not None:
        lon = lon[lon_idx]
        cf = cf[:, lon_idx]
    return lat, lon, cf


def bbox_indices(path, w, e, s, n):
    # get lat/lon index arrays for a bounding box from the first file
    with netCDF4.Dataset(path) as nc:
        lat = nc.variables['latitude'][:]
        lon = nc.variables['longitude'][:]
    lat_idx = np.where((lat >= s) & (lat <= n))[0]
    lon_idx = np.where((lon >= w) & (lon <= e))[0]
    return lat_idx, lon_idx

def compute_meanmap(subset, product, bbox, nodes, surface='all', angle='all'):
    # returns (lat,lon,meanmap), no plotting, just data
    w,e,s,n = bbox
    lat_idx, lon_idx = bbox_indices(subset['path'].iloc[0], w,e,s,n)

    accumulator = None
    count = 0
    for _, row in subset.iterrows():
        lat,lon,v = read_l3_file(row['path'], nodes, surface, angle, lat_idx, lon_idx)
        if accumulator is None:
            accumulator = np.zeros(v.shape)
        accumulator += v.filled(0)
        count += (~np.ma.getmaskarray(v)).astype(int)

    meanmap = np.ma.masked_where(count == 0, accumulator / np.maximum(count,1))
    return lat,lon,meanmap

FEATURE_MAP = {
    "coasts": cfeature.COASTLINE,
    "countries": cfeature.BORDERS,
    "states": cfeature.STATES,
}

def render_meanmap(lat, lon, meanmap, subset, product, bbox, cmap="viridis", min=0, max=1, features=None):
    import math

    fig = plt.figure(figsize=(10,4.5))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([bbox[0], bbox[1], bbox[2], bbox[3]], crs=ccrs.PlateCarree())
    im = ax.pcolormesh(lon, lat, meanmap, vmin=min, vmax=max, transform=ccrs.PlateCarree(), cmap=cmap)
    
    if features is None:
        features = []
    for feature in features:
        if feature in FEATURE_MAP:
            ax.add_feature(FEATURE_MAP[feature])

    plt.colorbar(im, ax=ax, label=product.replace('_', ' ').title(), shrink=0.8)

    # cols of platforms on the left
    sat_list = subset['platform'].unique()
    if len(sat_list) <= 8:
        sat_text = "\n".join(sorted(sat_list))
        fig.text(0.02,0.5,sat_text,ha='left',va='center',fontsize=11)
        plt.subplots_adjust(left=0.1)
    if len(sat_list) > 8:
        ncol = 2
        nrows = math.ceil(len(sat_list)/ncol)
        cols = []
        for i in range(ncol):
            col = sat_list[i*nrows:(i+1)*nrows]
            cols.append(col)
        lines = []
        for r in range(nrows):
            left = cols[0][r] if r < len(cols[0]) else ""
            right = cols[1][r] if r < len(cols[1]) else ""
            lines.append(f"{left:<9} {right}")
        sat_text = "\n".join(lines)
        fig.text(0.02,0.5,sat_text,family='monospace',fontsize=11,va='center')
        plt.subplots_adjust(left=0.19)

    date_range = f"{subset['date'].min().strftime('%Y-%m')} - {subset['date'].max().strftime('%Y-%m')}"
    ax.set_title(f"Mean {product.replace('_', ' ').title()}\n{date_range}")
    return fig_to_b64(fig)

def plot_meanmap(subset, product, bbox, nodes, surface='all', angle='all', cmap="viridis", min=0, max=1, features=None):
    lat, lon, meanmap = compute_meanmap(subset,product,bbox,nodes,surface,angle)
    img = render_meanmap(lat,lon,meanmap,subset,product,bbox,cmap,min,max,features)
    return (img, lat.tolist(), lon.tolist(), meanmap.filled(np.nan).tolist())

def build_meanmap_nc(cached):
    lat = cached['lat']
    lon = cached['lon']
    meanmap = cached['meanmap']
    product = cached['product']
    subset = cached['subset']

    tmp = tempfile.NamedTemporaryFile(suffix='.nc', delete=False)
    tmp.close()

    nc = netCDF4.Dataset(tmp.name, 'w')
    nc.title = f'PATMOS-x mean {product}'
    nc.platforms   = ', '.join(sorted(subset['platform'].unique()))
    nc.date_start  = str(subset['date'].min().date())
    nc.date_end    = str(subset['date'].max().date())
    nc.source      = 'SSEC PATMOS-x Data Explorer'

    nc.createDimension('lat', len(lat))
    nc.createDimension('lon', len(lon))

    v_lat = nc.createVariable('lat', 'f4', ('lat',))
    v_lat.units = 'degrees_north'
    v_lat.long_name = 'Latitude'
    v_lat[:] = lat

    v_lon = nc.createVariable('lon', 'f4', ('lon',))
    v_lon.units = 'degrees_east'
    v_lon.long_name = 'Longitude'
    v_lon[:] = lon

    meta = get_product_meta(product)

    v_data = nc.createVariable(product, 'f4', ('lat', 'lon'), fill_value=np.nan)
    v_data.long_name = product.replace('_', ' ').title()
    v_data.description = 'Time-averaged mean over selected date range and platforms'
    v_data[:] = meanmap.filled(np.nan)
    v_data.long_name = meta['long_name']
    v_data.units = meta['units']

    nc.close()
    return tmp.name

def compute_timeseries(subset, product, bbox, nodes, surface='all', angle='all'):
    w,e,s,n = bbox
    lat_idx, lon_idx = bbox_indices(subset['path'].iloc[0], w,e,s,n)

    # per satellite raw timeseries
    ts = {}
    for platform in subset['platform'].unique():
        plat_rows = subset[subset['platform'] == platform]
        dates, values = [], []
        for _, row in plat_rows.iterrows():
            _, _, v = read_l3_file(row['path'], nodes, surface, angle, lat_idx, lon_idx)
            spatial_mean = float(np.ma.mean(v))
            if not np.isnan(spatial_mean):
                dates.append(row['date'])
                values.append(spatial_mean)
        if dates:
            ts[platform] = {'dates':dates, 'values':values}

    # All_Satellites mean, avg across platforms per date

    return ts;


LINE_COLOR = '#1a1a1a'  # dark neutral — overall trend line

SATELLITE_COLORS = [
    '#003a7d',  # deep blue
    '#008dff',  # bright blue
    '#00c2c7',  # teal
    '#4ecb8d',  # green
    '#a0d911',  # lime
    '#f9e858',  # yellow
    '#ff9d3a',  # orange
    '#d83034',  # red
    '#ff73b6',  # pink
    '#c701ff',  # magenta/purple
    '#7c4dff',  # violet
    '#5c6bc0',  # indigo
    '#8d6e63',  # brown
    '#78909c',  # blue-grey
    '#00838f',  # dark teal
    '#c2185b',  # dark pink/rose
]

def render_timeseries(ts_data, product, active_platforms=None):
    all_platforms = list(ts_data.keys())
    if active_platforms is None:
        active_platforms = all_platforms
    
    # assign color per satellite chosen
    satellite_colors = {
        s: SATELLITE_COLORS[i % len(SATELLITE_COLORS)]
        for i, s in enumerate(all_platforms)
    }

    # COLLECT ACTIVE DATA ────────────────────────────────────
    active_dates_flat, active_values_flat = [], []
    for plat in active_platforms:
        if plat in ts_data:
            active_dates_flat.extend(ts_data[plat]['dates'])
            active_values_flat.extend(ts_data[plat]['values'])
    
    if not active_dates_flat:
        return None, None, satellite_colors
    
    overall_mean = np.mean(active_values_flat)

    # monthly climatology (12 vals)
    month_bucket = defaultdict(list)
    for plat in active_platforms:
        if plat not in ts_data:
            continue
        for date, val in zip(ts_data[plat]['dates'], ts_data[plat]['values']):
            month_bucket[date.month].append(val)
    clim = {m: np.mean(v) for m, v in month_bucket.items()}

    # overall mean line
    date_bucket = defaultdict(list)
    for plat in active_platforms:
        if plat not in ts_data:
            continue
        for date, val in zip(ts_data[plat]['dates'], ts_data[plat]['values']):
            date_bucket[date].append(val)
    mean_dates = sorted(date_bucket.keys())
    mean_vals = [np.mean(date_bucket[d]) for d in mean_dates]
    mean_dates_dt = pd.to_datetime(mean_dates)

    # trendline
    sorted_pairs = sorted(zip(active_dates_flat, active_values_flat))
    trend_dates = pd.to_datetime([p[0] for p in sorted_pairs])
    trend_values = [p[1] for p in sorted_pairs]
    x_num = (trend_dates - trend_dates[0]).days.values.astype(float)
    coeffs = np.polyfit(x_num, trend_values, 1)
    trend = np.polyval(coeffs, x_num)
    slope_per_decade = coeffs[0] * 365.25 * 10

    ylabel = product.replace('_', ' ').title()

    def make_fig():
        return plt.subplots(figsize=(10,3.2))

    def platform_scatterplots(ax):
        for plat in active_platforms:
            if plat not in ts_data:
                continue
            color = satellite_colors[plat]
            ax.scatter(pd.to_datetime(ts_data[plat]['dates']),
            ts_data[plat]['values'],
            color=color, s=10, alpha=0.55, label=plat, zorder=3)

    # PLOT 1: MEAN TIMESERIES ────────────────────────────────
    fig1, ax1 = make_fig()
    platform_scatterplots(ax1)
    ax1.plot(mean_dates_dt, mean_vals, color='#1a1a1a', linewidth=1.2,
             label='Overall mean', zorder=4)
    ax1.plot(trend_dates, trend, color='#8e1b11', linewidth=1.5, linestyle='--',
             label=f'Trend ({slope_per_decade:+.4f}/decade)', zorder=5)
    ax1.set_ylabel(ylabel)
    ax1.set_title(f"Regional mean {ylabel}")
    ax1.legend(fontsize=8, ncol=min(5, len(active_platforms) + 2),
               loc='upper left', framealpha=0.7)
    ax1.grid(alpha=0.2)
    fig1.tight_layout()
    img1 = fig_to_b64(fig1)

    # PLOT 2: ANOMALY TIMESERIES, OVERALL ────────────────────
    fig2, ax2 = make_fig()
    for plat in active_platforms:
        if plat not in ts_data:
            continue
        color = satellite_colors[plat]
        anom = [v - overall_mean for v in ts_data[plat]['values']]
        ax2.scatter(pd.to_datetime(ts_data[plat]['dates']), anom, 
            color=color, s=10, alpha=0.55, label=plat, zorder=3)
    ax2.axhline(0, color='#1a1a1a', linewidth=0.8, linestyle='--')
    ax2.set_ylabel('Anomaly')
    ax2.set_title(f"Anomaly vs. overall mean  (mean = {overall_mean:.3f})")
    ax2.legend(fontsize=8, ncol=min(5, len(active_platforms)),
               loc='upper left', framealpha=0.7)
    ax2.grid(alpha=0.2)
    fig2.tight_layout()
    img2 = fig_to_b64(fig2)

    # PLOT 3: ANOMALY TIMESERIES, MONTHLY ────────────────────
    fig3, ax3 = make_fig()
    for plat in active_platforms:
        if plat not in ts_data:
            continue
        color = satellite_colors[plat]
        anom = [v - clim.get(d.month, overall_mean) for d,v in zip(ts_data[plat]['dates'], ts_data[plat]['values'])]
        ax3.scatter(pd.to_datetime(ts_data[plat]['dates']), anom, 
            color=color, s=10, alpha=0.55, label=plat, zorder=3)
    ax3.axhline(0, color='#1a1a1a', linewidth=0.8, linestyle='--')
    ax3.set_ylabel('Anomaly')
    ax3.set_title(f"Anomaly vs. monthly mean")
    ax3.legend(fontsize=8, ncol=min(5, len(active_platforms)),
               loc='upper left', framealpha=0.7)
    ax3.grid(alpha=0.2)
    fig3.tight_layout()
    img3 = fig_to_b64(fig3)

    return img1, img2, img3, satellite_colors

def plot_timeseries(subset, product, bbox, nodes, surface='all', angle='all'):
    
    dates = pd.to_datetime(dates)
    means = np.array(means)

    fig, ax = plt.subplots(figsize=(10,3.2))
    ax.plot(dates, means)
    ax.set_ylabel(product.replace('_', ' ').title())
    # ax.set_xlabel('')
    # ax.grid(alpha=0.3)
    platforms = ', '.join(sorted(subset['platform'].unique()))
    ax.set_title(f"Regional mean {product.replace('_', ' ').title()}\n{platforms}")

    fig.tight_layout()
    return fig_to_b64(fig)

def build_timeseries_nc(cached):
    """Write per-platform timeseries to a temp NetCDF file. Returns the file path."""
    ts_data = cached['ts_data']
    product = cached['product']
    meta = get_product_meta(product)

    tmp = tempfile.NamedTemporaryFile(suffix='.nc', delete=False)
    tmp.close()

    nc = netCDF4.Dataset(tmp.name, 'w')
    nc.title   = f'PATMOS-x {meta["long_name"]} timeseries'
    nc.source  = 'SSEC PATMOS-x Data Explorer'

    # find the union of all dates across platforms, sorted
    all_dates = sorted({d for plat in ts_data for d in ts_data[plat]['dates']})
    # store dates as days since 1970-01-01 (CF convention)
    epoch = pd.Timestamp('1970-01-01')
    date_nums = [(pd.Timestamp(d) - epoch).days for d in all_dates]
    # one variable per platform, filled with NaN where that platform has no data
    date_index = {d: i for i, d in enumerate(all_dates)}

    nc.createDimension('time', len(all_dates))

    v_time = nc.createVariable('time', 'i4', ('time',))
    v_time.units    = 'days since 1970-01-01'
    v_time.calendar = 'standard'
    v_time.long_name = 'Time'
    v_time[:] = date_nums


    # build per platform arrays, keep them to compute all-sat mean
    platform_arrays = {}
    for plat, data in ts_data.items():
        arr = np.full(len(all_dates), np.nan, dtype=np.float32)
        for d, v in zip(data['dates'], data['values']):
            arr[date_index[d]] = v
        platform_arrays[plat] = arr

        varname = plat.replace('-', '_')   # netCDF variable names can't contain hyphens
        v = nc.createVariable(varname, 'f4', ('time',), fill_value=np.nan)
        v.long_name  = f'{plat} {meta["long_name"]} regional mean'
        v.platform   = plat
        v.units      = meta['units']   # cloud fraction is dimensionless
        v[:] = arr

    # compute All_Satellites mean (avg across platforms at each date)
    stacked = np.stack(list(platform_arrays.values()), axis=0) # (n_platforms, n_times)
    all_mean = np.nanmean(stacked, axis=0).astype(np.float32)
    all_mean[np.all(np.isnan(stacked), axis=0)] = np.nan # keep NaN where ALL platforms are missing

    v_all = nc.createVariable('All_Satellites', 'f4', ('time',), fill_value=np.nan)
    v_all.long_name = f'All satellite mean {meta["long_name"]}'
    v_all.units = meta['units']
    v_all[:] = all_mean

    nc.close()
    return tmp.name

PRODUCT_META = {
    'cloud_fraction':   {'units': '1',   'long_name': 'Cloud Fraction'},
    'cld_press_acha':   {'units': 'hPa', 'long_name': 'Cloud Top Pressure'},
    'cld_temp_acha':    {'units': 'K',   'long_name': 'Cloud Top Temperature'},
    'cld_opd_dcomp':    {'units': '1',   'long_name': 'Cloud Optical Depth'},
    'cld_reff_dcomp':   {'units': 'um',  'long_name': 'Cloud Effective Radius'},
}

def get_product_meta(product):
    return PRODUCT_META.get(product, {'units':'unknown', 'long_name':product.replace('_',' ').title()})