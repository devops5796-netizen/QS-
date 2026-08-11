import json
import time
import pandas as pd
import sys
import requests as req
from PIL import Image
import io
from Common_files.r2_uploader import upload_buffer
from datetime import datetime, timezone, timedelta
from Common_files.request_tracker import tracker

API_URL = "https://production-api.qatarsale.com/api/ApplicantProfile/Search"
DETAILS_API_URL = "https://production-api.qatarsale.com/api/ApplicantProfile/GetProfileDetails"
BASE_PROFILE_URL = "https://qatarsale.com/ar/jobs/user/profile"
PAGE_SIZE = 15

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://qatarsale.com/",
    "Origin": "https://qatarsale.com",
}


def get_all_users(start_page: int = 0, end_page: int = None) -> list[dict]:
    all_users = []

    if end_page is None:
        payload = {
            "currentPage": 0, "pageSize": PAGE_SIZE, "sortBy": 0,
            "employmentTypes": [], "searchTerm": "", "yearsOfExperience": [],
            "cities": [], "countries": [], "degrees": [], "languages": [],
            "opportunityUri": None, "skills": [], "workFields": [], "workSpecialities": [],
            "isFavorite": False
        }
        tracker.log_request(source="users_search")
        r = req.post(API_URL, json=payload, headers=HEADERS, timeout=30)
        data = r.json()
        end_page = data.get("pagesCount", 1) - 1
        print(f"  Detected {end_page + 1} pages | {data.get('count', 0)} total users")

    for page in range(start_page, end_page + 1):
        payload = {
            "currentPage": page, "pageSize": PAGE_SIZE, "sortBy": 0,
            "employmentTypes": [], "searchTerm": "", "yearsOfExperience": [],
            "cities": [], "countries": [], "degrees": [], "languages": [],
            "opportunityUri": None, "skills": [], "workFields": [], "workSpecialities": [],
            "isFavorite": False
        }
        try:
            tracker.log_request(source="users_search")
            r = req.post(API_URL, json=payload, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            users = data.get("list", [])
            if not users:
                break
            print(f"  Page {page}: {len(users)} users")
            all_users.extend(users)
            time.sleep(1)
        except Exception as e:
            print(f"  [ERROR] Page {page}: {e}")
            break

    return all_users


def parse_user_details(uri_code: str) -> dict:
    if not uri_code:
        return {}

    url = f"{BASE_PROFILE_URL}/{uri_code}"

    try:
        tracker.log_request(source="users_details")
        response = req.get(
            DETAILS_API_URL,
            params={"uriCode": uri_code},
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()
        user = response.json()

        if not user.get("id"):
            return {}

        row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
               for k, v in user.items()}
        row["profile_url"] = url
        return row

    except Exception as e:
        print(f"  [ERROR] {uri_code}: {e}")
        return {}


def download_and_upload_image(img_url: str, user_uri: str) -> str:
    if not img_url:
        return ""
    today = datetime.now(timezone.utc)
    try:
        r = req.get(img_url, timeout=15)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content))
            output_buffer = io.BytesIO()
            img.save(
                    output_buffer,
                    format="WEBP",
                    quality=100,
                    method=6
                )
            filename = f"{user_uri}.webp"
            r2_key = upload_buffer(
                output_buffer,
                filename=filename,
                folder_name="qatarsale",
                category="users",
                file_type="images",
                content_type="image/webp",
                dt = today
            )
            return r2_key or ""
        return ""
    except Exception as e:
        print(f"  [ERROR] Image upload failed for {user_uri}: {e}")
        return ""


def filter_yesterday_links(users: list[dict]) -> dict:
    df = pd.DataFrame(users)

    if "activatedAt" not in df.columns:
        print("⚠️ No activatedAt column found, using all users")
        return {
            "total": len(df),
            "yesterday": len(df),
            "filtered_users": users
        }

    df["date_parsed"] = pd.to_datetime(df["activatedAt"], format="ISO8601", utc=True)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    mask = df["date_parsed"].dt.date == yesterday
    df_yesterday = df[mask].drop(columns=["date_parsed"])

    print(f"  Total users:     {len(df)}")
    print(f"  Yesterday users: {len(df_yesterday)}")

    filtered_users = df_yesterday.to_dict('records')

    return {
        "total": len(df),
        "yesterday": len(df_yesterday),
        "filtered_users": filtered_users
    }


def run(output_excel: str = "users.xlsx", start_page: int = 0, end_page: int = None) -> dict:
    print("=" * 50)
    print("QatarSale Users Scraper")
    print("=" * 50)

    start_time = time.time()

    print("\nSTEP 1: Fetching users from API...")
    raw_users = get_all_users(start_page=start_page, end_page=end_page)
    print(f"Total users fetched: {len(raw_users)}")

    if not raw_users:
        print("No users found!")
        return {"total": 0, "success": 0, "failed": 0}

    print("\nSTEP 2: Scraping user details...")
    results = []
    failed = []
    uri_map = {user.get("uriCode", ""): user for user in raw_users}

    total_checked = 0
    total_yesterday = 0

    for i, user in enumerate(raw_users, 1):
        uri = user.get("uriCode", "")

        print(f"  [{i}/{len(raw_users)}] uriCode={uri}")

        data = parse_user_details(uri) if uri else {}

        if data:
            total_checked += 1
            filter_result = filter_yesterday_links([data])
            filtered_data = filter_result["filtered_users"]

            if filtered_data:
                total_yesterday += 1
                img_url = user.get("personalPictureUrl", "")
                r2_image = download_and_upload_image(img_url, uri)
                data["image_r2_key"] = r2_image
                results.append(data)
                print(f"    ✓ {data.get('fullName', 'OK')} (yesterday)")
            else:
                print(f"      Skipped (not yesterday): {data.get('fullName', 'N/A')}")
        else:
            failed.append(uri)
            print(f"    ✗ Failed")

        # if data:
        #     img_url = user.get("personalPictureUrl", "")
        #     r2_image = download_and_upload_image(img_url, uri)
        #     data["image_r2_key"] = r2_image
        #     results.append(data)
        #     print(f"    ✓ {data.get('fullName', 'OK')}")

        # else:
        #     failed.append(uri)
        #     print(f"    ✗ Failed")

    # Retry
    if failed:
        print(f"\nRetrying {len(failed)} failed URIs...")
        still_failed = []
        for uri in failed:
            data = parse_user_details(uri)
            if data:
                total_checked += 1
                filter_result = filter_yesterday_links([data])
                filtered_data = filter_result["filtered_users"]

                if filtered_data:
                    total_yesterday += 1
                    user = uri_map.get(uri, {})
                    img_url = user.get("personalPictureUrl", "")
                    r2_image = download_and_upload_image(img_url, uri)
                    data["image_r2_key"] = r2_image
                    results.append(data)
                    print(f"  ✓ {uri} (yesterday)")
                else:
                    print(f"      Skipped (not yesterday): {uri}")
            else:
                still_failed.append(uri)
                print(f"  ✗ {uri}")
            # if data:
            #     user = uri_map.get(uri, {})
            #     img_url = user.get("personalPictureUrl", "")
            #     r2_image = download_and_upload_image(img_url, uri)
            #     data["image_r2_key"] = r2_image
            #     results.append(data)
            #     print(f"    ✓ {data.get('fullName', 'OK')} (yesterday)")
            # else:
            #     still_failed.append(uri)
            #     print(f"  ✗ {uri}")

        failed = still_failed

    print(f"\nSTEP 3: Saving {len(results)} users to Excel...")
    print(f"  Total checked: {total_checked} | Yesterday: {total_yesterday}")

    df = pd.DataFrame(results)
    df.to_excel(output_excel, index=False, sheet_name="users")
    print(f"Saved: {output_excel}")

    if failed:
        with open("failed_urls.txt", "w", encoding="utf-8") as f:
            f.write(f"Total Failed URLs: {len(failed)}\n\n")
            for u in failed:
                f.write(f"{BASE_PROFILE_URL}/{u}\n")

    elapsed = time.time() - start_time
    print(f"\nDONE: {len(results)} users | {len(failed)} failed | {int(elapsed//60)}m {int(elapsed%60)}s")

    stats_file = output_excel.replace(".xlsx", "_request_stats.json")
    stats = tracker.save(stats_file)
    print(f"\n--- Request Stats ---")
    print(f"Total: {stats['total_requests']} req | {stats['total_req_per_min']} req/min")

    return {
        "total": len(raw_users),
        "success": len(results),
        "failed": len(failed),
        "failed_urls": failed
    }

if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else None
    end_label = end if end is not None else "all"

    run(
        output_excel=f"users_{start}_{end_label}.xlsx",
        start_page=start,
        end_page=end
    )