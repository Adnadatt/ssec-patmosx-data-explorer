# patmosxDataExplorer.py

import io, base64, asyncio
import pandas as pd
import cartopy.io.img_tiles as cimgt
from sanic import Sanic
from sanic.response import raw, file as sanic_file, json as sanic_json
import warnings
warnings.filterwarnings("ignore", message=".*get_event_loop_policy.*")
import tempfile, os

import plot_utils as pu
import l3_utils
from products_l2bc import PRODUCTS as L2BC_PRODUCTS

app = Sanic("PatmosxDataExplorer")
app.static('/static', './static')

@app.get('/api/borders')
async def borders(request):
    # returns a transparent PNG w/ coastlines & borders, fetched once & cached by browser
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    w = float(request.args.get('w', -180))
    e = float(request.args.get('e', 180))
    s = float(request.args.get('s', -90))
    n = float(request.args.get('n', 90))

    def render():
        fig = plt.figure(figsize=(10,5))
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent([w,e,s,n], crs=ccrs.PlateCarree())
        ax.set_facecolor('none')
        fig.patch.set_alpha(0)
        ax.add_feature(cfeature.COASTLINE)
        ax.add_feature(cfeature.BORDERS)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=110, bbox_inches='tight', transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    
    loop = asyncio.get_event_loop()
    png = await loop.run_in_executor(None, render)
    return raw(png, content_type='image/png',
               headers={'Cache-Control': 'public, max-age=86400'})

@app.before_server_start
async def load_data(app):
    print("Loading l2bc file index...")
    app.ctx.l2bc_files = pd.read_pickle('l2bc_files.pickle')
    app.ctx.l2bc_products = L2BC_PRODUCTS

    print("Loading l3 file index...")
    app.ctx.l3_files = pd.read_pickle('l3_files.pickle')
    app.ctx.meanmap_cache = {}
    app.ctx.timeseries_cache = {}

    print(f"L2BC: {len(app.ctx.l2bc_files)} rows | L3: {len(app.ctx.l3_files)} files")

# serves the html page
@app.route("/")
async def index(request):
    return await sanic_file("index.html")

@app.get("/api/l2bc/products")
async def l2bc_products(request):
    products = request.app.ctx.l2bc_products;
    return sanic_json([
        {'value': k, 'label': v['label'], 'unit': v['unit']}
        for k, v in products.items()
    ])

@app.get("/api/l2bc/platforms")
async def l2bc_platforms(request):
    files = request.app.ctx.l2bc_files
    return sanic_json(sorted(files.index.get_level_values('platform').unique().tolist()))

@app.get("/api/l2bc/dates")
async def l2bc_dates(request):
    files = request.app.ctx.l2bc_files
    platform, node = request.args.get('platform'), request.args.get('node')
    try:
        loc = files.index.get_loc((platform, node))
    except KeyError:
        return sanic_json([])
    dates = files.index[loc].get_level_values('date')
    return sanic_json(sorted({d.strftime('%Y-%m-%d') for d in dates}))

@app.get('/api/l2bc/generate')
async def l2bc_generate(request):
    files,products = request.app.ctx.l2bc_files, request.app.ctx.l2bc_products
    platform = request.args.get('platform')
    node     = request.args.get('node')
    date     = request.args.get('date')
    product  = request.args.get('product')

    if product not in products:
        return sanic_json({'error': f'Unknown product: {product}'}, status=400)
    variable = products[product]['variable']

    try:
        f = files[variable].loc[platform, node, date]
    except KeyError:
        f = None
    if f is None or pd.isna(f):
        return sanic_json({'error': 'No file for that platform/node/date.'}, status=404)

    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(None, pu.plot_l2bc, f, 3)
    fp = io.BytesIO()
    img.save(fp, format='PNG')
    fp.seek(0)
    return sanic_json({'img': 'data:image/png;base64' + base64.b64encode(fp.read()).decode()})

@app.get("/api/l3/platforms")
async def l3_platforms(request):
    files = request.app.ctx.l3_files
    return sanic_json(sorted(files['platform'].unique().tolist()))

@app.get('/api/l3/generate')
async def l3_generate(request):
    files = request.app.ctx.l3_files
    product    = request.args.get('product', 'cloud_fraction')
    platforms  = request.args.get('platform', '').split(',')
    platforms  = [p for p in platforms if p]
    start      = request.args.get('start')
    end        = request.args.get('end')
    plot_type  = request.args.get('plotType', 'meanmap')
    node       = request.args.get('node', 'both')
    surface    = request.args.get('surface', 'all').lower()
    angle      = request.args.get('angle', 'all').lower()
    nodes = ['asc', 'des'] if node == 'both' else [node]
    features = [f for f in request.args.get('features', '').split(',') if f]
    cmap = request.args.get("cmap", "viridis")
    min = float(request.args.get("min", 0))
    max = float(request.args.get("max", 1))
    w = float(request.args.get('w', -180))
    e = float(request.args.get('e', 180))
    s = float(request.args.get('s', -90))
    n = float(request.args.get('n', 90))

    if not platforms:
        return sanic_json({'error': 'Select at least one platform.'}, status=400)
    
    subset = l3_utils.filter_files(files, product, platforms, start, end)
    if subset.empty:
        return sanic_json({'error': 'No files found for those parameters.'}, status=404)

    bbox = (w, e, s, n)
    cache_key = make_cache_key(product, platforms, start, end, nodes, surface, angle, bbox)


    loop = asyncio.get_event_loop()

    if plot_type == 'meanmap':
        mm_cache = request.app.ctx.meanmap_cache
        if cache_key not in mm_cache:
            lat, lon, meanmap = await loop.run_in_executor(None, l3_utils.compute_meanmap, subset, product, bbox, nodes, surface, angle)
            mm_cache[cache_key] = {"lat":lat, "lon":lon, "meanmap":meanmap, "subset":subset, "product":product, "bbox":bbox}
        cached = mm_cache[cache_key]
        img = await loop.run_in_executor(None, l3_utils.render_meanmap, cached["lat"], cached["lon"], cached["meanmap"], cached["subset"], cached["product"], cached["bbox"], cmap, min, max, features)
        return sanic_json({"img": img, "cacheKey": cache_key,"plot_type": "meanmap"})
        # result = await loop.run_in_executor(None, l3_utils.plot_meanmap, subset, product, bbox, nodes, surface, angle)
        # img, lat, lon, data = result
        # return sanic_json({'img':img, 'lat':lat, 'lon': lon, 'data': data, 'plot_type': 'meanmap'})
    elif plot_type == 'timeseries':
        ts_cache = request.app.ctx.timeseries_cache
        if cache_key not in ts_cache:
            ts_data = await loop.run_in_executor(None, l3_utils.compute_timeseries, subset, product, bbox, nodes, surface, angle)
            ts_cache[cache_key] = {'ts_data': ts_data, 'product': product}
        cached = ts_cache[cache_key]
        img1, img2, img3, colors = await loop.run_in_executor(None, l3_utils.render_timeseries, cached['ts_data'], cached['product'], None)
        return sanic_json({'plot_type': 'timeseries', 'img_mean': img1, 'img_anom_overall': img2, 'img_anom_monthly': img3, 'platforms': list(cached['ts_data'].keys()), 'colors': colors, 'cacheKey': cache_key })
    else: 
        return sanic_json({'error': f'Unknown plot type: {plot_type}'}, status=400)
    
    # return sanic_json({'img': img})

@app.get('/api/l3/rerender-meanmap')
async def l3_rerender(request):
    cache = request.app.ctx.meanmap_cache
    cache_key = request.args.get('cacheKey')
    if cache_key not in cache:
        return sanic_json({"error":"cache expired"}, status=404)
    
    cmap = request.args.get("cmap", "viridis")
    min = float(request.args.get("min",0))
    max = float(request.args.get("max",1))
    features = request.args.get("features", "")
    features = [
        f for f in features.split(",")
        if f
    ]

    cached = cache[cache_key]
    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(None,l3_utils.render_meanmap,cached["lat"],cached["lon"],cached["meanmap"],cached["subset"],cached["product"],cached["bbox"],cmap,min,max,features)
    return sanic_json({"img":img})

@app.get('/api/l3/rerender-timeseries')
async def rerender_timeseries(request):
    cache = request.app.ctx.timeseries_cache
    cache_key = request.args.get('cacheKey')
    if cache_key not in cache:
        return sanic_json({"error":"cache expired"}, status=404)
    
    active = [p for p in request.args.get('platforms', '').split(',') if p]
    cached = cache[cache_key]

    loop = asyncio.get_event_loop()
    img1, img2, img3, colors = await loop.run_in_executor(None, l3_utils.render_timeseries, cached['ts_data'], cached['product'], active or None)

    return sanic_json({'img_mean':img1, 'img_anom_overall':img2, 'img_anom_monthly': img3})

def make_cache_key(product, platforms, start, end, nodes, surface, angle, bbox):
    return '|'.join([
        product, ','.join(sorted(platforms)), str(start), str(end),
        ','.join(nodes), surface, angle, ','.join(str(x) for x in bbox)
    ])

@app.get('/api/l3/download')
async def l3_download(request):
    cache_key = request.args.get('cacheKey')
    plot_type = request.args.get('plotType', 'meanmap')

    if plot_type == 'meanmap':
        cache = request.app.ctx.meanmap_cache
        if cache_key not in cache:
            return sanic_json({"error":"cache expired"}, status=404)
        cached = cache[cache_key]
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, l3_utils.build_meanmap_nc, cached)
    elif plot_type == 'timeseries':
        cache = request.app.ctx.timeseries_cache
        if cache_key not in cache:
            return sanic_json({"error":"cache expired"}, status=404)
        cached = cache[cache_key]
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, l3_utils.build_timeseries_nc, cached)
    else:
        return sanic_json({'error': f'Unknown plot type: {plot_type}'}, status=400)
    
    # stream the file, clean up after
    resp = await sanic_file(
        path,
        mime_type='application/x-netcdf',
        headers={'Content-Disposition': f'attachment; filename="patmosx_{plot_type}.nc"'}
    )
    os.unlink(path)
    return resp

if __name__ == "__main__":
    app.run()