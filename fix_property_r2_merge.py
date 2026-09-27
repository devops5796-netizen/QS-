"""
One-off cleanup script.

Scans every day-folder already on R2 under qatarsale/.../property/, finds
the old page-range-split files (e.g. property_for_sale_1_20_property.xlsx,
property_for_sale_41_60_property.xlsx, ...), merges each split's sheets
together (with the same product_url de-dup the workflow already does),
re-uploads them under one clean name (property_for_sale_property.xlsx /
.json) and deletes the old split parts.

Safe by default: runs in DRY_RUN mode (prints what it *would* do) unless
you explicitly set DRY_RUN=false.

Usage:
    python fix_property_r2_merge.py                # dry run, just prints
    DRY_RUN=false python fix_property_r2_merge.py   # actually uploads + deletes

Requires the same .env as the rest of the pipeline:
CF_R2_ACCESS_KEY_ID, CF_R2_SECRET_ACCESS_KEY, CF_R2_ENDPOINT_URL, CF_R2_BUCKET_NAME
"""
import os
import re
import json
import shutil
import boto3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

CF_R2_ACCESS_KEY = os.getenv("CF_R2_ACCESS_KEY_ID")
CF_R2_SECRET_KEY = os.getenv("CF_R2_SECRET_ACCESS_KEY")
CF_R2_ENDPOINT_URL = os.getenv("CF_R2_ENDPOINT_URL")
BUCKET_NAME = os.getenv("CF_R2_BUCKET_NAME", "")

# Same endpoint-cleanup logic as Common_files/r2_uploader.py
CLEAN_ENDPOINT = ""
if CF_R2_ENDPOINT_URL:
    CLEAN_ENDPOINT = CF_R2_ENDPOINT_URL.rstrip("/").removesuffix("/" + BUCKET_NAME)

DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"  # default: dry run
TMP_DIR = "r2_property_fix_tmp"

# Matches the "_<start>_<end>" chunk main.py adds to keep matrix-job
# filenames unique, e.g. "property_for_sale_1_20_property.xlsx"
PAGE_RANGE_RE = re.compile(r"_\d+_\d+")
INVALID_SHEET_CHARS = re.compile(r'[\\/*?:\[\]]')


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=CLEAN_ENDPOINT,
        aws_access_key_id=CF_R2_ACCESS_KEY,
        aws_secret_access_key=CF_R2_SECRET_KEY,
        region_name="auto",
    )


def strip_page_range(name: str) -> str:
    return PAGE_RANGE_RE.sub("", name)


def list_property_day_prefixes(client) -> list[str]:
    """Every qatarsale/year=*/month=*/day=*/property prefix in the bucket."""
    prefixes = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="qatarsale/"):
        for obj in page.get("Contents", []):
            m = re.match(r"^(qatarsale/year=\d+/month=\d+/day=\d+/property)/", obj["Key"])
            if m:
                prefixes.add(m.group(1))
    return sorted(prefixes)


def list_excel_keys(client, day_prefix: str) -> list[str]:
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=f"{day_prefix}/excel/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".xlsx"):
                keys.append(obj["Key"])
    return keys


def process_day(client, day_prefix: str) -> None:
    excel_keys = list_excel_keys(client, day_prefix)

    groups: dict[str, list[str]] = {}
    for key in excel_keys:
        base = os.path.basename(key)
        clean = strip_page_range(base)
        if clean == base:
            continue  # already a clean, merged filename -- skip
        groups.setdefault(clean, []).append(key)

    if not groups:
        print(f"  {day_prefix}: nothing to merge")
        return

    os.makedirs(TMP_DIR, exist_ok=True)

    for clean_name, keys in groups.items():
        print(f"  {day_prefix}: merging {len(keys)} part(s) -> {clean_name}")

        sheets: dict[str, pd.DataFrame] = {}
        for key in keys:
            local_path = os.path.join(TMP_DIR, os.path.basename(key))
            client.download_file(BUCKET_NAME, key, local_path)
            xl = pd.ExcelFile(local_path)
            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                sheets[sheet] = (
                    pd.concat([sheets[sheet], df], ignore_index=True)
                    if sheet in sheets else df
                )

        for sheet_name, df in sheets.items():
            if "product_url" in df.columns:
                sheets[sheet_name] = df.drop_duplicates(subset=["product_url"], keep="first")

        merged_excel_local = os.path.join(TMP_DIR, clean_name)
        with pd.ExcelWriter(merged_excel_local, engine="openpyxl") as writer:
            for sheet_name, df in sheets.items():
                safe = INVALID_SHEET_CHARS.sub("-", sheet_name)[:31]
                df.to_excel(writer, sheet_name=safe, index=False)
                print(f"    sheet '{safe}': {len(df)} rows")

        json_name = clean_name.replace(".xlsx", ".json")
        records = []
        for sheet_name, df in sheets.items():
            recs = df.to_dict(orient="records")
            for r in recs:
                r["_sheet"] = sheet_name
            records.extend(recs)
        merged_json_local = os.path.join(TMP_DIR, json_name)
        with open(merged_json_local, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        merged_excel_key = f"{day_prefix}/excel/{clean_name}"
        merged_json_key = f"{day_prefix}/json/{json_name}"
        old_json_keys = [
            f"{day_prefix}/json/" + os.path.basename(k).replace(".xlsx", ".json")
            for k in keys
        ]

        if DRY_RUN:
            print(f"    [dry-run] would upload {merged_excel_key}")
            print(f"    [dry-run] would upload {merged_json_key}")
            print(f"    [dry-run] would delete {len(keys)} old excel key(s) + {len(old_json_keys)} old json key(s)")
        else:
            client.upload_file(
                merged_excel_local, BUCKET_NAME, merged_excel_key,
                ExtraArgs={"ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            print(f"    uploaded {merged_excel_key}")

            client.upload_file(
                merged_json_local, BUCKET_NAME, merged_json_key,
                ExtraArgs={"ContentType": "application/json; charset=utf-8"},
            )
            print(f"    uploaded {merged_json_key}")

            for key in keys:
                client.delete_object(Bucket=BUCKET_NAME, Key=key)
            for key in old_json_keys:
                client.delete_object(Bucket=BUCKET_NAME, Key=key)
            print(f"    deleted {len(keys)} old excel + {len(old_json_keys)} old json part(s)")

    shutil.rmtree(TMP_DIR, ignore_errors=True)


def main():
    if not all([CF_R2_ACCESS_KEY, CF_R2_SECRET_KEY, CLEAN_ENDPOINT, BUCKET_NAME]):
        print("Missing R2 credentials (check your .env).")
        return

    print(f"Mode: {'DRY RUN (no changes will be made)' if DRY_RUN else 'LIVE (will upload + delete on R2)'}")

    client = get_client()
    day_prefixes = list_property_day_prefixes(client)
    print(f"Found {len(day_prefixes)} property day-folder(s) on R2\n")

    for day_prefix in day_prefixes:
        process_day(client, day_prefix)


if __name__ == "__main__":
    main()