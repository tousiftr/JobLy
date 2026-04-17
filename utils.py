import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import time
import logging
from collections import Counter
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


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "with", "you",
    "your", "our", "we", "will", "this", "they", "their", "who", "what", "when", "where",
    "how", "about", "into", "more", "least", "plus", "role", "team", "experience", "work",
}

ROLE_SKILL_MAP = {
    "Data Analyst": [
        "sql", "python", "tableau", "power bi", "dashboard", "a b testing", "statistics",
        "excel", "stakeholder", "kpi", "data visualization", "ga4", "gtm",
    ],
    "Analytics Engineer": [
        "dbt", "sql", "python", "snowflake", "bigquery", "redshift", "etl", "elt",
        "dimensional modeling", "airflow", "git", "data modeling", "tests", "ci cd",
    ],
    "Data Engineer": [
        "python", "spark", "sql", "airflow", "kafka", "aws", "gcp", "azure", "databricks",
        "batch", "streaming", "orchestration", "data lake", "warehouse", "terraform",
    ],
}

CORE_PHRASES = {
    "visa sponsorship", "work permit", "relocation support", "remote", "global remote",
    "analytics engineer", "data analyst", "data engineer", "business intelligence", "power bi",
    "tableau", "dbt", "snowflake", "bigquery", "redshift", "airflow", "ga4", "gtm",
    "stakeholder management", "data modeling", "machine learning", "a b testing",
}


def tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+#\.]{1,}", text)]


def extract_keywords(text: str, top_n: int = 30) -> list[str]:
    tk = [t for t in tokens(text) if t not in STOPWORDS and len(t) > 2]
    counts = Counter(tk)

    phrase_hits = []
    lower = text.lower()
    for phrase in CORE_PHRASES:
        if phrase in lower:
            phrase_hits.append((phrase, lower.count(phrase) + 2))

    for phrase, score in phrase_hits:
        counts[phrase] += score

    return [w for w, _ in counts.most_common(top_n)]


def infer_role_scores(text: str) -> dict[str, int]:
    lower = text.lower()
    scores: dict[str, int] = {}
    for role, skills in ROLE_SKILL_MAP.items():
        score = 0
        for skill in skills:
            if skill in lower:
                score += 2
        if role.lower() in lower:
            score += 4
        scores[role] = score
    return scores


def calculate_ats_match_score(job_text: str, target_role: str, user_skills: list[str] = None) -> tuple[int, str, bool]:
    if user_skills is None:
        user_skills = []

    lower = job_text.lower()
    role_skills = ROLE_SKILL_MAP.get(target_role, [])

    matched_count = sum(1 for skill in role_skills if skill in lower)
    matched_score = matched_count * 15

    role_scores = infer_role_scores(job_text)
    role_fit = role_scores.get(target_role, 0)
    role_bonus = min(role_fit * 3, 25)

    keywords = extract_keywords(job_text, top_n=30)
    rare_keyword_count = sum(1 for kw in keywords if kw in CORE_PHRASES)
    keyword_boost = min(rare_keyword_count * 5, 20)

    raw_score = min(matched_score + role_bonus + keyword_boost, 100)

    if raw_score >= 81:
        category = "Excellent"
    elif raw_score >= 61:
        category = "Good"
    elif raw_score >= 31:
        category = "Fair"
    else:
        category = "Poor"

    is_strong_match = raw_score >= 70

    return raw_score, category, is_strong_match
