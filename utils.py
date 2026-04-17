import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from dateutil import parser as dp

from config import (HEADERS, REQUEST_TIMEOUT, MAX_RETRIES,
                    VISA_KEYWORDS, RELOCATION_KEYWORDS, TARGET_LOCATIONS)

logger = logging.getLogger(__name__)
_NOW = datetime.now(tz=timezone.utc)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def safe_get(url: str, session=None, params: dict = None,
             retries: int = MAX_RETRIES) -> Optional[requests.Response]:
    sess = session or make_session()
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5 + attempt * 3))
                logger.debug("Rate-limited %s — sleeping %ds", url, wait)
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None   # company not found — skip silently
            r.raise_for_status()
            return r
        except requests.exceptions.SSLError:
            return None
        except requests.exceptions.ConnectionError:
            return None
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(1.5 ** attempt)
            else:
                logger.debug("Failed %s: %s", url, e)
    return None


def parse_date(raw) -> Optional[datetime]:
    if not raw:
        return None
    raw = str(raw).strip()
    # Unix milliseconds (Lever)
    if raw.isdigit() and len(raw) == 13:
        return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    if raw.isdigit() and len(raw) == 10:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    # Relative
    m = re.match(r"(\d+)\s+(second|minute|hour|day|week|month)s?\s+ago", raw, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        d = {"second": timedelta(seconds=n), "minute": timedelta(minutes=n),
             "hour": timedelta(hours=n), "day": timedelta(days=n),
             "week": timedelta(weeks=n), "month": timedelta(days=n * 30)}
        return _NOW - d[unit]
    if re.search(r"today|just\s*posted|just\s*now", raw, re.I):
        return _NOW
    if re.search(r"yesterday", raw, re.I):
        return _NOW - timedelta(days=1)
    try:
        dt = dp.parse(raw, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_within_days(raw, max_days: int = 5) -> bool:
    dt = parse_date(raw)
    if dt is None:
        return True
    return (_NOW - dt).days <= max_days


def to_timestamp(raw) -> Optional[float]:
    dt = parse_date(raw)
    return dt.timestamp() if dt else None


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def has_visa(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in VISA_KEYWORDS)


def has_relocation(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in RELOCATION_KEYWORDS)


def location_matches(location: str, description: str = "") -> bool:
    combined = (location + " " + description).lower()
    return any(t in combined for t in TARGET_LOCATIONS)


def role_matches(title: str, roles: list) -> bool:
    return any(r in title.lower() for r in roles)


def humanise(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()
