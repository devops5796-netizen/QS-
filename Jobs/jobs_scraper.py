import json
import time
import pandas as pd
from datetime import datetime, timezone, timedelta
import requests as req
from PIL import Image
import io
from Common_files.r2_uploader import upload_buffer
import sys
from Common_files.request_tracker import tracker

API_URL = "https://production-api.qatarsale.com/api/Opportunity/Search"
DETAILS_API_URL = "https://production-api.qatarsale.com/api/Opportunity/GetOpportunityDetails"
BASE_JOB_URL = "https://qatarsale.com/ar/jobs/opportunity"
PAGE_SIZE = 15

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://qatarsale.com/",
    "Origin": "https://qatarsale.com",
}


def get_all_jobs(start_page: int = 0, end_page: int = None) -> list[dict]:
    all_jobs = []

    if end_page is None:
        payload = {
            "currentPage": 0, "pageSize": PAGE_SIZE, "sortBy": 0,
            "workFields": [], "workSpecialities": [], "employmentTypes": [],
            "workplaceTypes": [], "searchTerm": "", "experiences": [],
            "countries": [], "languages": [], "cities": [], "degrees": [],
            "skills": [], "userId": None, "isFavorite": False, "yearsOfExperience": []
        }
        tracker.log_request(source="jobs_search")
        r = req.post(API_URL, json=payload, headers=HEADERS, timeout=30)
        data = r.json()
        end_page = data.get("pagesCount", 1) - 1
        print(f"  Detected {end_page + 1} pages | {data.get('count', 0)} total jobs")

    for page in range(start_page, end_page + 1):
        payload = {
            "currentPage": page, "pageSize": PAGE_SIZE, "sortBy": 0,
            "workFields": [], "workSpecialities": [], "employmentTypes": [],
            "workplaceTypes": [], "searchTerm": "", "experiences": [],
            "countries": [], "languages": [], "cities": [], "degrees": [],
            "skills": [], "userId": None, "isFavorite": False, "yearsOfExperience": []
        }
        try:
            tracker.log_request(source="jobs_search")
            r = req.post(API_URL, json=payload, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            jobs = data.get("list", [])
            if not jobs:
                break
            print(f"  Page {page}: {len(jobs)} jobs")
            all_jobs.extend(jobs)
            time.sleep(1)
        except Exception as e:
            print(f"  [ERROR] Page {page}: {e}")
            break

    return all_jobs


def parse_job_details(uri: str) -> dict:
    if not uri:
        return {}

    url = f"{BASE_JOB_URL}/{uri}"

    try:
        tracker.log_request(source="jobs_details")
        response = req.get(
            DETAILS_API_URL,
            params={"uri": uri, "forEdit": "false"},
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("status") or "data" not in result:
            return {}

        job = result["data"]
        if not job.get("id"):
            return {}

        row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
               for k, v in job.items()}
        row["job_url"] = url
        return row

    except Exception as e:
        print(f"  [ERROR] {uri}: {e}")
        return {}


def download_and_upload_image(img_url: str, job_uri: str) -> str:
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
            filename = f"{job_uri}.webp"
            r2_key = upload_buffer(
                output_buffer,
                filename=filename,
                folder_name="qatarsale",
                category="jobs",
                file_type="images",
                content_type="image/webp",
                dt=today
            )
            return r2_key or ""
        return ""
    except Exception as e:
        print(f"  [ERROR] Image upload failed for {job_uri}: {e}")
        return ""


def filter_yesterday_links(jobs: list[dict]) -> dict:
    df = pd.DataFrame(jobs)

    if "createdAt" not in df.columns:
        print("⚠️ No createdAt column found, using all jobs")
        return {
            "total": len(df),
            "yesterday": len(df),
            "filtered_jobs": jobs
        }

    df["date_parsed"] = pd.to_datetime(df["createdAt"], format="ISO8601", utc=True)
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    mask = df["date_parsed"].dt.date == yesterday
    df_yesterday = df[mask].drop(columns=["date_parsed"])

    print(f"  Total jobs:     {len(df)}")
    print(f"  Yesterday jobs: {len(df_yesterday)}")

    filtered_jobs = df_yesterday.to_dict('records')

    return {
        "total": len(df),
        "yesterday": len(df_yesterday),
        "filtered_jobs": filtered_jobs
    }


def run(output_excel: str = "jobs.xlsx", start_page: int = 0, end_page: int = None) -> dict:
    print("=" * 50)
    print("QatarSale Jobs Scraper")
    print("=" * 50)

    start_time = time.time()

    print("\nSTEP 1: Fetching jobs from API...")
    raw_jobs = get_all_jobs(start_page=start_page, end_page=end_page)
    print(f"Total jobs fetched: {len(raw_jobs)}")

    if not raw_jobs:
        print("No jobs found!")
        return {"total": 0, "success": 0, "failed": 0, "failed_urls": []}

    print("\nSTEP 1.5: Filtering jobs created yesterday...")
    filter_result = filter_yesterday_links(raw_jobs)
    raw_jobs = filter_result["filtered_jobs"]
    print(f"  Total jobs:     {filter_result['total']}")
    print(f"  Yesterday jobs: {filter_result['yesterday']}")

    if not raw_jobs:
        print("No jobs from yesterday!")
        return {"total": filter_result["total"], "success": 0, "failed": 0, "failed_urls": []}
    
    print("\nSTEP 2: Scraping job details...")
    results = []
    failed = []
    uri_map = {job.get("uri", ""): job for job in raw_jobs}

    for i, job in enumerate(raw_jobs, 1):
        uri = job.get("uri", "")

        print(f"  [{i}/{len(raw_jobs)}] uri={uri}")

        data = parse_job_details(uri) if uri else {}

        if data:
            img_url = job.get("companyPicture", "")
            r2_image = download_and_upload_image(img_url, uri)
            data["image_r2_key"] = r2_image
            results.append(data)
            print(f"    ✓ {data.get('jobTitleName', 'N/A')} | {data.get('companyName', 'N/A')}")
        else:
            failed.append(uri)
            print(f"    ✗ Failed")

        time.sleep(0.5)

    # Retry failed
    if failed:
        print(f"\nRetrying {len(failed)} failed URIs...")
        still_failed = []
        for uri in failed:
            data = parse_job_details(uri)
            if data:
                job = uri_map.get(uri, {})
                img_url = job.get("companyPicture", "")
                r2_image = download_and_upload_image(img_url, uri)
                data["image_r2_key"] = r2_image
                results.append(data)
                print(f"  ✓ {uri}")
            else:
                still_failed.append(uri)
                print(f"  ✗ {uri}")
        failed = still_failed

    print(f"\nSTEP 3: Saving {len(results)} jobs to Excel...")
    df = pd.DataFrame(results)
    df.to_excel(output_excel, index=False, sheet_name="jobs")
    print(f"Saved: {output_excel}")

    if failed:
        with open("failed_urls.txt", "w", encoding="utf-8") as f:
            f.write(f"Total Failed URIs: {len(failed)}\n\n")
            for u in failed:
                f.write(f"{BASE_JOB_URL}/{u}\n")

    elapsed = time.time() - start_time
    print(f"\nDONE: {len(results)} jobs | {len(failed)} failed | {int(elapsed//60)}m {int(elapsed%60)}s")

    stats_file = output_excel.replace(".xlsx", "_request_stats.json")
    stats = tracker.save(stats_file)
    print(f"\n--- Request Stats ---")
    print(f"Total: {stats['total_requests']} req | {stats['total_req_per_min']} req/min")

    return {
        "total": filter_result["total"],
        "success": len(results),
        "failed": len(failed),
        "failed_urls": failed
    }



if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end   = int(sys.argv[2]) if len(sys.argv) > 2 else None
    end_label = end if end is not None else "all"
    run(
        output_excel=f"jobs_{start}_{end_label}.xlsx",
        start_page=start,
        end_page=end
    )