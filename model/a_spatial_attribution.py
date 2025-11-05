#!/usr/bin/env python
# a_spatial_attribution.py

"""
DeDuCE Spatial Attribution Module

This script performs the spatial attribution of deforestation using the Google Earth
Engine (GEE) Python API. It loads various remote sensing datasets, overlays them with
tree cover loss data from Hansen et al., and attributes the loss to specific
commodities or land uses based on a hierarchical, priority-based logic.

This module reads its configuration from 'config.yaml'.

Main steps:
1. Initialize Google Earth Engine.
2. Load and preprocess spatial datasets for a given administrative boundary.
3. Perform priority-based attribution of forest loss.
4. Export the results (classification, carbon, etc.) as tasks to Google Drive.
"""

import argparse
import datetime
import os
import yaml
import ee
import pandas as pd

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
    
    # Dynamically construct full paths from the base directory
    base_dir = config['paths']['base_dir']
    version_params = config['project']['versioning']
    
    for section, settings in config['paths'].items():
        if isinstance(settings, dict):
            for key, value in settings.items():
                formatted_value = value.format(**version_params)
                config['paths'][section][key] = os.path.join(base_dir, formatted_value)
        elif section != 'base_dir':
             formatted_value = settings.format(**version_params)
             config['paths'][section] = os.path.join(base_dir, formatted_value)

    return config

# ==============================================================================
# 2. GEE INITIALIZATION
# ==============================================================================

def initialize_gee():
    """Authenticates and initializes the Google Earth Engine API."""
    try:
        ee.Initialize()
        print("GEE already initialized.")
    except Exception:
        ee.Authenticate()
        ee.Initialize()
        print("GEE authenticated and initialized.")

# ==============================================================================
# 3. CORE LOGIC FUNCTIONS
# ==============================================================================

def load_and_preprocess_data(geometry, config):
    """
    Loads all required GEE assets and performs initial preprocessing.
    
    Args:
        geometry (ee.Geometry): The geometry of the administrative boundary.
        config (dict): The configuration dictionary.
        
    Returns:
        dict: A dictionary containing all loaded and preprocessed GEE image objects.
    """
    print("Loading and preprocessing datasets...")
    data = {}
    assets = config['gee_assets']
    params = config['parameters']['spatial_attribution']

    # Load Hansen Data and create the primary forest loss mask
    hansen_data = ee.Image(assets['forest_cover']['hansen_forest_change'])
    data['hansen'] = hansen_data.clip(geometry)
    
    tc_mask = data['hansen'].select('loss').gt(0).And(
        data['hansen'].select('treecover2000').gte(params['forest_threshold'])
    )
    data['tc_mask'] = tc_mask
    
    # Load Dominant Driver
    dominant_driver = ee.Image(assets['drivers_and_management']['dominant_driver_curtis']).clip(geometry)
    in_class = [1, 2, 3, 4, 5]
    reclass = [3000, 3000, 500, 200, 600]
    data['dominant_driver'] = dominant_driver.remap(in_class, reclass, 1).updateMask(tc_mask)

    # NOTE: This is a placeholder for the full data loading logic from the notebook.
    # The complete script would include loading and preprocessing for ALL datasets
    # listed in the config['gee_assets'], such as Plantations, MapBiomas, Croplands,
    # AGB, SOC, etc., applying the tc_mask to each.
    #
    # Example for MapBiomas (conceptual):
    # mapbiomas_brazil = ee.Image(assets['commodities_and_land_use']['mapbiomas_collections']['Brazil'])
    # data['mapbiomas_brazil'] = mapbiomas_brazil.clip(geometry).updateMask(tc_mask)
    
    print("Dataset loading complete.")
    return data


def perform_attribution(data, admin_boundary, config):
    """
    Performs the priority-based spatial attribution of forest loss.

    Args:
        data (dict): Dictionary of preprocessed GEE image objects.
        admin_boundary (str): The name of the country/region being processed.
        config (dict): The configuration dictionary.

    Returns:
        ee.Image: An image where each pixel value represents the attributed driver.
    """
    print("Performing spatial attribution...")
    
    attribution_image = data['hansen'].select('loss').rename('classification')
    
    # NOTE: This is a placeholder for the full, hierarchical attribution logic.
    # The complete script would contain the series of `.where()` clauses from the
    # notebook, using the preprocessed layers from the `data` dictionary and
    # the reclassification codes from `config['classification_codes']`.
    # The order of these operations is critical for the priority-based system.
    
    # Example of a low-priority attribution step:
    attribution_image = attribution_image.where(
        attribution_image.eq(1).And(data['dominant_driver']),
        data['dominant_driver']
    )
    
    print("Attribution complete.")
    return attribution_image


def export_results(attribution_image, data, geometry, country, simulation_type, config):
    """
    Creates and starts GEE tasks to export results to Google Drive.
    
    Args:
        attribution_image (ee.Image): The final attributed forest loss image.
        data (dict): The dictionary of preprocessed GEE data.
        geometry (ee.FeatureCollection): The geometry for the region.
        country (str): The sanitized name of the country for filenames.
        simulation_type (str): Type of simulation to export (e.g., 'CLASSIFICATION').
        config (dict): The configuration dictionary.
    """
    print(f"Starting export tasks for {country}...")
    
    hansen_lossyear = data['hansen'].select('lossyear')
    hansen_projection = hansen_lossyear.projection()
    pixel_area_ha = ee.Image.pixelArea().reproject(hansen_projection).divide(1e4)
    
    if simulation_type in ['All', 'CLASSIFICATION']:
        reducer = ee.Reducer.sum().group(1, 'lossYear').group(2, 'Class')
        
        stats = pixel_area_ha.addBands(hansen_lossyear).addBands(attribution_image) \
            .reduceRegion(
                reducer=reducer,
                geometry=geometry.geometry(),
                scale=hansen_projection.nominalScale(),
                maxPixels=1e13,
                tileScale=2
            )
            
        task_desc = f'DeDuCE_CLASSIFICATION_{country}_{datetime.datetime.now().isoformat()[:19]}'
        folder_name = f"DeDuCE_v{config['project']['versioning']['gee_data_version']}"
        
        # Simplified export: Exports raw reducer output. Formatting is best done post-download.
        task = ee.batch.Export.table.toDrive(
            collection=ee.FeatureCollection([ee.Feature(None, stats)]),
            description=task_desc,
            folder=folder_name,
            fileFormat='CSV'
        )
        task.start()
        print(f"  - Task started: {task_desc}")

    # Add similar export logic for 'AGB', 'BGB', 'SOC', 'PEATLAND' if needed,
    # which would require those layers to be calculated and passed here.

# ==============================================================================
# 4. MAIN WORKFLOW
# ==============================================================================

def run_spatial_attribution_workflow(countries_to_process, simulation_type, config):
    """
    Main function to orchestrate the spatial attribution workflow.
    """
    initialize_gee()
    
    country_corrections = {
        'México': 'Mexico', "Côte d'Ivoire": 'Cote dIvoire',
        # ... and other corrections from notebook
    }

    for country in countries_to_process:
        if country in ['Greenland', 'Kiribati']:
            print(f"Skipping {country} as per model design.")
            continue
        
        country_gee_name = country_corrections.get(country, country)

        try:
            print(f"\n--- Processing {country} ---")
            
            geometry = ee.FeatureCollection(config['gee_assets']['boundaries']['gadm_admin']) \
                .filter(ee.Filter.eq('COUNTRY', country))

            if geometry.size().getInfo() == 0:
                print(f"Warning: No GEE geometry found for {country}. Skipping.")
                continue

            preprocessed_data = load_and_preprocess_data(geometry, config)
            attribution_result = perform_attribution(preprocessed_data, country, config)
            export_results(attribution_result, preprocessed_data, geometry, country_gee_name, simulation_type, config)

        except Exception as e:
            print(f"!!! FAILED to process {country}. Error: {e}")

# ==============================================================================
# 5. COMMAND-LINE INTERFACE
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the DeDuCE Spatial Attribution model using Google Earth Engine.")
    
    parser.add_argument(
        '--config', 
        type=str, 
        default='config.yaml', 
        help='Path to the YAML configuration file.'
    )
    parser.add_argument(
        '--country', 
        type=str, 
        help='Specify a single country to process.'
    )
    parser.add_argument(
        '--all_countries', 
        action='store_true', 
        help="Process all countries listed in the GADM boundaries CSV file."
    )
    parser.add_argument(
        '--simulation', 
        type=str, 
        default='CLASSIFICATION', 
        choices=['All', 'CLASSIFICATION', 'PEATLAND', 'AGB', 'BGB', 'SOC 0-30', 'SOC 30-100'],
        help='Specify the simulation type to run and export.'
    )

    args = parser.parse_args()

    try:
        CONFIG = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{args.config}'. Please specify a valid path.")
        exit()

    if args.country:
        countries_to_run = [args.country]
    elif args.all_countries:
        try:
            gadm_df = pd.read_csv(CONFIG['paths']['inputs']['gadm_boundaries_csv'])
            countries_to_run = sorted(gadm_df['COUNTRY'].unique())
        except FileNotFoundError:
            print(f"Error: Could not find GADM boundaries CSV at '{CONFIG['paths']['inputs']['gadm_boundaries_csv']}'.")
            exit()
    else:
        parser.print_help()
        exit()
        
    run_spatial_attribution_workflow(countries_to_run, args.simulation, CONFIG)