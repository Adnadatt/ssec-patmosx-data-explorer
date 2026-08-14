## Project Structure

- `patmosxDataExplorer.py` — Sanic app, API routes, receives the requests from the user
- `l3_utils.py` — L3 data reading, computation, and plotting
- `plot_utils.py` — L2BC plotting
- `index.html` — frontend
- `pickle_l2bc.py` / `pickle_l3.py` — build the file indexes
- `products_l2bc.py` — L2BC product definitions

## Configuration

Copy the example config script and fill in your local data paths:

```bash
cp config-example.sh config.sh
```

Then edit `config.sh` with the actual paths to your L2BC and L3 data on disk:

```bash
export L2BC_ROOT="/path/to/your/l2bc/data"
export L3_ROOT="/path/to/your/l3a/data"
```

`config.sh` is gitignored since paths may be machine-specific — only
`config-example.sh` (with placeholder values) is tracked in git.

## Setup
Before running the server, build the file indexes by running the following commands from the project root:
```bash
source config.sh
python pickle_l2bc.py 
python pickle_l3.py
```
Each script takes about a minute to run and produces a `.pickle` file
(`l2bc_files.pickle` and `l3_files.pickle` respectively) that the server
loads on startup.

## Running the server
Start the server on port 8001:

```bash
sanic server --dev -p 8001
```

## Accessing the server remotely (via tyr)

If the server is running on `tyr`, open a **separate terminal** and tunnel port 8001 to your local machine:

```bash
ssh -NL 8001:localhost:8001 tyr
```

Leave this terminal open while you are using the server.
Then you can access the server at 

```bash
http://localhost:8001
```

## How to add another cloud product

1. **Add a new entry to `PRODUCT_META`** in `l3_utils.py`. The dictionary key must match the netCDF variable name inside the L3 files exactly.

```python
   PRODUCT_META = {
       ...
       'cloud_top_pressure': {                 # netCDF variable name
           'units': 'km',
           'long_name': 'Cloud Top Pressure',
           'type': 'weighted_mean',            # 'fraction' or 'weighted_mean'
           'counts_var': 'counts',             # 'counts_all' or 'counts'
       },
   }
```
   - Use `'type': 'fraction'` only for products that store raw observation
     counts (like `cloud_fraction`). Everything else — anything the L3 file
     stores as a precomputed per-bin mean plus a separate counts array —
     should use `'type': 'weighted_mean'`.
   - `ALLOWED_PRODUCTS` in `patmosxDataExplorer.py` is derived automatically
     from `PRODUCT_META.keys()`, so no changes needed there.

2. **Confirm that the product's `key` matches what `pickle_l3.py` extracts.**
    `pickle_l3.py` parses the product key from the filename itself
   (`patmosx_v06r00_METOP-A_2007_07_1deg_l3a_<key>.nc`) — the `key` your new
   `PRODUCT_META` entry uses must match that filename suffix exactly, or
   `filter_files()` will never find any matching rows.

3. **Add the new cloud product option to the dropdown** in `index.html`:

```html
   <select id="l3-product">
       ...
       <option value="cloud_top_pressure">Cloud Top pressure</option>
   </select>
```

4. **Add default color range** to `PRODUCT_RANGES` in `index.html`'s `<script>` block. This forces the mean map colorbar to start at a sensible range instead of the previous product's leftover values:

```javascript
   const PRODUCT_RANGES = {
       ...
       cloud_top_pressure: [50, 1100],
   }
```

5. **Re-run `pickle_l3.py`** (see Setup above) so the file index is updated with the new product, then restart the server.

7. **Sanity check**: generate a meanmap for the new product with "All"
   platforms and a short date range, and confirm the values fall in a
   physically reasonable range for that variable before trusting it.

## How to add another plot

