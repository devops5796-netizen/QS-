import json
import random
import time

import pandas as pd
import requests
from Common_files.request_tracker import tracker

BASE_URL = "https://qatarsale.com"
API_BASE = "https://production-api.qatarsale.com/api"
BASE_PRODUCT_URL = "https://qatarsale.com/ar/product"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# -------------------------
# SHOWROOM LIST
# -------------------------
def get_showroom_links(category: str = "cars_for_sale") -> list[str]:
    url = f"{API_BASE}/Showrooms/GetAllShowrooms"
    payload = {"name": "", "categoryUri": category}

    print(f"Fetching showroom list for: {category}")

    resp = SESSION.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    links = []
    for item in data:
        uri = item.get("uri")
        if not uri:
            continue
        links.append(f"{BASE_URL}/ar/showroom/{uri}/{category}")

    links = list(dict.fromkeys(links))
    print(f"Found {len(links)} showrooms")
    return links


def _showroom_uri_and_category(showroom_url: str) -> tuple[str, str]:
    tail = showroom_url.split("/ar/showroom/")[-1].strip("/")
    parts = tail.split("/")
    uri = parts[0] if parts else ""
    category = parts[1] if len(parts) > 1 else "cars_for_sale"
    return uri, category


# -------------------------
# SHOWROOM DETAILS
# -------------------------
def _parse_contact_info(contact_infos: list) -> tuple[list, list]:
    phones = []
    whatsapps = []

    for c in contact_infos:
        raw = c.get("contactInfo", "")
        try:
            info = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(info, list):
            info = info[0] if info and isinstance(info[0], dict) else {}

        if not isinstance(info, dict):
            print(f"  [WARN] Unexpected contactInfo shape, skipping: {raw!r}")
            continue

        phone = info.get("phone", "")
        if not phone:
            continue

        type_text = (c.get("typeAsText") or "").lower()
        if "whatsapp" in type_text:
            whatsapps.append(phone)
        else:
            phones.append(phone)

    return phones, whatsapps


def parse_showroom_details(showroom_url: str) -> dict:
    showroom_uri, _ = _showroom_uri_and_category(showroom_url)
    url = f"{API_BASE}/Showrooms/GetShowroomDetails"

    try:
        resp = SESSION.get(url, params={"showroomUri": showroom_uri}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        tracker.log_request(source="showroom_details", success=True)
    except Exception as e:
        tracker.log_request(source="showroom_details", success=False)
        print(f"  [ERROR] Failed to fetch showroom details: {showroom_url} -> {e}")
        return {
            "url": showroom_url,
            "name": "",
            "cover_image": "",
            "phones": "[]",
            "whatsapps": "[]",
            "posts_count": "",
            "views_count": "",
        }

    phones, whatsapps = _parse_contact_info(data.get("contactInfos", []))

    return {
        "url": showroom_url,
        "name": (data.get("name") or "").strip(),
        "cover_image": data.get("coverImage", ""),
        "phones": str(phones),
        "whatsapps": str(whatsapps),
        "posts_count": data.get("postCount", ""),
        "views_count": data.get("viewCount", ""),
    }


# -------------------------
# PRODUCTS (ID-LEVEL ONLY)
# -------------------------
def _get_products_page(showroom_uri: str, category: str, page: int, page_size: int = 36) -> dict:
    url = f"{API_BASE}/v2/Products"
    page_path = f"/ar/showroom/{showroom_uri}/{category}"
    if page > 0:
        page_path += f"?page={page}"

    payload = {
        "url": page_path,
        "includeFavs": False,
        "pageSize": page_size,
    }
    try:
        resp = SESSION.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        tracker.log_request(source="showroom_products", success=True)
        return resp.json()
    except Exception:
        tracker.log_request(source="showroom_products", success=False)
        raise


def _extract_product_rows(products: list, source_url: str) -> list[dict]:
    rows = []
    for p in products:
        pid = p.get("id")
        uri = p.get("uri", "")
        if pid is None or not uri:
            continue
        rows.append({
            "id": pid,
            "uri": uri,
            "product_url": f"{BASE_PRODUCT_URL}/{uri}",
            "startDate": p.get("startDate", ""),
            "title": p.get("title", ""),
            "startingPrice": p.get("startingPrice", ""),
            "showroomUri": p.get("showroomUri", ""),
            "categoryUri": p.get("categoryUri", ""),
            "isSold": p.get("isSold", ""),
            "isExpired": p.get("isExpired", ""),
            "source_url": source_url,
        })
    return rows


# -------------------------
# MAIN SCRAPER
# -------------------------
def scrape_showroom(showroom_url: str):
    print(f"\nScraping: {showroom_url}")

    showroom_uri, category = _showroom_uri_and_category(showroom_url)

    details = parse_showroom_details(showroom_url)

    try:
        first_page = _get_products_page(showroom_uri, category, page=0)
    except Exception as e:
        print(f"  [ERROR] Failed to fetch products page 0: {e}")
        return details, pd.DataFrame()

    pages_count = first_page.get("pagesCount", 1) or 1
    total_count = first_page.get("totalCount", "")
    print(f"Pages: {pages_count} (totalCount: {total_count})")

    all_rows = _extract_product_rows(first_page.get("list", []), showroom_url)
    print(f"  ✓ Page 0: {len(all_rows)} products")

    for page in range(1, pages_count):
        for attempt in range(3):
            try:
                data = _get_products_page(showroom_uri, category, page=page)
                rows = _extract_product_rows(data.get("list", []), showroom_url)
                all_rows.extend(rows)
                print(f"  ✓ Page {page}: {len(rows)} products")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  Page {page} attempt {attempt + 1} failed, retrying...")
                    time.sleep(3)
                else:
                    print(f"  [ERROR] Page {page} failed permanently: {e}")

        if page < pages_count - 1:
            time.sleep(random.uniform(1.0, 2.0))

    all_products_df = pd.DataFrame(all_rows)

    if "product_url" in all_products_df.columns:
        all_products_df = all_products_df.drop_duplicates(subset=["product_url"], keep="first")

    return details, all_products_df