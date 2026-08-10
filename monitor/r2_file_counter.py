import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("monitor")

# Subfolders immediately under a scraper's date partition (see Common_files/r2_uploader.build_r2_key).
_DATA_SUBFOLDERS = frozenset({"excel", "images", "summary", "csv", "json"})


def count_r2_objects(client, bucket: str, prefix: str) -> int:
    """
    Count all objects under *prefix* using paginated list_objects_v2.

    Skips zero-byte folder marker keys ending with '/'.
    """
    normalized = prefix.strip("/")
    list_prefix = f"{normalized}/" if normalized else ""

    count = 0
    paginator = client.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                count += 1
    except Exception as exc:
        log.warning(f"R2 object count failed for prefix {list_prefix!r}: {exc}")
        return 0

    return count


def sum_r2_object_sizes(client, bucket: str, prefix: str) -> int:
    """Sum byte sizes of all objects under *prefix* (skips folder markers)."""
    normalized = prefix.strip("/")
    list_prefix = f"{normalized}/" if normalized else ""

    total = 0
    paginator = client.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                total += obj.get("Size", 0)
    except Exception as exc:
        log.warning(f"R2 size sum failed for prefix {list_prefix!r}: {exc}")
        return 0

    return total


def daily_partition_prefix(r2_base: str, dt: datetime) -> str:
    """R2 prefix for one date partition: {base}/year=YYYY/month=MM/day=DD/"""
    base = r2_base.strip("/")
    return f"{base}/year={dt.year}/month={dt.month:02d}/day={dt.day:02d}/"


def scraper_daily_prefix(r2_base: str, category: Optional[str], dt: datetime) -> str:
    """All objects for one scraper on a given date (excel, images, summary, etc.)."""
    prefix = daily_partition_prefix(r2_base, dt)
    if category:
        return f"{prefix}{category.strip('/')}/"
    return prefix


def _segments_after_date_partition(key: str, r2_base: str) -> Optional[List[str]]:
    """
    Return path segments after year=/month=/day= for keys like:
    qatarsale/year=2026/month=08/day=09/cars_for_sale/excel/file.xlsx
    """
    base = r2_base.strip("/")
    marker = f"{base}/year="
    if not key.startswith(marker):
        return None

    rest = key[len(base) + 1 :]
    parts = rest.split("/")
    if len(parts) < 4:
        return None
    if not (
        parts[0].startswith("year=")
        and parts[1].startswith("month=")
        and parts[2].startswith("day=")
    ):
        return None
    return parts[3:]


def category_path_from_key(key: str, r2_base: str) -> Optional[str]:
    """
    Extract scraper category from a partitioned R2 key.
    Stops before the first known data subfolder (excel, images, summary, ...).
    """
    segments = _segments_after_date_partition(key, r2_base)
    if not segments:
        return None

    for idx, segment in enumerate(segments):
        if segment in _DATA_SUBFOLDERS:
            if idx == 0:
                return None
            return "/".join(segments[:idx])

    return None


def _match_scraper_for_category(
    category_path: str,
    category_to_scraper: Dict[str, str],
) -> Optional[str]:
    """Map an R2 category path to a configured scraper name."""
    if category_path in category_to_scraper:
        return category_to_scraper[category_path]

    # Longest-prefix match for nested category paths.
    best_match = None
    best_len = -1
    for known_category, scraper_name in category_to_scraper.items():
        if category_path == known_category or category_path.startswith(known_category + "/"):
            if len(known_category) > best_len:
                best_len = len(known_category)
                best_match = scraper_name
    return best_match


def _aggregate_sizes_under_prefix(
    client,
    bucket: str,
    list_prefix: str,
    r2_base: str,
    category_to_scraper: Dict[str, str],
) -> Dict[str, int]:
    """Single-pass size aggregation keyed by scraper name."""
    sizes: Dict[str, int] = defaultdict(int)
    paginator = client.get_paginator("list_objects_v2")

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue

                category_path = category_path_from_key(key, r2_base)
                if not category_path:
                    continue

                scraper_name = _match_scraper_for_category(category_path, category_to_scraper)
                if scraper_name:
                    sizes[scraper_name] += obj.get("Size", 0)
    except Exception as exc:
        log.warning(f"R2 size aggregation failed for prefix {list_prefix!r}: {exc}")

    return dict(sizes)


def collect_scraper_r2_sizes(
    client,
    bucket: str,
    r2_prefix: str,
    scraper_configs: List[dict],
    target_date: datetime,
) -> Tuple[List[dict], int, int, int]:
    """
    Compute per-scraper R2 sizes and site totals.

    Returns:
        scrapers_list: [{scraper, r2_size_bytes, r2_daily_size}, ...]
        total_r2_size_bytes: entire site prefix (all objects under r2_prefix)
        total_r2_daily_size: sum of per-scraper daily sizes for target_date
        total_r2_files: object count under site prefix (existing metric)
    """
    from inspect_r2_schema import r2_base_prefix

    r2_base = r2_prefix.strip("/")
    category_to_scraper: Dict[str, str] = {}

    for scraper_config in scraper_configs:
        scraper_name = scraper_config.get("name")
        if not scraper_name:
            continue

        _, category = r2_base_prefix(scraper_config.get("r2_path", ""))
        if category:
            category_to_scraper[category] = scraper_name

    daily_prefix = daily_partition_prefix(r2_base, target_date)
    daily_sizes = _aggregate_sizes_under_prefix(
        client, bucket, daily_prefix, r2_base, category_to_scraper
    )
    total_sizes = _aggregate_sizes_under_prefix(
        client, bucket, f"{r2_base}/", r2_base, category_to_scraper
    )

    scrapers_list = []
    total_r2_daily_size = 0

    for scraper_config in scraper_configs:
        scraper_name = scraper_config.get("name")
        if not scraper_name:
            continue

        r2_daily_size = daily_sizes.get(scraper_name, 0)
        r2_size_bytes = total_sizes.get(scraper_name, 0)
        total_r2_daily_size += r2_daily_size

        scrapers_list.append(
            {
                "scraper": scraper_name,
                "r2_size_bytes": r2_size_bytes,
                "r2_daily_size": r2_daily_size,
            }
        )

    scrapers_list.sort(key=lambda item: item["r2_size_bytes"], reverse=True)

    total_r2_size_bytes = sum_r2_object_sizes(client, bucket, r2_base)
    total_r2_files = count_site_r2_files(client, bucket, r2_prefix)

    log.info(
        f"R2 sizes ({r2_base}): site={total_r2_size_bytes} bytes, "
        f"daily={total_r2_daily_size} bytes, {len(scrapers_list)} scraper(s)"
    )

    return scrapers_list, total_r2_size_bytes, total_r2_daily_size, total_r2_files


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Total objects under the site's data prefix (all scrapers + monitor artifacts)."""
    prefix = r2_prefix.strip("/")
    if not prefix:
        return 0
    total = count_r2_objects(client, bucket, prefix)
    log.info(f"Site R2 inventory ({prefix}): {total} object(s)")
    return total
