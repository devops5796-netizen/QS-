import sys
import time
import Common_files.excel_writer as excel_writer
from Common_files.detect_utils import analyze_category_with_products
from datetime import datetime, timezone, timedelta
import pandas as pd
from Common_files.request_tracker import tracker
import Common_files.links_scraper as links_scraper
import Common_files.products_scraper as products_scraper
import Common_files.flatten as flatten
from Common_files.columns_loader import load_all_expected_columns, enforce_columns
from dotenv import load_dotenv
load_dotenv()


CATEGORIES = {
    "cars_for_rent":
        "https://qatarsale.com/ar/products/cars_for_rent?basic_search:StatusFilter=0",
    "bikes":
        "https://qatarsale.com/ar/products/bikes?basic_search:StatusFilter=0",
    "caravan":
        "https://qatarsale.com/ar/products/caravan?basic_search:StatusFilter=0",
    "gift_items":
        "https://qatarsale.com/ar/products/gift_items?basic_search:StatusFilter=0",
    "escalator":
        "https://qatarsale.com/ar/products/escalator?basic_search:StatusFilter=0",
    "air_beds_sleeping_bags":
        "https://qatarsale.com/ar/products/air_beds_sleeping_bags?basic_search:StatusFilter=0",
    "cashier_machines":
        "https://qatarsale.com/ar/products/cashier_machines?basic_search:StatusFilter=0",
    "elevators":
        "https://qatarsale.com/ar/products/elevators?basic_search:StatusFilter=0",
    "generators":
        "https://qatarsale.com/ar/products/generators?basic_search:StatusFilter=0",
    "building_materials":
        "https://qatarsale.com/ar/products/building_materials?basic_search:StatusFilter=0",
    "shaving_hair_removal_products":
        "https://qatarsale.com/ar/products/shaving_hair_removal_products?basic_search:StatusFilter=0",
    "metal_detector":
        "https://qatarsale.com/ar/products/metal_detector?basic_search:StatusFilter=0",
    "aquariums":
        "https://qatarsale.com/ar/products/aquariums?basic_search:StatusFilter=0",
    "business_industrial":
        "https://qatarsale.com/ar/products/business_industrial?basic_search:StatusFilter=0",
    "pumps":
        "https://qatarsale.com/ar/products/pumps?basic_search:StatusFilter=0",
    "walkie_talkie":
        "https://qatarsale.com/ar/products/walkie_talkie?basic_search:StatusFilter=0",
    "glasses":
        "https://qatarsale.com/ar/products/glasses?basic_search:StatusFilter=0",
    "safe_boxes":
        "https://qatarsale.com/ar/products/safe_boxes?basic_search:StatusFilter=0",
    "tracking_systems":
        "https://qatarsale.com/ar/products/tracking_systems?basic_search:StatusFilter=0",
    "pet_accessories":
        "https://qatarsale.com/ar/products/pet_accessories?basic_search:StatusFilter=0",
    "stamps":
        "https://qatarsale.com/ar/products/stamps?basic_search:StatusFilter=0",
    "inflatable_games":
        "https://qatarsale.com/ar/products/inflatable_games?basic_search:StatusFilter=0",
    "porta_cabin":
        "https://qatarsale.com/ar/products/porta_cabin?basic_search:StatusFilter=0",
    "fishing_equipment":
        "https://qatarsale.com/ar/products/fishing_equipment?basic_search:StatusFilter=0",
}

EXPECTED_COLUMNS = load_all_expected_columns()

def filter_yesterday_links(links_csv: str, filtered_csv: str) -> dict:
    df = pd.read_csv(links_csv)

    if "startDate" not in df.columns:
        print("⚠️ No startDate column found, using all links")
        df.to_csv(filtered_csv, index=False, encoding="utf-8")
        return {"total": len(df), "yesterday": len(df)}

    df["date_parsed"] = pd.to_datetime(df["startDate"], format="ISO8601", utc=True)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    mask = df["date_parsed"].dt.date == yesterday
    df_yesterday = df[mask].drop(columns=["date_parsed"])

    print(f"  Total links:     {len(df)}")
    print(f"  Yesterday links: {len(df_yesterday)}")

    df_yesterday.to_csv(filtered_csv, index=False, encoding="utf-8")
    return {"total": len(df), "yesterday": len(df_yesterday)}


def run_single_category(category: str, start: int, end: int):
    listing_url = CATEGORIES[category]

    last_page, has_products = analyze_category_with_products(listing_url)
    if not has_products:
        print(f"⚠️ No products found in '{category}' — skipping.")
        return None

    links_csv     = f"links_{category}_{start}_{end}.csv"
    filtered_csv  = f"links_yesterday_{category}_{start}_{end}.csv"
    products_json = f"products_{category}_{start}_{end}.jsonl"
    output_excel  = f"{category}_{start}_{end}.xlsx"

    elapsed_start = time.time()
    print(f"QatarSale Scraper - Single Category")
    print(f"Category: {category} | Pages: {start} to {end}")

    category_path = listing_url.replace("https://qatarsale.com", "").replace("https://www.qatarsale.com", "")
    s1 = links_scraper.run(category_path, start, end, links_csv)
    if s1['total_links'] == 0:
        print(f"⚠️ No links found — skipping.")
        return None

    s_filter = filter_yesterday_links(links_csv, filtered_csv)

    if s_filter["yesterday"] == 0:
        print("\n" + "="*60)
        print("No listings found for yesterday.")
        print("Skipping product scraping and flattening.")
        print("="*60)

        elapsed = time.time() - elapsed_start
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print("\n" + "="*60)
        print("FINAL SUMMARY")
        print("="*60)
        print(f"STEP 1   - Links:    {s1['success']} pages OK | {s1['failed']} failed | {s1['total_links']} total")
        print(f"STEP 1.5 - Filter:   0 yesterday / {s_filter['total']} total")
        print("STEP 2   - Products: Skipped")
        print("STEP 3   - Flatten:  Skipped")
        print(f"Total Time: {minutes}m {seconds}s")
        print("="*60)
        return None

    s2 = products_scraper.run(filtered_csv, products_json, workers=1, category=category)
    if s2['success'] == 0:
        print(f"⚠️ No products scraped for '{category}' — skipping.")
        return None

    s3 = flatten.run(products_json)
    df = s3["df"]
    COLUMNS_TO_DROP = [
            "categoryId", "categoryName", "_CategoryPath", "categoryUri", "createdBy", "thumbnailImages",
            "coverImage", "seoImageUrl", "arSeo", "enSeo", "seoTitle", "seoDesc", "isMyProduct",
            "isFavourite", "returnOriginalImages", "originalImages"
        ]
    df = df.drop(columns=[c for c in COLUMNS_TO_DROP if c in df.columns])

    expected = EXPECTED_COLUMNS.get(category, [])
    df = enforce_columns(df, expected)

    excel_writer.write_split_by_subcategory(df, output_excel, category_column="categoryPath")

    elapsed = time.time() - elapsed_start
    print(f"\nDONE: {s1['total_links']} links | {s2['success']} scraped | {int(elapsed//60)}m {int(elapsed%60)}s")
    stats_file = f"request_stats_{start}_{end}.json"
    stats = tracker.save(stats_file)

    print(f"\n--- Combined Request Stats ---")
    print(f"Total: {stats['total_requests']} req | {stats['total_req_per_min']} req/min")
    print(f"By source: {stats['per_source']}")
    for worker, s in stats["per_worker"].items():
        print(f"  {worker}: {s['requests']} req | {s['req_per_min']} req/min")
    return output_excel


def main():
    if len(sys.argv) == 4:
        category = sys.argv[1]
        start    = int(sys.argv[2])
        end      = int(sys.argv[3])
        if category in CATEGORIES:
            run_single_category(category, start, end)
        else:
            print(f"Unknown category: {category}")
            sys.exit(1)
    else:
        print("Usage: python main.py <category> <start_page> <end_page>")
        sys.exit(1)


if __name__ == "__main__":
    main()