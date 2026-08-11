import sys
import time
import pandas as pd
import showroom_parser
from PIL import Image
import pandas as pd
import requests as req
import io
from datetime import datetime, timezone, timedelta
from Common_files.r2_uploader import upload_buffer
from Common_files.request_tracker import tracker
from Common_files.excel_writer import write_excel_sheets
from dotenv import load_dotenv
load_dotenv()


def download_images(images: list, product_url: str = "", category: str = "", fmt: str = "WEBP") -> list:
    r2_paths = []
    uploaded = 0
    failed = 0

    ext = "webp"

    slug = product_url.rstrip("/").split("/")[-2] if product_url else "unknown"

    for idx, img_url in enumerate(images, start=1):
        filename = f"{slug}-{idx}.{ext}"

        try:
            r = req.get(img_url, timeout=15)

            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content))

                output_buffer = io.BytesIO()

                img = img.convert("RGB")
                img.save(
                    output_buffer,
                    format="WEBP",
                    quality=100,
                    method=6
                )

                output_buffer.seek(0)

                today = datetime.now(timezone.utc)

                r2_key = upload_buffer(
                    output_buffer,
                    filename=filename,
                    category=category,
                    file_type="images",
                    content_type="image/webp",
                    dt=today
                )

                if r2_key:
                    r2_paths.append(r2_key)
                    uploaded += 1
                else:
                    failed += 1

            else:
                failed += 1

        except Exception as e:
            print(f"Image download failed: {e}")
            failed += 1

    print(f"Images: {uploaded} uploaded, {failed} failed out of {len(images)}")
    return r2_paths



def filter_yesterday_links(product_df: pd.DataFrame) -> pd.DataFrame:
    if "startDate" not in product_df.columns:
        print("⚠️ No startDate column found, using all products")
        return product_df

    df = product_df.copy()
    df["date_parsed"] = pd.to_datetime(df["startDate"], format="ISO8601", utc=True)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    mask = df["date_parsed"].dt.date == yesterday
    df_yesterday = df[mask].drop(columns=["date_parsed"])

    print(f"  Total products:     {len(df)}")
    print(f"  Yesterday products: {len(df_yesterday)}")
    return df_yesterday


def process_showroom(url, category_key: str):
    for attempt in range(3):
        try:
            details, product_df = showroom_parser.scrape_showroom(url)

            if product_df is None or product_df.empty:
                print(f"  [EMPTY] No products found")
                return None, "empty"

            df = filter_yesterday_links(product_df)
            if df.empty:
                print("No listings found for yesterday.")
                return None, "empty"

            if details.get("cover_image"):
                r2 = download_images(
                    [details["cover_image"]],
                    product_url=url,
                    category=f"showrooms_{category_key}"
                )
                details["r2_image"] = r2[0] if r2 else ""

            for k, v in details.items():
                df[k] = v

            return df, "success"

        except Exception as e:
            print(f"  [Attempt {attempt + 1}/3] failed: {e}")
            time.sleep(2)

    print(f"  [FAILED] Skipping: {url}")
    return None, "failed"


def run_single_showroom(url, category_key: str = "cars_for_sale"):
    slug = url.split("/ar/showroom/")[-1].split("/")[0] if "/ar/showroom/" in url else "showroom"

    df, status = process_showroom(url, category_key)
    COLUMNS_TO_DROP = [
        "title", "startingPrice", "source_url"
    ]
    if df is not None:
        df = df.drop(columns=[c for c in COLUMNS_TO_DROP if c in df.columns])

    stats_file = f"request_stats_{slug}.json"
    tracker.save(stats_file)

    if status == "success" and df is not None and not df.empty:
        sheets = {slug: df}
        write_excel_sheets(sheets, f"showroom_{slug}.xlsx")
        print(f"  ✓ Saved: showroom_{slug}.xlsx")
        return True
    elif status == "empty":
        empty_df = pd.DataFrame({"status": ["empty - no products found"]})
        write_excel_sheets({slug: empty_df}, f"showroom_{slug}.xlsx")
        print(f"  ⚠ Empty marker saved: showroom_{slug}.xlsx")
    else:
        with open(f"{slug}_failed.txt", "w", encoding="utf-8") as f:
            f.write(url + "\n")
        print(f"  ✗ Failed: {slug}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        cat = sys.argv[2] if len(sys.argv) > 2 else "cars_for_sale"
        run_single_showroom(url, cat)