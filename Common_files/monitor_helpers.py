import glob
import json


def aggregate_request_stats(stats_glob: str) -> dict:
    """
    Reads all request_stats json files matching stats_glob (each produced by
    RequestTracker.save()) and rolls them into one dict for this category.
    """
    total_requests = 0
    total_duration_min = 0.0

    for f in glob.glob(stats_glob):
        with open(f, "r", encoding="utf-8") as fh:
            stats = json.load(fh)
        total_requests += stats.get("total_requests", 0)
        total_duration_min += stats.get("total_duration_min", 0) or 0

    requests_per_min = round(total_requests / total_duration_min, 2) if total_duration_min > 0 else total_requests

    return {
        "requests_total": total_requests,
        "duration_sec": round(total_duration_min * 60, 2),
        "requests_per_min": requests_per_min,
    }


def collect_failed_links(paths_glob: str) -> list:
    links = []
    for f in glob.glob(paths_glob):
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("http"):
                    links.append(line)
    return links


def build_failed_report(failed_links: list, total_scraped: int = 0) -> dict:
    total_failed = len(failed_links)
    total_attempted = total_scraped + total_failed
    failed_pct = round(total_failed / total_attempted * 100, 2) if total_attempted > 0 else 0
    return {
        "total_failed": total_failed,
        "failed_percentage": failed_pct,
        "failed_links": failed_links,
    }