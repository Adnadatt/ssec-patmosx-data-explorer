# pickle_files.py
# scans the data directors, builds a lookup table, caches it

import l2bc_utils
import pandas as pd
from pathlib import Path

DB = 'files.pickle'
root = Path('/data/www/patmosx_l2bc')

# reads the CSV index of all available files, 'date' parsed as datetime objects
_files = pd.read_csv(root / 'index.csv', parse_dates=['date'])

_files['root'] = str(root) + '/'
_files['path'] = _files['root'].str.cat(_files['path'])

files = l2bc_utils.pivot_files(_files)
files.to_pickle(DB)