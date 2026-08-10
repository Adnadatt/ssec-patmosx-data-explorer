# pickle_l3.py
from tqdm import tqdm
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pathlib import Path

L3A_ROOT = Path('[path to L3 files]')
OUT_PATH = 'l3_files.pickle'

def scan_l3_files(root):
    df = []
    with tqdm(root.rglob('*.nc')) as bar:
        for f in bar:
            # patmosx_v06r00_METOP-A_2007_07_1deg_l3a_cloud_fraction.nc
            stem = f.stem # drop .nc
            parts = stem.split('_')
            platform = parts[2]
            year = int(parts[3])
            month = int(parts[4])
            key = '_'.join(parts[7:])
            date = datetime(year,month,1)
            df.append({'platform':platform, 'date':date, 'key':key, 'path':f})
    return pd.DataFrame(df)

def main():
    print("Scanning l3a files...")
    df = scan_l3_files(L3A_ROOT)
    df.to_pickle(OUT_PATH)
    print(f"Saved {OUT_PATH} - {len(df)} files, "
          f"{df['platform'].nunique()} platforms, "
          f"{df['key'].nunique()} products")
    
if __name__ == '__main__':
    main()
