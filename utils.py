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
    return [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+#\.]{1,}", str(text or ""))]


def extract_keywords(text: str, top_n: int = 30) -> list[str]:
    text = str(text or "")
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


TITLE_ROLE_TOKENS = {
    "Data Analyst": ["data analyst", "business analyst", "bi analyst", "analytics analyst", "product analyst", "marketing analyst"],
    "Analytics Engineer": ["analytics engineer", "bi engineer", "analytics developer", "data modeler"],
    "Data Engineer": ["data engineer", "etl engineer", "data platform", "data infrastructure", "data pipeline"],
}


def calculate_ats_match_score(
    job_text: str,
    target_role: str,
    user_skills: list[str] = None,
    job_title: str = "",
) -> tuple[int, str, bool]:
    if user_skills is None:
        user_skills = []

    lower = str(job_text or "").lower()
    title_lower = str(job_title or "").lower()
    role_skills = ROLE_SKILL_MAP.get(target_role, [])

    # 1. Title match — strongest signal (up to 40 pts)
    title_score = 0
    role_title_tokens = TITLE_ROLE_TOKENS.get(target_role, [target_role.lower()])
    if any(phrase in title_lower for phrase in role_title_tokens):
        title_score = 40
    elif target_role.lower() in title_lower:
        title_score = 35
    else:
        role_words = target_role.lower().split()
        word_hits = sum(1 for w in role_words if w in title_lower and len(w) > 2)
        if word_hits >= 2:
            title_score = 20
        elif word_hits == 1:
            title_score = 8

    # 2. Role-skill coverage in description (up to 30 pts)
    matched_count = sum(1 for skill in role_skills if skill in lower)
    skill_score = min(matched_count * 4, 30)
    skill_coverage = matched_count / max(len(role_skills), 1)

    # 3. User skills bonus (up to 15 pts)
    user_skill_matches = sum(1 for s in user_skills if s.strip().lower() in lower) if user_skills else 0
    user_bonus = min(user_skill_matches * 3, 15)

    # 4. Core phrase / rare keyword boost (up to 15 pts)
    keywords = extract_keywords(job_text, top_n=30)
    rare_keyword_count = sum(1 for kw in keywords if kw in CORE_PHRASES)
    keyword_boost = min(rare_keyword_count * 2, 15)

    raw_score = min(title_score + skill_score + user_bonus + keyword_boost, 100)

    # Penalty: title completely unrelated AND weak skill coverage
    if title_score == 0 and skill_coverage < 0.2:
        raw_score = int(raw_score * 0.5)

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
