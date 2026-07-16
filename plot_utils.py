# plot_utils.py
# raw netCDF into PNG

import tarfile
import io
import numpy as np
import PIL.Image
import matplotlib.pyplot as plt
import netCDF4

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
 'snpp': 'C0',
 'snpp-00': 'C0',
 'noaa-20': 'C1',
 'noaa-21': 'C2',
 'tiros-n': 'C8'
}


def plot_image(v, cmap, vmin, vmax, scale=1):
    cmap = plt.get_cmap(cmap)
    v_scaled = (v - vmin) / (vmax - vmin) # normalize values to [0,1]
    np.clip(v_scaled, 0, 1, out=v_scaled) # cut out out of range vals
    v_rgba = cmap(v_scaled) # apply colormap to v_scaled percentages
    rgba8 = (v_rgba * 255).astype(np.uint8)
    img = PIL.Image.fromarray(rgba8, mode='RGBA')
    if scale != 1:
        img = scale_image(img, scale)
    return img


def scale_image(img, scale: int):
    arr = np.array(img)
    h, w, c = arr.shape
    # tile each pixel into a scale×scale block using numpy reshape/tile trick
    # avoids slow PIL resize and preserves sharp pixel boundaries
    arr = np.tile(arr.reshape(h, 1, w, 1, c), (1, scale, 1, scale, 1)).reshape(h * scale, w * scale, c)
    return PIL.Image.fromarray(arr, mode=img.mode)


def plot_l2b_var(nc, k, s=slice(0,None,10), scale=1):
    if k.startswith('temp_stddev3x3'):
        vmin = 0
        vmax = 5
        cmap = 'magma'
    elif k.startswith('temp_'):
        vmin = 180
        vmax = 330
        cmap = 'turbo'
    elif k.startswith('refl_'):
        vmin = 0
        vmax = 100
        cmap = 'binary_r'
    elif k.endswith('cloud_probability'):
        vmin = 0
        vmax = 1
        cmap = 'RdBu_r'
    elif k.startswith('cld_opd_uncer'):
        vmin = 0
        vmax = 5
        cmap = 'magma'
    elif k.startswith('cld_opd_dcomp'):
        vmin = 0
        vmax = 15
        cmap = 'viridis'
        mask = (nc[k.replace('cld_opd_dcomp', 'dcomp_quality')][:].squeeze()[s,s][::-1] & 1) != 1
        v = nc[k][:].squeeze()[s,s][::-1]
        v[mask.filled(True)] = np.ma.masked
        return plot_image(v, cmap, vmin, vmax, scale=scale)
    elif k.startswith('cld_reff_dcomp'):
        vmin = 0
        vmax = 100
        cmap = 'viridis'
        mask = (nc[k.replace('cld_reff_dcomp', 'dcomp_quality')][:].squeeze()[s,s][::-1] & 1) != 1
        v = nc[k][:].squeeze()[s,s][::-1]
        v[mask.filled(True)] = np.ma.masked
        return plot_image(v, cmap, vmin, vmax, scale=scale)
    elif k == 'cld_temp_top_uncer_acha':
        vmin = 0
        vmax = 30
        cmap = 'magma'
    elif k.startswith('cld_reff_uncer_dcomp'):
        vmin = 0
        vmax = 2
        cmap = 'magma'
    elif k.startswith('cld_temp'):
        vmin = 180
        vmax = 300
        cmap = 'turbo'
    elif 'flux' in k:
        vmin = 0
        if '_sw_' in k or k == 'solar_flux':
            vmax = 900
        else:
            vmax = 500
        cmap = 'plasma'
    elif k == 'cld_emis_acha':
        vmin = 0
        vmax = 1
        cmap = 'viridis'
    elif k == 'cld_emis_uncer_acha':
        vmin = 0
        vmax = 0.5
        cmap = 'magma'
    elif k == 'cld_height_top_acha':
        vmin = 0
        vmax = 12000
        cmap = 'nipy_spectral'
    elif k == 'cld_press_top_acha':
        vmin = 100
        vmax = 1000
        cmap = 'nipy_spectral_r'
    elif k == 'cld_beta_acha':
        vmin = 1
        vmax = 3
        cmap = 'viridis'
    elif k.endswith('_azimuth_angle'):
        vmin = -180
        vmax = 180
        cmap = 'hsv'
    elif k.endswith('_counts'):
        vmin = 0
        vmax = 1000
        cmap = 'turbo'
    elif k == 'acha_quality':
        # processed valid_Tc_retrieval valid_ec_retrieval valid_beta_retrieval degraded_Tc_retrieval degraded_ec_retrieval degraded_beta_retrieval
        v = nc[k][:].squeeze()[s,s][::-1]
        return plot_image(v, 'viridis', 0.0, 3.0, scale=scale)
    elif k == 'acha_info':
        # Cloud_Height_Attempted  Bias_Correction_Employed  Ice_Cloud_Retrieval  Local_Radiative_Center_Processing_Used  Multi_Layer_Retrieval  Lower_Cloud_Interpolation_Used  Boundary_Layer_Inversion_Assumed
        vmin = 0
        vmax = 42
        cmap = 'tab20'
    elif k.startswith('dcomp_quality'):
        v = nc[k][:].squeeze()[s,s][::-1].data & 0b111
        return plot_image(v, 'viridis', 0, 7, scale=scale)
    elif k.startswith('dcomp_info'):
        vmin = 0
        vmax = 255
        cmap = 'tab20'
    elif k == 'sensor_zenith_angle':
        vmin = 0
        vmax = 60
        cmap = 'viridis'
    elif k == 'solar_zenith_angle':
        vmin = 90-30
        vmax = 90+30
        cmap = 'coolwarm_r'
    elif k == 'snow_class':
        vmin =.5
        vmax = 10.5
        cmap = 'tab10'
    elif k == 'bayes_mask_sfc_type':
        vmin = 0.5
        vmax = 10.5
        cmap = 'tab10'
    elif k == 'land_class':
        vmin = -0.5
        vmax = 9.5
        cmap = 'tab10'
    elif k == 'cloud_type':
        vmin = -0.5
        vmax = 9.5
        cmap = 'tab10'
    elif k == 'datetime':
        vmin = 0
        vmax = 24*60*60
        v = nc[k][:].squeeze()[s,s][::-1] % (24*60*60)
        return plot_image(v, 'hsv', vmin, vmax, scale=scale)

    elif k.startswith('dtemp_'):
        vmin = -10
        vmax = 10
        cmap = 'RdBu_r'
        ch = k.split('_ch')[1]
        v1 = nc[f'temp_ch{ch}'][:].squeeze()[s,s][::-1]
        v2 = nc[f'temp_sounder_ch{ch}'][:].squeeze()[s,s][::-1]
        v = v2 - v1
        return plot_image(v, cmap, vmin, vmax, scale=scale)

    elif k == 'bad_pixel_mask':
        v = nc[k][:].squeeze()[s,s][::-1]
        v = np.ma.masked_where(v == 0, v)
        return plot_image(v, 'viridis', 0.0, 1.0, scale=scale)

    elif k == 'surface_temperature_nwp':
        vmin = 200
        vmax = 320
        cmap = 'turbo'
        return plot_image(nc[k][:].squeeze()[s,s][::-1], cmap, vmin, vmax, scale=scale)

    else:
        raise ValueError(f'Unknown variable for plotting: {k}')

    v = nc[k][:].squeeze()[s,s][::-1] # read variable, remove size-1 dims, subsample, flip
    return plot_image(v, cmap, vmin, vmax, scale=scale)

def plot_l2b_diff(nc1, nc2, k, s=slice(0,None,10), scale=1):
    v1 = nc1[k][:].squeeze()[s,s][::-1]
    v2 = nc2[k][:].squeeze()[s,s][::-1]
    vdiff = v2 - v1
    if k.startswith('temp_'):
        vmin = -10
        vmax = 10
        cmap = 'RdBu_r'
    elif k.startswith('refl_'):
        vmin = -10
        vmax = 10
        cmap = 'RdBu_r'
    elif k.endswith('cloud_probability'):
        vmin = -0.2
        vmax = 0.2
        cmap = 'RdBu_r'
    elif k == 'cld_temp_top_acha':
        vmin = -10
        vmax = 10
        cmap = 'RdBu_r'
    elif 'flux' in k:
        vmin = -50
        vmax = 50
        cmap = 'RdBu_r'
    elif k == 'surface_temperature_nwp':
        vmin = -10
        vmax = 10
        cmap = 'RdBu_r'
    else:
        raise ValueError(f'Unknown variable for plotting diff: {k}')
    im = plot_image(vdiff, cmap, vmin, vmax, scale=scale)
    return im


def plot_rgb(data):
    mu = np.cos(np.deg2rad(data['solar_zenith_angle'])).clip(0, 1)
    gb = np.ma.asarray(data['refl_ch01']) * mu
    r = np.ma.asarray(data['refl_ch02']) * mu
    rgb8 = np.full((*r.shape, 3), 255, dtype=np.uint8)
    scale = 30
    r8 = (r * (255 / scale)).clip(0, 255).filled(0).astype(np.uint8)
    gb8 = (gb * (255 / scale)).clip(0, 255).filled(0).astype(np.uint8)
    rgb8[..., 0] = r8
    rgb8[..., 1] = gb8
    rgb8[..., 2] = gb8
    return PIL.Image.fromarray(rgb8)


def add_img_to_tar(tar, img, fname):
    fp = io.BytesIO()
    img.save(fp, format='PNG')
    tarinfo = tarfile.TarInfo(name=fname)
    tarinfo.size = fp.tell()
    fp.seek(0)
    tar.addfile(tarinfo, fp)


def multihist(*arrays, bins=20, density=False, range=None, labels=None, colors=None, **kwargs):
    if range is not None:
        min_val, max_val = range
    else:
        min_val = min([np.min(a) for a in arrays])
        max_val = max([np.max(a) for a in arrays])
    if isinstance(bins, int):
        bins = np.linspace(min_val, max_val, bins)
    bin_centers = (bins[1:] + bins[:-1]) / 2
    if labels is not None:
        label_it = iter(labels)
    if colors is not None:
        color_it = iter(colors)
    for a in arrays:
        H, _ = np.histogram(a, bins=bins, density=density)
        if labels is not None:
            label = next(label_it)
        else:
            label = None
        if colors is not None:
            color = next(color_it)
        else:
            color = None
        plt.plot(bin_centers, H, label=label, color=color, **kwargs)
    


def plot_l2bc(f, scale=1):
    k = str(f).split('.')[-2]
    with netCDF4.Dataset(f) as nc:
        return plot_l2b_var(nc, k, s=slice(None), scale=scale)

def plot_l2bc_diff(f1, f2, scale=1):
    k = str(f1).split('.')[-2]
    with netCDF4.Dataset(f1) as nc1, netCDF4.Dataset(f2) as nc2:
        return plot_l2b_diff(nc1, nc2, k, s=slice(None), scale=scale)