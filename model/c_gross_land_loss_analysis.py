#!/usr/bin/env python
# c_gross_land_loss_analysis.py

"""
DeDuCE Gross Land Loss Analysis Module

This script calculates the gross annual loss of cropland and grassland for specified
regions. It uses C3S land cover data and a conversion matrix to estimate changes
between years. The analysis can be run for national or sub-national levels depending
on the input shapefile.

This module reads all its configuration from 'config.yaml'.
"""

import argparse
import math
import os
import warnings
import yaml
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ==============================================================================
# 1. CONFIGURATION LOADER
# ==============================================================================

def load_config(config_path='config.yaml'):
    """
    Loads and processes the main configuration file from YAML.

    Args:
        config_path (str): Path to the YAML configuration file.

    Returns:
        dict: A dictionary containing the processed configuration.
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Construct full paths from the base directory
    base_dir = config['paths']['base_dir']
    
    # This path construction logic should handle all paths in the config.
    # We will focus on the paths relevant to this specific script.
    config['paths']['inputs']['shapefile_national'] = os.path.join(base_dir, config['paths']['inputs']['shapefile_national'])
    config['paths']['inputs']['c3s_data_dir'] = os.path.join(base_dir, config['paths']['inputs']['c3s_data_dir'])
    config['paths']['inputs']['conversion_matrix_excel'] = os.path.join(base_dir, config['paths']['inputs']['conversion_matrix_excel'])
    config['paths']['outputs']['gross_loss_output_dir'] = os.path.join(base_dir, config['paths']['outputs']['gross_loss_output_dir'])

    return config

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================

def areaquad(lat_max, lat_min, csize, shape):
    """
    Creates a GCS raster where the cell value is the area of the cell in hectares.
    (Simplified from notebook for clarity - assumes wgs84 datum)
    """
    a, b = 6378137.0, 6356752.3  # wgs84
    e2 = (a**2 - b**2) / (a**2)
    e = math.sqrt(e2)
    
    nrow, ncol = shape
    
    lats1 = np.linspace(lat_max, lat_min + csize, num=nrow)
    lats2 = lats1 - csize
    latin1 = np.radians(lats1)
    latin2 = np.radians(lats2)
    
    fact1 = e**2 / 3 + 31 * e**4 / 180 + 517 * e**6 / 5040
    fact2 = 23 * e**4 / 360 + 251 * e**6 / 3780
    fact3 = 761 * e**6 / 45360
    latout1 = latin1 - fact1 * np.sin(2 * latin1) + fact2 * np.sin(4 * latin1) + fact3 * np.sin(6 * latin1)
    latout2 = latin2 - fact1 * np.sin(2 * latin2) + fact2 * np.sin(4 * latin2) + fact3 * np.sin(6 * latin2)

    r_2 = math.sqrt((a**2 / 2) + (b**2 / 2) * (math.atanh(e) / e))
    r2_km = r_2 / 1000.0

    cst = (np.pi / 180) * (r2_km ** 2)
    area = cst * np.absolute(np.sin(latout1) - np.sin(latout2)) * np.absolute(csize)
    grid = np.tile(area, (ncol, 1)).T
    return grid * 100  # Convert km^2 to hectares

# ==============================================================================
# 3. CORE LOGIC
# ==============================================================================

def calculate_gross_change_for_region(region_name, year, gdf, conversion_matrix, config):
    """
    Calculates the gross loss of cropland and grassland for a specific region and year.
    """
    try:
        shape = gdf[gdf[config['parameters']['gross_loss_analysis']['region_id_column']] == region_name]
        if shape.empty:
            print(f"Warning: No geometry found for {region_name}. Skipping.")
            return 0, 0
            
        _, lat_min, _, lat_max = shape.total_bounds

        tiff_path_prev = os.path.join(config['paths']['inputs']['c3s_data_dir'], f'C3S-LC-L4-LCCS-Map-300m-P1Y-{year-1}-v2.1.1.tif')
        with rasterio.open(tiff_path_prev) as src:
            clipped_prev, transform = mask(src, shapes=shape.geometry, crop=True)
        
        csize = transform[0]
        array_shape = clipped_prev[0].shape
        
        tiff_path_curr = os.path.join(config['paths']['inputs']['c3s_data_dir'], f'C3S-LC-L4-LCCS-Map-300m-P1Y-{year}-v2.1.1.tif')
        with rasterio.open(tiff_path_curr) as src:
            clipped_curr, _ = mask(src, shapes=shape.geometry, crop=True)

        pixel_area_ha = areaquad(lat_max, lat_min, csize, array_shape)
        
        pft_y = clipped_curr[0].flatten()
        pft_y_minus_1 = clipped_prev[0].flatten()
        pixel_area_flat = pixel_area_ha.flatten()

        crop_factors_y = conversion_matrix.loc[pft_y, 'Crop'].values
        crop_factors_y_minus_1 = conversion_matrix.loc[pft_y_minus_1, 'Crop'].values
        
        grass_factors_y = conversion_matrix.loc[pft_y, 'Grass'].values
        grass_factors_y_minus_1 = conversion_matrix.loc[pft_y_minus_1, 'Grass'].values

        result_crop = (crop_factors_y - crop_factors_y_minus_1) * pixel_area_flat / 100
        result_grass = (grass_factors_y - grass_factors_y_minus_1) * pixel_area_flat / 100
        
        gross_crop_loss = np.sum(result_crop[result_crop < 0])
        gross_grass_loss = np.sum(result_grass[result_grass < 0])
        
        return gross_crop_loss, gross_grass_loss

    except Exception as e:
        print(f"Error processing {region_name} for year {year}: {e}")
        return 0, 0

# ==============================================================================
# 4. MAIN ORCHESTRATION FUNCTION
# ==============================================================================

def run_gross_land_loss_analysis(config):
    """
    Orchestrates the entire gross land loss analysis workflow.
    """
    print("Starting Gross Land Loss Analysis...")
    
    # Extract relevant config sections for clarity
    paths = config['paths']
    params = config['parameters']['gross_loss_analysis']
    
    print("Loading shapefile and conversion matrix...")
    try:
        gdf = gpd.read_file(paths['inputs']['shapefile_national'])
        conversion_matrix = pd.read_excel(paths['inputs']['conversion_matrix_excel'], 'Aggregated CF', index_col=0).fillna(0)
    except FileNotFoundError as e:
        print(f"Error: Required file not found. {e}")
        return

    regions = sorted(gdf[params['region_id_column']].unique())
    results_df = pd.DataFrame({params['region_id_column']: regions})
    
    for year in range(params['start_year'], params['end_year'] + 1):
        print(f"\nProcessing year: {year}")
        croploss_final = []
        grassloss_final = []

        for region in tqdm(regions, desc=f"  Regions in {year}"):
            croploss, grassloss = calculate_gross_change_for_region(region, year, gdf, conversion_matrix, config)
            croploss_final.append(croploss)
            grassloss_final.append(grassloss)

        results_df[f'Croploss_{year}'] = croploss_final
        results_df[f'Grassloss_{year}'] = grassloss_final

    # Convert units from hectares to Million km^2
    loss_cols = [col for col in results_df.columns if 'loss' in col.lower()]
    results_df[loss_cols] /= (10**8)
    
    # Save results to Excel
    output_filename = f"{params['output_filename_prefix']}_{params['start_year']}-{params['end_year']}.xlsx"
    output_filepath = os.path.join(paths['outputs']['gross_loss_output_dir'], output_filename)
    
    os.makedirs(paths['outputs']['gross_loss_output_dir'], exist_ok=True)
    
    print(f"\nSaving results to {output_filepath}...")
    with pd.ExcelWriter(output_filepath, engine='xlsxwriter') as writer:
        year_range = range(params['start_year'], params['end_year'] + 1)
        
        crop_loss_df = results_df[[params['region_id_column']] + [f'Croploss_{y}' for y in year_range]]
        grass_loss_df = results_df[[params['region_id_column']] + [f'Grassloss_{y}' for y in year_range]]
        
        crop_loss_df.to_excel(writer, sheet_name='crop_loss', index=False)
        grass_loss_df.to_excel(writer, sheet_name='grass_loss', index=False)

    print("Gross Land Loss Analysis completed successfully.")


# ==============================================================================
# 5. COMMAND-LINE INTERFACE
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate gross cropland and grassland loss from C3S land cover data.")
    
    parser.add_argument(
        '--config', 
        type=str, 
        default='config.yaml', 
        help='Path to the YAML configuration file.'
    )
    
    args = parser.parse_args()

    try:
        CONFIG = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{args.config}'. Please provide a valid path.")
        exit()
    
    run_gross_land_loss_analysis(CONFIG)