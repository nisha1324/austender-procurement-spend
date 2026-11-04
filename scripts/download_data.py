"""Download one financial year of AusTender contract notices from the official OCDS API.

Source: AusTender OCDS API, published by the Australian Government Department of Finance
(https://api.tenders.gov.au, docs: https://github.com/austender/austender-ocds-api).
Licence: CC BY 3.0 AU (stated in every API response, and checked by this script).

The API returns contract notices (and amendments to them) published in a date window, 100 at
a time, with a cursor link to the next page. This script asks for one Canberra calendar day
at a time and saves each day's releases to `data/raw/YYYY-MM-DD.json.gz`. Days already saved
are skipped, so an interrupted run can be restarted. No key or sign-up is needed.

    python -m scripts.download_data                  # FY2024-25 (1 Jul 2024 - 30 Jun 2025)
    python -m scripts.download_data --fy 2024        # same thing
    python -m scripts.download_data --start 2025-07-01 --end 2025-07-02
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.tenders.gov.au/ocds/findByDates/contractPublished/{start}/{end}"
EXPECTED_LICENCE = "https://creativecommons.org/licenses/by/3.0/au/"
CANBERRA = ZoneInfo("Australia/Sydney")  # Canberra keeps Sydney time
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
USER_AGENT = "austender-procurement-spend (github.com/nisha1324; study project)"
MAX_PAGES_PER_DAY = 500


def day_window_utc(day: dt.date) -> tuple[str, str]:
    """Canberra midnight to the next Canberra midnight, as UTC strings the API accepts.

    Daylight saving moves the UTC offset between +10 and +11, so this is worked out per day.
    """
    start = dt.datetime.combine(day, dt.time(0), CANBERRA).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0), CANBERRA).astimezone(
        dt.timezone.utc
    )
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


class NoRecords(Exception):
    """The API answers HTTP 400, errorCode 100, for a window with no notices (e.g. a Sunday)."""


def get_json(url: str, retries: int = 5) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:  # a client error won't change on retry
                body = exc.read().decode("utf-8", "replace")
                try:
                    if json.loads(body).get("errorCode") == 100:
                        raise NoRecords(body) from exc
                except json.JSONDecodeError:
                    pass
                raise
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt * 3
            print(f"    retry {attempt + 1} after {exc!r}, waiting {wait}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt * 3
            print(f"    retry {attempt + 1} after {exc!r}, waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch_day(day: dt.date, pause: float = 0.25) -> dict:
    """All releases published on one Canberra day, following the cursor to the end."""
    start, end = day_window_utc(day)
    url = API.format(start=start, end=end)
    releases: list[dict] = []
    seen_urls: set[str] = set()
    licence = None
    for _ in range(MAX_PAGES_PER_DAY):
        if url in seen_urls:  # a cursor that points back at itself ends the day
            break
        seen_urls.add(url)
        try:
            page = get_json(url)
        except NoRecords:
            if releases:  # "no records" mid-way through a day would mean lost pages
                raise
            licence = EXPECTED_LICENCE  # no page body to read it from; checked on every other day
            break
        licence = page.get("license")
        if licence != EXPECTED_LICENCE:
            raise RuntimeError(f"licence changed: {licence!r} (expected {EXPECTED_LICENCE})")
        batch = page.get("releases", [])
        releases.extend(batch)
        url = (page.get("links") or {}).get("next")
        if not batch or not url:
            break
        time.sleep(pause)
    else:
        raise RuntimeError(f"{day}: more than {MAX_PAGES_PER_DAY} pages, stopping")
    return {
        "day": day.isoformat(),
        "window_utc": [start, end],
        "license": licence,
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages": len(seen_urls),
        "releases": releases,
    }


def save_day(payload: dict, raw_dir: Path = RAW_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"{payload['day']}.json.gz"
    tmp = out.with_suffix(".gz.part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    tmp.replace(out)  # only complete days get the final name
    return out


def days(start: dt.date, end: dt.date):
    d = start
    while d < end:
        yield d
        d += dt.timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fy", type=int, default=2024, help="financial year starting 1 July of this year")
    ap.add_argument("--start", type=dt.date.fromisoformat, help="first day (overrides --fy)")
    ap.add_argument("--end", type=dt.date.fromisoformat, help="day after the last day")
    ap.add_argument("--refresh", action="store_true", help="download days already saved again")
    ap.add_argument("--workers", type=int, default=4, help="days fetched at once (keep it small)")
    args = ap.parse_args()

    start = args.start or dt.date(args.fy, 7, 1)
    end = args.end or dt.date(args.fy + 1, 7, 1)
    todo = [d for d in days(start, end)
            if args.refresh or not (RAW_DIR / f"{d.isoformat()}.json.gz").exists()]

    def one(day: dt.date) -> int:
        payload = fetch_day(day)
        save_day(payload)
        print(f"{day}: {len(payload['releases']):5d} releases, {payload['pages']} pages", flush=True)
        return len(payload["releases"])

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as pool:
        total = sum(pool.map(one, todo))
    print(f"done: {total} releases in {len(todo)} days downloaded this run into {RAW_DIR}")


if __name__ == "__main__":
    main()
