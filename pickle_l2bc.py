# pickle_l2bc.py
import os
import numpy as np
import netCDF4
import pandas as pd
import l2bc_utils
from products_l2bc import PRODUCTS
from pathlib import Path

L2BC_ROOT = Path(os.environ.get('L2BC_ROOT'))
OUT_PATH = 'l2bc_files.pickle'

def main():
    print("Scanning L2BC files...")
    df = l2bc_utils.scan_files(L2BC_ROOT)
    files = l2bc_utils.pivot_files(df)

    # only keep wanted products in PRODUCTS
    available = [c for c in files.columns if c in PRODUCTS]
    files = files[available]

    files.to_pickle(OUT_PATH)
    print(f"saved {OUT_PATH} - {len(files)} platform/node/date rows, "
          f"{len(available)}/{len(PRODUCTS)} configured variables found on disk")
    
if __name__ == '__main__':
    main()