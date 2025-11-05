import argparse
import pandas as pd
from a_spatial_attribution import run_spatial_attribution
from b_statistical_attribution import run_statistical_attribution
from c_gross_land_loss_analysis import run_gross_land_loss_analysis

def main():
    """
    Main function to run the DeDuCE model.

    This script orchestrates the different modules of the DeDuCE model,
    from spatial and statistical attribution of deforestation to the analysis
    of gross cropland and grass loss.
    """
    parser = argparse.ArgumentParser(description="Run the DeDuCE model.")
    parser.add_argument('--run_all', action='store_true', help="Run all steps of the model.")
    parser.add_argument('--run_spatial', action='store_true', help="Run only the spatial attribution.")
    parser.add_argument('--run_statistical', action='store_true', help="Run only the statistical attribution.")
    parser.add_argument('--run_gross_loss', action='store_true', help="Run only the gross land loss analysis.")
    args = parser.parse_args()

    if args.run_all or args.run_spatial:
        print("Starting Spatial Attribution...")
        run_spatial_attribution()
        print("Spatial Attribution completed.")

    if args.run_all or args.run_gross_loss:
        print("Starting Gross Land Loss Analysis...")
        run_gross_land_loss_analysis()
        print("Gross Land Loss Analysis completed.")

    if args.run_all or args.run_statistical:
        print("Starting Statistical Attribution...")
        run_statistical_attribution()
        print("Statistical Attribution completed.")

if __name__ == "__main__":
    main()