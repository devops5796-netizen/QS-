import subprocess
import sys
import os


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_cars_for_sale(start, end):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Cars_for_sale/main.py",
            str(start),
            str(end)
        ],
        check=True,
        env=env
    )


def run_users(start, end):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Users/user_scraper.py",
            str(start),
            str(end)
        ],
        check=True,
        env=env
    )

def run_jobs(start, end):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Jobs/jobs_scraper.py",
            str(start),
            str(end)
        ],
        check=True,
        env=env
    )

def run_showrooms(url, cat):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Showrooms/showroom_main.py",
            url,
            cat
        ],
        check=True,
        env=env
    )
    

"""def run_simple_category(category, start, end):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Simple_Category/main.py",
            category,
            str(start),
            str(end)
        ],
        check=True,
        env=env
    )


def run_sub_category(category, category_path, start, end):
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    subprocess.run(
        [
            sys.executable,
            "Sub_and_Sub_Sub_Categories/main.py",
            category,
            category_path,
            str(start),
            str(end)
        ],
        check=True,
        env=env
    )

"""
if __name__ == "__main__":

    # Cars for sale
    print("=" * 60)
    print("Running cars_for_sale")
    print("=" * 60)

    """run_cars_for_sale(
        start=0,
        end=0
    )"""

    run_showrooms(
        'https://qatarsale.com/ar/showroom/lotus_car_for_cars_169/cars_for_sale',
        'cars_for_sale'
    )

    """
    run_jobs(
        start=0,
        end=0
    )

    run_users(
        start=0,
        end=0
    )"""

"""
    # Simple categories
    categories = [
        "cars_for_rent",
        "bikes",
        "caravan",
        "gift_items",
        "escalator",
        "air_beds_sleeping_bags",
        "cashier_machines",
        "elevators",
        "generators",
        "building_materials",
        "shaving_hair_removal_products",
        "metal_detector",
        "aquariums",
        "business_industrial",
        "pumps",
        "walkie_talkie",
        "glasses",
        "safe_boxes",
        "tracking_systems",
        "pet_accessories",
        "stamps",
        "inflatable_games",
        "porta_cabin",
        "fishing_equipment",
    ]

    for category in categories:
        print("=" * 60)
        print(f"Running {category}")
        print("=" * 60)

        run_simple_category(
            category,
            start=0,
            end=2
        )
 
    # Sub categories
    categories = {
                "car_spare_parts_accessories-automotive_exterior_accessories":
                    "/ar/products/car_spare_parts_accessories-automotive_exterior_accessories?basic_search:StatusFilter=0",
                "heavy_equipments":
                    "/ar/products/heavy_equipments?basic_search:StatusFilter=0",
                "car_spare_parts_accessories":
                    "/ar/products/car_spare_parts_accessories?basic_search:StatusFilter=0",
                "jewellery":
                    "/ar/products/jewellery?basic_search:StatusFilter=0",
                "property":
                    "/ar/products/property?basic_search:StatusFilter=0",
                "watercrafts":
                    "/ar/products/watercrafts?basic_search:StatusFilter=0",
                "computers_and_parts":
                    "/ar/products/computers_and_parts?basic_search:StatusFilter=0",
                "video_games":
                    "/ar/products/video_games?basic_search:StatusFilter=0",
                "wrist_watches":
                    "/ar/products/wrist_watches?basic_search:StatusFilter=0",
                "home_security_surveillance_systems":
                    "/ar/products/home_security_surveillance_systems?basic_search:StatusFilter=0",
                "health_beauty":
                    "/ar/products/health_beauty?basic_search:StatusFilter=0",
                "toys_games":
                    "/ar/products/toys_games?basic_search:StatusFilter=0",
                "kids":
                    "/ar/products/kids?basic_search:StatusFilter=0",
                "shoes_bags":
                    "/ar/products/shoes_bags?basic_search:StatusFilter=0",
                "arts_crafts_sewing":
                    "/ar/products/arts_crafts_sewing?basic_search:StatusFilter=0",
                "kitchen_dining_room":
                    "/ar/products/kitchen_dining_room?basic_search:StatusFilter=0",
                "education":
                    "/ar/products/education?basic_search:StatusFilter=0",
                "bikes_accessories":
                    "/ar/products/bikes_accessories?basic_search:StatusFilter=0",
                "clothes":
                    "/ar/products/clothes?basic_search:StatusFilter=0",
                "camping":
                    "/ar/products/camping?basic_search:StatusFilter=0",
                "tools_home_improvement":
                    "/ar/products/tools_home_improvement?basic_search:StatusFilter=0",
                "men_accessories":
                    "/ar/products/men_accessories?basic_search:StatusFilter=0",
                "musical_instruments":
                      "/ar/products/musical_instruments?basic_search:StatusFilter=0",
                "travel_accessories":
                      "/ar/products/travel_accessories?basic_search:StatusFilter=0",
                "special_numbers":
                      "/ar/products/special_numbers?basic_search:StatusFilter=0",
                "home_appliances":
                  "/ar/products/home_appliances?basic_search:StatusFilter=0",
              "services":
                  "/ar/products/services?basic_search:StatusFilter=0",
              "mobile_telephone_and_tablets":
                  "/ar/products/mobile_telephone_and_tablets?basic_search:StatusFilter=0",
              "furniture_dcor":
                  "/ar/products/furniture_dcor?basic_search:StatusFilter=0",
              "electronics":
                  "/ar/products/electronics?basic_search:StatusFilter=0",
              "sportswear_equipment":
                  "/ar/products/sportswear_equipment?basic_search:StatusFilter=0"
          }

    for category, category_path in categories.items():
        print("=" * 60)
        print(f"Running {category}")
        print("=" * 60)

        run_sub_category(
            category,
            category_path,
            start=0,
            end=2
        )
    
    print("ALL DONE")


from pathlib import Path
import pandas as pd
import json

root = Path("excel_to_check")

all_files_columns = {}

for excel_file in root.glob("*.xlsx"):
    if excel_file.name.startswith("~$"):
        continue

    try:
        sheets = pd.read_excel(excel_file, sheet_name=None)

        file_columns = set()
        has_data = False

        for _, df in sheets.items():
            if df.empty:
                continue

            has_data = True
            file_columns.update(df.columns.tolist())

        if not has_data:
            print(f"Skipping empty file: {excel_file.name}")
            continue

        all_files_columns[excel_file.name] = file_columns

    except Exception as e:
        print(f"Failed reading {excel_file}: {e}")

# ==========================
# Common columns across all files
# ==========================

if all_files_columns:
    common_columns = set.intersection(*all_files_columns.values())
else:
    common_columns = set()

# ==========================
# Per-file analysis
# ==========================

files_result = {}

for file_name, columns in all_files_columns.items():
    files_result[file_name] = {
        "all_columns": sorted(columns),
        "unique_columns": sorted(columns - common_columns),
    }

# ==========================
# Save JSON
# ==========================

output = {
    "total_files": len(all_files_columns),
    "common_columns_across_all_files": sorted(common_columns),
    "files": files_result,
}

with open("columns_analysis.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)

print("Done -> columns_analysis.json")"""