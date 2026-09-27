"""
One-off cleanup script.

Goes through every day-folder under qatarsale/.../property/ on R2, and for
each split (property_for_sale / property_for_rent):
  1. Merges any leftover page-range parts (in case a day wasn't fixed yet).
  2. Reports duplicate rows per sheet -- first by "id" (the product's own
     id field), falling back to "product_url" for any sheet that has no
     "id" column.
  3. Removes those duplicates, keeping the first occurrence.
  4. Re-uploads the clean excel/json, and deletes any leftover old parts.

Safe by default: DRY_RUN=true (the default) only prints a report of what
duplicates it found -- it uploads and deletes nothing until you re-run with
DRY_RUN=false.

Usage:
    python dedupe_property_r2.py                # dry run, just report
    DRY_RUN=false python dedupe_property_r2.py   # actually clean + upload

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

CLEAN_ENDPOINT = ""
if CF_R2_ENDPOINT_URL:
    CLEAN_ENDPOINT = CF_R2_ENDPOINT_URL.rstrip("/").removesuffix("/" + BUCKET_NAME)

DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"  # default: dry run
TMP_DIR = "r2_property_dedupe_tmp"

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


def dedupe_sheet(df: pd.DataFrame, sheet_name: str, day_prefix: str, clean_name: str) -> pd.DataFrame:
    """Dedupe by 'id' if present, else 'product_url'. Reports what it removed."""
    key_col = "id" if "id" in df.columns else ("product_url" if "product_url" in df.columns else None)
    if key_col is None:
        return df  # nothing reliable to dedupe on -- leave as-is

    before = len(df)
    deduped = df.drop_duplicates(subset=[key_col], keep="first")
    removed = before - len(deduped)

    if removed > 0:
        print(f"    [{day_prefix}/{clean_name}] sheet '{sheet_name}': "
              f"{before} -> {len(deduped)} rows ({removed} duplicate '{key_col}' removed)")
    return deduped


def process_day(client, day_prefix: str) -> None:
    excel_keys = list_excel_keys(client, day_prefix)
    if not excel_keys:
        return

    # Group by clean name -- merges any leftover page-range parts too
    groups: dict[str, list[str]] = {}
    for key in excel_keys:
        clean = strip_page_range(os.path.basename(key))
        groups.setdefault(clean, []).append(key)

    os.makedirs(TMP_DIR, exist_ok=True)

    for clean_name, keys in groups.items():
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

        total_before = sum(len(df) for df in sheets.values())
        for sheet_name in list(sheets.keys()):
            sheets[sheet_name] = dedupe_sheet(sheets[sheet_name], sheet_name, day_prefix, clean_name)
        total_after = sum(len(df) for df in sheets.values())

        had_multiple_parts = len(keys) > 1
        had_duplicates = total_after < total_before

        if not had_multiple_parts and not had_duplicates:
            continue  # already clean and no dupes -- nothing to do

        print(f"  {day_prefix}/{clean_name}: {total_before} -> {total_after} total rows "
              f"({len(keys)} part(s) merged, {total_before - total_after} duplicate(s) removed)")

        merged_excel_local = os.path.join(TMP_DIR, clean_name)
        with pd.ExcelWriter(merged_excel_local, engine="openpyxl") as writer:
            for sheet_name, df in sheets.items():
                safe = INVALID_SHEET_CHARS.sub("-", sheet_name)[:31]
                df.to_excel(writer, sheet_name=safe, index=False)

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
        # old parts to remove: every downloaded key except the clean target
        # itself if it was already among them (we'll re-upload it anyway)
        old_json_keys = [
            f"{day_prefix}/json/" + os.path.basename(k).replace(".xlsx", ".json")
            for k in keys
        ]

        if DRY_RUN:
            print(f"    [dry-run] would upload {merged_excel_key}")
            print(f"    [dry-run] would upload {merged_json_key}")
            if had_multiple_parts:
                print(f"    [dry-run] would delete {len(keys)} old excel + {len(old_json_keys)} old json part(s)")
        else:
            client.upload_file(
                merged_excel_local, BUCKET_NAME, merged_excel_key,
                ExtraArgs={"ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            client.upload_file(
                merged_json_local, BUCKET_NAME, merged_json_key,
                ExtraArgs={"ContentType": "application/json; charset=utf-8"},
            )
            print(f"    uploaded {merged_excel_key} + {merged_json_key}")

            if had_multiple_parts:
                for key in keys:
                    if key != merged_excel_key:
                        client.delete_object(Bucket=BUCKET_NAME, Key=key)
                for key in old_json_keys:
                    if key != merged_json_key:
                        client.delete_object(Bucket=BUCKET_NAME, Key=key)
                print(f"    deleted old parts")

    shutil.rmtree(TMP_DIR, ignore_errors=True)


def main():
    if not all([CF_R2_ACCESS_KEY, CF_R2_SECRET_KEY, CLEAN_ENDPOINT, BUCKET_NAME]):
        print("Missing R2 credentials (check your .env / secrets).")
        return

    print(f"Mode: {'DRY RUN (report only, no changes)' if DRY_RUN else 'LIVE (will upload + delete on R2)'}")

    client = get_client()
    day_prefixes = list_property_day_prefixes(client)
    print(f"Found {len(day_prefixes)} property day-folder(s) on R2\n")

    for day_prefix in day_prefixes:
        process_day(client, day_prefix)


if __name__ == "__main__":
    main()