# products_l2bc.py

PRODUCTS = {
    'cloud_fraction': {
        'label': 'Cloud Fraction',
        'vmin': 0, 'vmax': 1,
        'unit': None,
    },
    'cld_opd_dcomp': {
        'label': 'Cloud Optical Depth',
        'vmin': 0, 'vmax': 100,
        'unit': None,
    },
    'cld_press_acha': {
        'label': 'Cloud Top Pressure',
        'vmin': 50, 'vmax': 1150,
        'unit': 'hPa',
    },
    'cloud_probability': {
        'label': 'Cloud Probability',
        'vmin': 0, 'vmax': 1,
        'unit': None,
    },
    'temp_11_0um_nom': {
        'label': '11 Micron Brightness Temperature',
        'vmin': 180, 'vmax': 340,
        'unit': 'K',
    },
    'refl_0_65um_nom': {
        'label': '0.65 Micron Reflectance',
        'vmin': 0, 'vmax': 120,
        'unit': None,
    },
}