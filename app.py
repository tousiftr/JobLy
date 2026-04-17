import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jobly.db"

app = Flask(__name__)

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

ATS_BOARDS = [
    "jobs.ashbyhq.com", "boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co",
    "apply.workable.com", "jobs.smartrecruiters.com", "jobs.jobvite.com", "myworkdayjobs.com",
    "careers.recruitee.com", "jobs.personio.com", "bamboohr.com/careers",
]

TITLES = [
    "analytics engineer", "data analyst", "business intelligence analyst", "bi analyst",
    "bi engineer", "product analyst", "growth analyst", "marketing analyst", "web analyst",
    "digital analytics engineer", "senior data analyst", "senior analytics engineer",
]

SCRAPE_ROLE_TERMS = {
    "analytics engineer", "data analyst", "business intelligence analyst", "bi analyst",
    "bi engineer", "product analyst", "growth analyst", "marketing analyst", "web analyst",
    "data engineer", "analytics", "reporting analyst",
}


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                job_url TEXT,
                status TEXT DEFAULT 'Saved',
                remote INTEGER DEFAULT 0,
                visa_sponsorship INTEGER DEFAULT 0,
                notes TEXT,
                target_role TEXT,
                top_keywords TEXT,
                matched_skills TEXT,
                missing_skills TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                job_url TEXT,
                source TEXT,
                description TEXT,
                remote INTEGER DEFAULT 0,
                visa_sponsorship INTEGER DEFAULT 0,
                relocation_support INTEGER DEFAULT 0,
                ats_score REAL DEFAULT NULL,
                ats_category TEXT,
                role_match TEXT,
                matched_skills TEXT,
                top_keywords TEXT,
                published_at TEXT,
                scraped_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_tracked INTEGER DEFAULT 0
            )
            """
        )
        # Create indexes for common queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_jobs_visa_remote
            ON raw_jobs(visa_sponsorship, remote)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_jobs_ats_score
            ON raw_jobs(ats_score DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_jobs_published
            ON raw_jobs(published_at DESC)
            """
        )


init_db()


def normalize_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def fetch_job_text(url: str) -> str:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "JobLy/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return normalize_text(text)


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


def calculate_ats_match_score(job_text: str, target_role: str, user_skills: list[str]) -> tuple[int, str, bool]:
    """
    Calculate ATS match score (0-100) based on job-to-profile fit.

    Returns:
        (score: int, category: str, is_strong_match: bool)
        category: "Poor", "Fair", "Good", "Excellent"
        is_strong_match: True if score >= 70
    """
    lower = job_text.lower()
    role_skills = ROLE_SKILL_MAP.get(target_role, [])

    # Count matched skills (each worth 15 points)
    matched_count = sum(1 for skill in role_skills if skill in lower)
    matched_score = matched_count * 15

    # Role fit bonus (from infer_role_scores)
    role_scores = infer_role_scores(job_text)
    role_fit = role_scores.get(target_role, 0)
    role_bonus = min(role_fit * 3, 25)  # Cap at 25 points

    # Keyword rarity boost - count extracted keywords that are in CORE_PHRASES
    keywords = extract_keywords(job_text, top_n=30)
    rare_keyword_count = sum(1 for kw in keywords if kw in CORE_PHRASES)
    keyword_boost = min(rare_keyword_count * 5, 20)  # Cap at 20 points

    # Calculate raw score, cap at 100
    raw_score = min(matched_score + role_bonus + keyword_boost, 100)

    # Categorize
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


def tailor_resume(job_text: str, role: str, user_skills: list[str]) -> dict[str, Any]:
    lower = job_text.lower()
    role_skills = ROLE_SKILL_MAP.get(role, [])
    matched = sorted({s for s in role_skills if s in lower})
    missing = sorted({s for s in role_skills if s not in lower and s not in [u.lower() for u in user_skills]})

    action_lines = [
        "Place the strongest matching keywords in your Professional Summary and Skills section.",
        "Mirror wording from the job post exactly for tools (e.g., 'Power BI' vs 'powerbi').",
        "Quantify impact with metrics in every recent bullet (%, $, time saved, SLA).",
    ]

    role_template = {
        "Data Analyst": [
            "Built KPI dashboards in Tableau/Power BI used by leadership to drive weekly decisions.",
            "Automated SQL/Python reporting workflows, reducing manual reporting effort by XX%.",
        ],
        "Analytics Engineer": [
            "Developed dbt models and tests to improve warehouse data reliability and trust.",
            "Created semantic data layers enabling self-serve analytics across business teams.",
        ],
        "Data Engineer": [
            "Designed scalable ELT pipelines with orchestration and monitoring for freshness SLA.",
            "Optimized warehouse processing cost/performance across high-volume datasets.",
        ],
    }

    bullets = role_template.get(role, [])
    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "suggested_bullets": bullets,
        "ats_actions": action_lines,
    }


def bool_from_text(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(w in lower for w in words)


def matches_target_title(title: str) -> bool:
    t = (title or "").lower()
    return any(term in t for term in SCRAPE_ROLE_TERMS)


def source_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc
        return host.replace("www.", "") if host else "unknown"
    except Exception:
        return "unknown"


def fetch_remotive_jobs(limit: int = 120) -> list[dict[str, Any]]:
    resp = requests.get("https://remotive.com/api/remote-jobs", timeout=20, headers={"User-Agent": "JobLy/1.0"})
    resp.raise_for_status()
    data = resp.json().get("jobs", [])
    jobs: list[dict[str, Any]] = []
    for row in data:
        title = normalize_text(row.get("title", ""))
        if not matches_target_title(title):
            continue
        description = normalize_text(BeautifulSoup(row.get("description", ""), "lxml").get_text(" ", strip=True))
        company = normalize_text(row.get("company_name", ""))
        location = normalize_text(row.get("candidate_required_location", "Remote"))
        url = row.get("url") or row.get("job_url") or ""
        combined_text = f"{title} {description}"
        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "job_url": url,
            "source": source_from_url(url) if url else "remotive.com",
            "remote": bool_from_text(f"{location} {combined_text}", ["remote", "work from anywhere", "worldwide", "global"]),
            "visa_sponsorship": bool_from_text(combined_text, ["visa sponsorship", "work permit", "sponsor"]),
            "relocation_support": bool_from_text(combined_text, ["relocation", "relocation support", "relocation assistance"]),
            "published_at": row.get("publication_date", ""),
            "tags": row.get("tags", []),
        })
        if len(jobs) >= limit:
            break
    return jobs


def fetch_arbeitnow_jobs(limit: int = 120) -> list[dict[str, Any]]:
    resp = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=20, headers={"User-Agent": "JobLy/1.0"})
    resp.raise_for_status()
    data = resp.json().get("data", [])
    jobs: list[dict[str, Any]] = []
    for row in data:
        title = normalize_text(row.get("title", ""))
        if not matches_target_title(title):
            continue
        description = normalize_text(BeautifulSoup(row.get("description", ""), "lxml").get_text(" ", strip=True))
        company = normalize_text(row.get("company_name", ""))
        location = normalize_text(row.get("location", ""))
        url = row.get("url", "")
        combined_text = f"{title} {description}"
        jobs.append({
            "title": title,
            "company": company,
            "location": location or "Not specified",
            "job_url": url,
            "source": source_from_url(url) if url else "arbeitnow.com",
            "remote": bool_from_text(f"{location} {combined_text}", ["remote", "work from anywhere", "worldwide", "global"]),
            "visa_sponsorship": bool_from_text(combined_text, ["visa sponsorship", "work permit", "sponsor"]),
            "relocation_support": bool_from_text(combined_text, ["relocation", "relocation support", "relocation assistance"]),
            "published_at": row.get("created_at", ""),
            "tags": row.get("tags", []),
        })
        if len(jobs) >= limit:
            break
    return jobs


@app.get("/")
def index() -> Response:
    return Response(HTML, mimetype="text/html")


@app.post("/api/analyze")
def api_analyze() -> Any:
    payload = request.get_json(silent=True) or {}
    job_text = normalize_text(payload.get("job_text", ""))
    job_url = normalize_text(payload.get("job_url", ""))
    role = payload.get("target_role", "Data Analyst")
    user_skills_raw = payload.get("user_skills", "")
    user_skills = [s.strip() for s in str(user_skills_raw).split(",") if s.strip()]

    if not job_text and job_url:
        try:
            job_text = fetch_job_text(job_url)
        except Exception as exc:
            return jsonify({"error": f"Could not fetch URL content: {exc}"}), 400

    if not job_text:
        return jsonify({"error": "Please provide a job description or job URL."}), 400

    kw = extract_keywords(job_text)
    role_scores = infer_role_scores(job_text)
    tailored = tailor_resume(job_text, role, user_skills)

    # Calculate ATS match score
    ats_score, ats_category, is_strong_match = calculate_ats_match_score(job_text, role, user_skills)

    result = {
        "ats_score": ats_score,
        "ats_category": ats_category,
        "is_strong_match": is_strong_match,
        "keywords": kw,
        "role_scores": role_scores,
        "top_role": max(role_scores, key=role_scores.get),
        "requirements": [k for k in kw if k in {
            "sql", "python", "dbt", "tableau", "power bi", "snowflake", "bigquery",
            "airflow", "spark", "aws", "gcp", "azure", "ga4", "gtm"
        }],
        "remote_status": "Yes" if bool_from_text(job_text, ["remote", "global remote", "work from anywhere"]) else ("No" if bool_from_text(job_text, ["office", "on-site", "onsite"]) else "Not mentioned"),
        "visa_sponsorship_status": "Yes" if bool_from_text(job_text, ["visa sponsorship", "work permit", "sponsor"]) else ("No" if bool_from_text(job_text, ["no visa", "visa not provided"]) else "Not mentioned"),
        "relocation_support": "Yes" if bool_from_text(job_text, ["relocation", "relocation support", "relocation assistance"]) else ("No" if bool_from_text(job_text, ["no relocation"]) else "Not mentioned"),
        "tailoring": tailored,
        "analyzed_at": now_iso(),
        "source_url": job_url,
    }
    return jsonify(result)


@app.get("/api/tracker/jobs")
def list_tracked_jobs() -> Any:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tracked_jobs ORDER BY updated_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/tracker/jobs")
def create_tracked_job() -> Any:
    payload = request.get_json(silent=True) or {}
    now = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tracked_jobs (
                title, company, location, job_url, status, remote, visa_sponsorship, notes,
                target_role, top_keywords, matched_skills, missing_skills, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("title", "Untitled Role"),
                payload.get("company", ""),
                payload.get("location", ""),
                payload.get("job_url", ""),
                payload.get("status", "Saved"),
                1 if payload.get("remote") else 0,
                1 if payload.get("visa_sponsorship") else 0,
                payload.get("notes", ""),
                payload.get("target_role", ""),
                json.dumps(payload.get("top_keywords", [])),
                json.dumps(payload.get("matched_skills", [])),
                json.dumps(payload.get("missing_skills", [])),
                now,
                now,
            ),
        )
        job_id = cur.lastrowid
    return jsonify({"id": job_id, "message": "Saved"}), 201


@app.patch("/api/tracker/jobs/<int:job_id>")
def update_tracked_job(job_id: int) -> Any:
    payload = request.get_json(silent=True) or {}
    allowed = {
        "title", "company", "location", "job_url", "status", "remote", "visa_sponsorship",
        "notes", "target_role", "top_keywords", "matched_skills", "missing_skills",
    }
    fields, values = [], []
    for key, val in payload.items():
        if key not in allowed:
            continue
        if key in {"top_keywords", "matched_skills", "missing_skills"}:
            val = json.dumps(val)
        if key in {"remote", "visa_sponsorship"}:
            val = 1 if val else 0
        fields.append(f"{key} = ?")
        values.append(val)

    if not fields:
        return jsonify({"error": "No valid fields provided."}), 400

    fields.append("updated_at = ?")
    values.append(now_iso())
    values.append(job_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE tracked_jobs SET {', '.join(fields)} WHERE id = ?", values)
    return jsonify({"message": "Updated"})


@app.delete("/api/tracker/jobs/<int:job_id>")
def delete_tracked_job(job_id: int) -> Any:
    with get_conn() as conn:
        conn.execute("DELETE FROM tracked_jobs WHERE id = ?", (job_id,))
    return jsonify({"message": "Deleted"})


@app.get("/api/tracker/stats")
def tracker_stats() -> Any:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM tracked_jobs").fetchone()["c"]
        applied = conn.execute("SELECT COUNT(*) AS c FROM tracked_jobs WHERE status = 'Applied'").fetchone()["c"]
        interview = conn.execute("SELECT COUNT(*) AS c FROM tracked_jobs WHERE status = 'Interview'").fetchone()["c"]
        remote = conn.execute("SELECT COUNT(*) AS c FROM tracked_jobs WHERE remote = 1").fetchone()["c"]
        sponsorship = conn.execute("SELECT COUNT(*) AS c FROM tracked_jobs WHERE visa_sponsorship = 1").fetchone()["c"]
    return jsonify({
        "total": total,
        "applied": applied,
        "interview": interview,
        "remote": remote,
        "visa_sponsorship": sponsorship,
    })


@app.get("/api/search-queries")
def search_queries() -> Any:
    focus = '("analytics engineer" OR "data analyst" OR "bi analyst" OR "bi engineer")'
    modifiers = [
        "(remote OR \"visa sponsorship\" OR relocation)",
        "(\"work from anywhere\" OR worldwide OR \"global remote\" OR international)",
        "(Europe OR EU OR EMEA) (\"visa sponsorship\" OR relocation OR \"relocation support\")",
    ]
    queries = []
    for board in ATS_BOARDS:
        for title in TITLES[:6]:
            queries.append(f"site:{board} {title}")
        for m in modifiers:
            queries.append(f"site:{board} {focus} {m}")
    return jsonify({"queries": queries})


@app.get("/api/web-jobs")
def web_jobs() -> Any:
    combined: list[dict[str, Any]] = []
    warnings: list[str] = []
    for fetcher in (fetch_remotive_jobs, fetch_arbeitnow_jobs):
        try:
            combined.extend(fetcher())
        except Exception as exc:
            warnings.append(f"{fetcher.__name__} failed: {exc}")

    deduped: dict[str, dict[str, Any]] = {}
    for job in combined:
        key = normalize_text(job.get("job_url", "")).lower() or (
            f"{normalize_text(job.get('title', '')).lower()}|"
            f"{normalize_text(job.get('company', '')).lower()}|"
            f"{normalize_text(job.get('location', '')).lower()}"
        )
        if key not in deduped:
            deduped[key] = job

    jobs = list(deduped.values())
    jobs.sort(key=lambda j: j.get("published_at") or "", reverse=True)
    return jsonify({"jobs": jobs, "count": len(jobs), "warnings": warnings, "scanned_at": now_iso()})


@app.get("/api/jobs/raw")
def list_raw_jobs() -> Any:
    """List raw scraped jobs with optional filtering"""
    remote = request.args.get("remote", default=None, type=lambda x: x.lower() == "1")
    visa = request.args.get("visa", default=None, type=lambda x: x.lower() == "1")
    min_score = request.args.get("min_score", default=0, type=float)
    days = request.args.get("days", default=7, type=int)
    limit = request.args.get("limit", default=50, type=int)

    query = "SELECT * FROM raw_jobs WHERE 1=1"
    params: list[Any] = []

    if remote is not None:
        query += " AND remote = ?"
        params.append(1 if remote else 0)

    if visa is not None:
        query += " AND visa_sponsorship = ?"
        params.append(1 if visa else 0)

    if min_score > 0:
        query += " AND ats_score >= ?"
        params.append(min_score)

    if days > 0:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        query += " AND published_at >= ?"
        params.append(cutoff)

    query += " ORDER BY ats_score DESC, published_at DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify([dict(r) for r in rows])


@app.post("/api/jobs/raw/store")
def store_raw_job() -> Any:
    """Store a raw job from web scraping"""
    payload = request.get_json(silent=True) or {}
    now = now_iso()

    # Generate job_id from title+company+location hash
    import hashlib
    job_id = hashlib.md5(
        f"{payload.get('title', '')}|{payload.get('company', '')}|{payload.get('location', '')}"
        .encode()
    ).hexdigest()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO raw_jobs (
                job_id, title, company, location, job_url, source, description,
                remote, visa_sponsorship, relocation_support, ats_score, ats_category,
                role_match, matched_skills, top_keywords, published_at, scraped_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                payload.get("title", ""),
                payload.get("company", ""),
                payload.get("location", ""),
                payload.get("job_url", ""),
                payload.get("source", ""),
                payload.get("description", ""),
                1 if payload.get("remote") else 0,
                1 if payload.get("visa_sponsorship") else 0,
                1 if payload.get("relocation_support") else 0,
                payload.get("ats_score"),
                payload.get("ats_category"),
                payload.get("role_match", ""),
                json.dumps(payload.get("matched_skills", [])),
                json.dumps(payload.get("top_keywords", [])),
                payload.get("published_at", ""),
                now,
                now,
                now,
            ),
        )

    return jsonify({"id": job_id, "message": "Stored"}), 201


@app.patch("/api/jobs/raw/<job_id>/track")
def move_raw_to_tracker(job_id: str) -> Any:
    """Move a raw job to user's tracker"""
    with get_conn() as conn:
        # Get raw job
        raw = conn.execute(
            "SELECT * FROM raw_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()

        if not raw:
            return jsonify({"error": "Job not found"}), 404

        # Insert into tracked_jobs
        now = now_iso()
        cur = conn.execute(
            """
            INSERT INTO tracked_jobs (
                title, company, location, job_url, status, remote, visa_sponsorship,
                notes, target_role, top_keywords, matched_skills, missing_skills,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw["title"],
                raw["company"],
                raw["location"],
                raw["job_url"],
                "Saved",
                raw["remote"],
                raw["visa_sponsorship"],
                f"ATS: {raw['ats_score']}/100 - {raw['ats_category']}" if raw["ats_score"] else "",
                raw["role_match"],
                raw["top_keywords"],
                raw["matched_skills"],
                "",  # missing_skills
                now,
                now,
            ),
        )

        # Mark as tracked
        conn.execute(
            "UPDATE raw_jobs SET is_tracked = 1, updated_at = ? WHERE job_id = ?",
            (now, job_id),
        )

    return jsonify({"message": "Moved to tracker", "tracked_id": cur.lastrowid})


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>JobLy — Personal Job Search & ATS Assistant</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #ffffff; color: #1a1a1a; font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
    header { border-bottom: 1px solid #e5e5e5; padding: 24px 0; margin-bottom: 32px; }
    h1 { font-size: 32px; font-weight: 600; color: #1a1a1a; margin-bottom: 8px; }
    .tagline { font-size: 15px; color: #666; }
    h2 { font-size: 20px; font-weight: 600; color: #1a1a1a; margin: 24px 0 16px 0; }
    h3 { font-size: 14px; font-weight: 600; color: #1a1a1a; margin: 16px 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }

    .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 32px; }
    @media(max-width: 1024px) { .grid { grid-template-columns: 1fr; } }

    .card { background: #f9f9f9; border: 1px solid #e5e5e5; border-radius: 8px; padding: 24px; }
    .card.white { background: #ffffff; }

    label { display: block; font-size: 13px; font-weight: 500; color: #666; margin: 16px 0 6px 0; text-transform: uppercase; letter-spacing: 0.5px; }
    input, textarea, select { width: 100%; padding: 10px 12px; border: 1px solid #e5e5e5; border-radius: 6px; font-size: 14px; font-family: inherit; margin-bottom: 12px; }
    input:focus, textarea:focus, select:focus { outline: none; border-color: #0066cc; box-shadow: 0 0 0 2px rgba(0, 102, 204, 0.1); }
    textarea { min-height: 120px; resize: vertical; }

    button { background: #0066cc; color: white; border: none; border-radius: 6px; padding: 10px 16px; font-size: 14px; font-weight: 500; cursor: pointer; transition: background 0.2s; }
    button:hover { background: #0052a3; }
    button.secondary { background: transparent; color: #0066cc; border: 1px solid #0066cc; }
    button.secondary:hover { background: rgba(0, 102, 204, 0.05); }
    button.small { padding: 6px 12px; font-size: 13px; }

    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-start; margin-bottom: 12px; }
    .row > div { flex: 1; min-width: 200px; }

    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
    .stat { background: white; border: 1px solid #e5e5e5; border-radius: 6px; padding: 16px; text-align: center; }
    .stat-label { font-size: 12px; color: #999; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .stat-value { font-size: 24px; font-weight: 600; color: #0066cc; }

    .filters { background: white; border: 1px solid #e5e5e5; border-radius: 6px; padding: 16px; margin-bottom: 16px; }
    .filter-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .checkbox-group { display: flex; gap: 16px; align-items: center; }
    .checkbox { display: flex; align-items: center; gap: 6px; }
    input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }

    .tag { display: inline-block; background: #e5f0ff; color: #0066cc; padding: 4px 12px; border-radius: 20px; font-size: 13px; margin: 2px 4px 2px 0; }
    .tag.strong { background: #0066cc; color: white; }

    table { width: 100%; border-collapse: collapse; }
    th { background: #f0f0f0; text-align: left; padding: 12px; font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e5e5e5; }
    td { padding: 12px; border-bottom: 1px solid #f0f0f0; }
    tr:hover { background: #fafafa; }

    .job-title { font-weight: 600; color: #0066cc; }
    .job-subtitle { font-size: 13px; color: #999; margin-top: 4px; }

    .ats-score { display: inline-block; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
    .ats-score.poor { background: #ffe5e5; color: #d32f2f; }
    .ats-score.fair { background: #fff3e0; color: #f57f17; }
    .ats-score.good { background: #e8f5e9; color: #388e3c; }
    .ats-score.excellent { background: #d4edda; color: #155724; }

    .list { max-height: 300px; overflow-y: auto; border: 1px solid #e5e5e5; border-radius: 6px; }
    .list-item { padding: 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; font-family: "Monaco", monospace; }
    .list-item:last-child { border-bottom: none; }

    .no-data { text-align: center; color: #999; padding: 32px; }
    .error { color: #d32f2f; padding: 12px; background: #ffebee; border-radius: 6px; }
    .success { color: #155724; padding: 12px; background: #d4edda; border-radius: 6px; }

    a { color: #0066cc; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <header>
    <div class="container">
      <h1>JobLy</h1>
      <p class="tagline">Smart job search & ATS-optimized resume assistant for Data Analysts, Analytics Engineers, and Data Engineers</p>
    </div>
  </header>

  <div class="container">
    <!-- Job Analyzer Section -->
    <div class="grid">
      <section class="card">
        <h2>Analyze Job Posting</h2>
        <label>Job URL (optional)</label>
        <input id="job_url" placeholder="https://jobs.lever.co/company/job-id" />
        <label>Or paste job description</label>
        <textarea id="job_text" placeholder="Paste the full job description here..."></textarea>
        <div class="row">
          <div>
            <label>Target Role</label>
            <select id="target_role">
              <option>Data Analyst</option>
              <option>Analytics Engineer</option>
              <option>Data Engineer</option>
            </select>
          </div>
          <div>
            <label>Your Skills (comma-separated)</label>
            <input id="user_skills" placeholder="SQL, Python, dbt, Tableau, GA4" />
          </div>
        </div>
        <div class="row">
          <button onclick="analyzeJob()">Analyze Job</button>
          <button class="secondary" onclick="saveFromAnalysis()">Save to Tracker</button>
        </div>
        <div id="analysis" style="margin-top: 24px;"></div>
      </section>

      <section class="card">
        <h2>Dashboard</h2>
        <div class="stats" id="stats"></div>
        <div style="margin-top: 20px;">
          <label>Update Job Status</label>
          <div class="row">
            <input id="quick_status_id" placeholder="Job ID" style="max-width: 100px;" />
            <select id="quick_status" style="max-width: 150px;">
              <option>Saved</option><option>Applied</option><option>Interview</option><option>Offer</option><option>Rejected</option>
            </select>
            <button class="secondary small" onclick="updateStatus()">Update</button>
          </div>
        </div>
      </section>
    </div>

    <!-- Tracked Jobs Section -->
    <section class="card white">
      <h2>Your Tracked Jobs</h2>
      <div style="overflow-x: auto;">
        <table id="jobs_tbl">
          <thead><tr>
            <th>ID</th><th>Role</th><th>Company</th><th>Status</th><th>Remote</th><th>Visa</th><th>Notes</th><th></th>
          </tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <!-- Raw Jobs Section -->
    <section class="card white">
      <h2>Smart Job Discovery</h2>
      <p style="color: #666; margin-bottom: 16px;">Browse automatically scraped jobs matching your criteria. Filter by remote status, visa sponsorship, and ATS score.</p>

      <div class="filters">
        <div class="filter-row">
          <div class="checkbox-group">
            <label class="checkbox"><input type="checkbox" id="filter_remote" /> Remote Only</label>
            <label class="checkbox"><input type="checkbox" id="filter_visa" /> Visa Sponsorship</label>
          </div>
          <div>
            <label>Min ATS Score</label>
            <input type="number" id="filter_score" min="0" max="100" value="60" style="margin-bottom: 0;" />
          </div>
          <div>
            <label>Posted (days)</label>
            <input type="number" id="filter_days" min="1" max="30" value="7" style="margin-bottom: 0;" />
          </div>
          <div style="display: flex; gap: 8px; align-items: flex-end;">
            <button onclick="loadRawJobs()">Search</button>
            <button class="secondary" onclick="clearFilters()">Reset</button>
          </div>
        </div>
      </div>

      <p id="raw_jobs_meta" style="color: #999; font-size: 13px; margin-bottom: 12px;"></p>
      <div style="overflow-x: auto;">
        <table id="raw_jobs_tbl">
          <thead><tr>
            <th>Role</th><th>Company</th><th>Location</th><th>ATS Score</th><th>Remote</th><th>Visa</th><th>Posted</th><th></th>
          </tr></thead>
          <tbody><tr><td colspan="8" class="no-data">Click "Search" to load jobs</td></tr></tbody>
        </table>
      </div>
    </section>

    <!-- Search Queries Section -->
    <section class="card white">
      <h2>Google Search Queries</h2>
      <p style="color: #666; margin-bottom: 16px;">Pre-built search queries for major ATS boards. Use on Google with Tools → Past week filter.</p>
      <button class="secondary" onclick="loadQueries()" style="margin-bottom: 16px;">Generate Queries</button>
      <div class="list" id="queries"></div>
    </section>
  </div>

<script>
let latestAnalysis = null;

async function jfetch(url, opts={}) {
  const r = await fetch(url, {headers:{'Content-Type':'application/json'}, ...opts});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function pills(arr){return (arr||[]).map(x=>`<span class="tag">${x}</span>`).join('') || '<span style="color:#999">None</span>'}

async function analyzeJob(){
  const payload = {
    job_url: document.getElementById('job_url').value.trim(),
    job_text: document.getElementById('job_text').value,
    target_role: document.getElementById('target_role').value,
    user_skills: document.getElementById('user_skills').value,
  };
  try{
    const d = await jfetch('/api/analyze', {method:'POST', body: JSON.stringify(payload)});
    latestAnalysis = d;

    let scoreClass = 'poor';
    if(d.ats_score >= 81) scoreClass = 'excellent';
    else if(d.ats_score >= 61) scoreClass = 'good';
    else if(d.ats_score >= 31) scoreClass = 'fair';

    document.getElementById('analysis').innerHTML = `
      <div style="background: white; border: 1px solid #e5e5e5; border-radius: 8px; padding: 20px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
          <div style="font-size: 48px; font-weight: 700; color: #0066cc;">${d.ats_score}</div>
          <div>
            <div style="font-size: 18px; font-weight: 600;">ATS Score: <span class="ats-score ${scoreClass}">${d.ats_category}</span></div>
            <div style="font-size: 13px; color: #666; margin-top: 4px;">${d.is_strong_match ? '✓ Strong match (70+)' : '○ Below optimal threshold'}</div>
          </div>
        </div>
        <div>
          <span class="tag">Role: ${d.top_role}</span>
          <span class="tag ${d.remote_status === 'Yes' ? 'strong' : ''}">Remote: ${d.remote_status}</span>
          <span class="tag ${d.visa_sponsorship_status === 'Yes' ? 'strong' : ''}">Visa: ${d.visa_sponsorship_status}</span>
          <span class="tag ${d.relocation_support === 'Yes' ? 'strong' : ''}">Relocation: ${d.relocation_support}</span>
        </div>
      </div>
      <h3>ATS Keywords (${d.keywords.length})</h3>
      <div>${pills(d.keywords.slice(0, 25))}</div>
      <h3>Matched Skills (${d.tailoring.matched_skills.length})</h3>
      <div>${pills(d.tailoring.matched_skills)}</div>
      <h3>Missing Skills (${d.tailoring.missing_skills.length})</h3>
      <div>${pills(d.tailoring.missing_skills)}</div>
      <h3>Resume Suggestions</h3>
      <ul style="margin-left: 20px;">
        ${(d.tailoring.suggested_bullets||[]).map(b=>`<li style="margin-bottom: 8px;">${b}</li>`).join('')}
      </ul>
      <h3>ATS Optimization</h3>
      <ul style="margin-left: 20px;">
        ${(d.tailoring.ats_actions||[]).map(b=>`<li style="margin-bottom: 8px;">${b}</li>`).join('')}
      </ul>
    `;
  }catch(e){
    document.getElementById('analysis').innerHTML = `<div class="error">Error: ${e.message}</div>`;
  }
}

async function saveFromAnalysis(){
  if(!latestAnalysis){alert('Analyze a job first'); return;}
  const title = prompt('Role title:', latestAnalysis.top_role || 'Data Role');
  if(title === null) return;
  const company = prompt('Company name:', '') || 'Unknown';
  await jfetch('/api/tracker/jobs', {method:'POST', body: JSON.stringify({
    title, company, location: '', job_url: latestAnalysis.source_url || document.getElementById('job_url').value,
    status: 'Saved', remote: latestAnalysis.remote_status === 'Yes',
    visa_sponsorship: latestAnalysis.visa_sponsorship_status === 'Yes',
    notes: `ATS: ${latestAnalysis.ats_score}/100 - ${latestAnalysis.ats_category}`,
    target_role: document.getElementById('target_role').value,
    top_keywords: latestAnalysis.keywords?.slice(0,15) || [],
    matched_skills: latestAnalysis.tailoring?.matched_skills || [],
    missing_skills: latestAnalysis.tailoring?.missing_skills || [],
  })});
  await loadJobs();
  await loadStats();
  alert('Saved to tracker');
}

async function loadJobs(){
  try {
    const rows = await jfetch('/api/tracker/jobs');
    const tb = document.querySelector('#jobs_tbl tbody');
    tb.innerHTML = rows.length ? rows.map(r=>`<tr>
      <td>${r.id}</td><td class="job-title">${r.title}</td><td>${r.company || ''}</td>
      <td>${r.status}</td><td>${r.remote ? 'Yes':'No'}</td><td>${r.visa_sponsorship ? 'Yes':'No'}</td>
      <td>${(r.notes||'').slice(0,50)}</td><td><button class="secondary small" onclick="delJob(${r.id})">Delete</button></td>
    </tr>`).join('') : '<tr><td colspan="8" class="no-data">No tracked jobs yet</td></tr>';
  } catch(e) { console.error(e); }
}

async function delJob(id){
  if(!confirm('Delete this job?')) return;
  await jfetch(`/api/tracker/jobs/${id}`, {method:'DELETE'});
  await loadJobs();
  await loadStats();
}

async function updateStatus(){
  const id = document.getElementById('quick_status_id').value;
  const status = document.getElementById('quick_status').value;
  if(!id) return;
  await jfetch(`/api/tracker/jobs/${id}`, {method:'PATCH', body: JSON.stringify({status})});
  await loadJobs();
  await loadStats();
}

async function loadStats(){
  try {
    const s = await jfetch('/api/tracker/stats');
    document.getElementById('stats').innerHTML = `
      <div class="stat"><div class="stat-label">Total</div><div class="stat-value">${s.total}</div></div>
      <div class="stat"><div class="stat-label">Applied</div><div class="stat-value">${s.applied}</div></div>
      <div class="stat"><div class="stat-label">Interviews</div><div class="stat-value">${s.interview}</div></div>
      <div class="stat"><div class="stat-label">Remote</div><div class="stat-value">${s.remote}</div></div>
      <div class="stat"><div class="stat-label">Visa Support</div><div class="stat-value">${s.visa_sponsorship}</div></div>
    `;
  } catch(e) { console.error(e); }
}

async function loadRawJobs(){
  const remote = document.getElementById('filter_remote').checked ? '1' : '';
  const visa = document.getElementById('filter_visa').checked ? '1' : '';
  const min_score = document.getElementById('filter_score').value || '0';
  const days = document.getElementById('filter_days').value || '7';

  const meta = document.getElementById('raw_jobs_meta');
  const body = document.querySelector('#raw_jobs_tbl tbody');
  meta.textContent = 'Loading...';

  try{
    const url = new URL('/api/jobs/raw', window.location);
    if(remote) url.searchParams.set('remote', '1');
    if(visa) url.searchParams.set('visa', '1');
    if(min_score) url.searchParams.set('min_score', min_score);
    if(days) url.searchParams.set('days', days);

    const d = await jfetch(url.toString());
    meta.textContent = `Found ${d.length} jobs matching your criteria`;
    body.innerHTML = d.length ? d.map(j=>{
      let scoreClass = 'poor';
      if(j.ats_score >= 81) scoreClass = 'excellent';
      else if(j.ats_score >= 61) scoreClass = 'good';
      else if(j.ats_score >= 31) scoreClass = 'fair';

      return `<tr>
        <td class="job-title">${j.title}</td><td>${j.company || ''}</td><td>${j.location || ''}</td>
        <td><span class="ats-score ${scoreClass}">${j.ats_score ? j.ats_score.toFixed(0) : 'N/A'}</span></td>
        <td>${j.remote ? 'Yes' : 'No'}</td><td>${j.visa_sponsorship ? 'Yes' : 'No'}</td>
        <td style="font-size: 12px; color: #999;">${j.published_at ? new Date(j.published_at).toLocaleDateString() : ''}</td>
        <td><button class="secondary small" onclick="moveToTracker('${j.job_id}')">Save</button></td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="no-data">No jobs found. Try adjusting filters.</td></tr>';
  }catch(e){
    meta.textContent = `Error: ${e.message}`;
    body.innerHTML = '<tr><td colspan="8" class="error">Failed to load jobs</td></tr>';
  }
}

async function moveToTracker(jobId){
  try{
    await jfetch(`/api/jobs/raw/${jobId}/track`, {method:'PATCH'});
    alert('Job saved to tracker');
    await loadJobs();
    await loadStats();
  }catch(e){
    alert(`Error: ${e.message}`);
  }
}

function clearFilters(){
  document.getElementById('filter_remote').checked = false;
  document.getElementById('filter_visa').checked = false;
  document.getElementById('filter_score').value = '60';
  document.getElementById('filter_days').value = '7';
}

async function loadQueries(){
  try{
    const d = await jfetch('/api/search-queries');
    const q = document.getElementById('queries');
    q.innerHTML = d.queries.map(x=>`<div class="list-item">${x}</div>`).join('');
  }catch(e){
    q.innerHTML = `<div class="error">Error: ${e.message}</div>`;
  }
}

loadStats();
loadJobs();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
