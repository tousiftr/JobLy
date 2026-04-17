import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

    result = {
        "keywords": kw,
        "role_scores": role_scores,
        "top_role": max(role_scores, key=role_scores.get),
        "requirements": [k for k in kw if k in {
            "sql", "python", "dbt", "tableau", "power bi", "snowflake", "bigquery",
            "airflow", "spark", "aws", "gcp", "azure", "ga4", "gtm"
        }],
        "remote_friendly": bool_from_text(job_text, ["remote", "global remote", "work from anywhere"]),
        "visa_sponsorship": bool_from_text(job_text, ["visa sponsorship", "work permit", "sponsor"]),
        "relocation_support": bool_from_text(job_text, ["relocation", "relocation support", "relocation assistance"]),
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


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>JobLy — Personal Job Portal + ATS Resume Assistant</title>
  <style>
    :root{--bg:#0b1020;--card:#131b34;--line:#273256;--txt:#e6ecff;--muted:#93a2d1;--accent:#4ade80;--accent2:#60a5fa}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}
    .wrap{max-width:1200px;margin:auto;padding:18px}
    h1{margin:.2rem 0 0;font-size:1.6rem} h2{margin:0 0 .7rem;font-size:1.1rem}
    .sub{color:var(--muted);margin:.3rem 0 1rem}
    .grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px} @media(max-width:980px){.grid{grid-template-columns:1fr}}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
    label{display:block;margin:.65rem 0 .25rem;color:#c7d4ff;font-size:.85rem}
    input,textarea,select{width:100%;padding:10px;border-radius:8px;border:1px solid #32406c;background:#0c142a;color:var(--txt)}
    textarea{min-height:150px;resize:vertical}
    button{background:var(--accent);color:#062010;border:none;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer}
    button.secondary{background:#233154;color:#cfe0ff;border:1px solid #32406c}
    .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .stat{padding:10px;border:1px solid #334270;border-radius:8px;background:#0e1732;min-width:130px}
    .stat b{font-size:1.15rem;display:block}
    .pill{display:inline-block;padding:3px 8px;margin:2px;border:1px solid #3d4f85;border-radius:999px;font-size:.8rem;background:#0d1631}
    .list{max-height:260px;overflow:auto;border:1px solid #344471;border-radius:8px;padding:8px;background:#0b1329}
    table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid #2a385f;padding:8px;text-align:left;vertical-align:top}
    th{color:#b6c6f7;font-size:.8rem} .muted{color:var(--muted)} .ok{color:var(--accent)} .warn{color:#facc15}
    a{color:var(--accent2)}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>JobLy — Smart Personal Career Assistant</h1>
    <p class="sub">Built for Data Analyst, Analytics Engineer, and Data Engineer roles with focus on remote + visa sponsorship opportunities for a Bangladeshi applicant.</p>

    <div class="grid">
      <section class="card">
        <h2>1) Job Analyzer + ATS Resume Tailoring</h2>
        <label>Job URL (optional)</label>
        <input id="job_url" placeholder="https://jobs.lever.co/..." />
        <label>or Job Description</label>
        <textarea id="job_text" placeholder="Paste full JD here"></textarea>
        <div class="row">
          <div style="flex:1;min-width:200px">
            <label>Target Role</label>
            <select id="target_role">
              <option>Data Analyst</option>
              <option>Analytics Engineer</option>
              <option>Data Engineer</option>
            </select>
          </div>
          <div style="flex:2;min-width:240px">
            <label>Your Current Skills (comma-separated)</label>
            <input id="user_skills" placeholder="SQL, Python, dbt, Tableau, GA4" />
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <button onclick="analyzeJob()">Analyze + Tailor Resume</button>
          <button class="secondary" onclick="saveFromAnalysis()">Save to Tracker</button>
        </div>

        <div id="analysis" style="margin-top:14px"></div>
      </section>

      <aside class="card">
        <h2>2) Tracker Snapshot</h2>
        <div id="stats" class="row"></div>
        <p class="muted" style="margin:.7rem 0 .4rem">Status to use: Saved, Applied, Interview, Offer, Rejected.</p>
        <div class="row">
          <input id="quick_status_id" placeholder="Job ID" style="max-width:120px"/>
          <select id="quick_status" style="max-width:160px">
            <option>Saved</option><option>Applied</option><option>Interview</option><option>Offer</option><option>Rejected</option>
          </select>
          <button class="secondary" onclick="updateStatus()">Update</button>
        </div>
      </aside>
    </div>

    <section class="card" style="margin-top:14px">
      <h2>3) Tracked Jobs Dashboard</h2>
      <div style="overflow:auto"><table id="jobs_tbl"><thead><tr>
        <th>ID</th><th>Role / Company</th><th>Status</th><th>Remote</th><th>Visa</th><th>Notes</th><th>Actions</th>
      </tr></thead><tbody></tbody></table></div>
    </section>

    <section class="card" style="margin-top:14px">
      <h2>4) Built-in Google Search Query Generator</h2>
      <p class="muted">Use these on Google and set <b>Tools → Past week</b>; then verify each posting page for real recency and sponsorship wording.</p>
      <div class="row"><button class="secondary" onclick="loadQueries()">Generate Queries</button></div>
      <div id="queries" class="list" style="margin-top:10px"></div>
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

function pills(arr){return (arr||[]).map(x=>`<span class="pill">${x}</span>`).join('') || '<span class="muted">None</span>'}

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
    document.getElementById('analysis').innerHTML = `
      <div class="row" style="margin-bottom:8px">
        <span class="pill">Top role fit: <b>${d.top_role}</b></span>
        <span class="pill ${d.remote_friendly ? 'ok':'warn'}">Remote: ${d.remote_friendly ? 'Yes':'Unknown'}</span>
        <span class="pill ${d.visa_sponsorship ? 'ok':'warn'}">Visa: ${d.visa_sponsorship ? 'Mentioned':'Not explicit'}</span>
        <span class="pill ${d.relocation_support ? 'ok':'warn'}">Relocation: ${d.relocation_support ? 'Mentioned':'Not explicit'}</span>
      </div>
      <h3>Important ATS Keywords</h3><div>${pills(d.keywords.slice(0,28))}</div>
      <h3>Matched Skills</h3><div>${pills(d.tailoring.matched_skills)}</div>
      <h3>Potential Missing Skills</h3><div>${pills(d.tailoring.missing_skills)}</div>
      <h3>Resume Bullet Suggestions</h3>
      <ul>${(d.tailoring.suggested_bullets||[]).map(b=>`<li>${b}</li>`).join('')}</ul>
      <h3>ATS Action Checklist</h3>
      <ul>${(d.tailoring.ats_actions||[]).map(b=>`<li>${b}</li>`).join('')}</ul>
    `;
  }catch(e){
    document.getElementById('analysis').innerHTML = `<p class="warn">${e.message}</p>`;
  }
}

async function saveFromAnalysis(){
  if(!latestAnalysis){alert('Analyze a job first.'); return;}
  const title = prompt('Role title:', latestAnalysis.top_role || 'Data Role');
  if(title === null) return;
  const company = prompt('Company name:', '') ?? '';
  const notes = prompt('Notes:', '');
  await jfetch('/api/tracker/jobs', {method:'POST', body: JSON.stringify({
    title, company,
    location: '',
    job_url: latestAnalysis.source_url || document.getElementById('job_url').value,
    status: 'Saved',
    remote: latestAnalysis.remote_friendly,
    visa_sponsorship: latestAnalysis.visa_sponsorship,
    notes,
    target_role: document.getElementById('target_role').value,
    top_keywords: latestAnalysis.keywords?.slice(0,15) || [],
    matched_skills: latestAnalysis.tailoring?.matched_skills || [],
    missing_skills: latestAnalysis.tailoring?.missing_skills || [],
  })});
  await loadJobs();
  await loadStats();
  alert('Saved to tracker.');
}

async function loadJobs(){
  const rows = await jfetch('/api/tracker/jobs');
  const tb = document.querySelector('#jobs_tbl tbody');
  tb.innerHTML = rows.map(r=>{
    return `<tr>
      <td>${r.id}</td>
      <td><b>${r.title}</b><div class="muted">${r.company || ''} ${r.job_url ? `· <a href="${r.job_url}" target="_blank">link</a>`:''}</div></td>
      <td>${r.status}</td>
      <td>${r.remote ? 'Yes':'No'}</td>
      <td>${r.visa_sponsorship ? 'Yes':'No'}</td>
      <td>${(r.notes||'').slice(0,80)}</td>
      <td><button class="secondary" onclick="delJob(${r.id})">Delete</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="muted">No tracked jobs yet.</td></tr>';
}

async function delJob(id){
  if(!confirm('Delete this tracked job?')) return;
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
  const s = await jfetch('/api/tracker/stats');
  document.getElementById('stats').innerHTML = `
    <div class="stat"><span>Total</span><b>${s.total}</b></div>
    <div class="stat"><span>Applied</span><b>${s.applied}</b></div>
    <div class="stat"><span>Interview</span><b>${s.interview}</b></div>
    <div class="stat"><span>Remote</span><b>${s.remote}</b></div>
    <div class="stat"><span>Visa</span><b>${s.visa_sponsorship}</b></div>
  `;
}

async function loadQueries(){
  const d = await jfetch('/api/search-queries');
  const q = document.getElementById('queries');
  q.innerHTML = d.queries.map(x=>`<div style="padding:6px 4px;border-bottom:1px solid #26345a"><code>${x}</code></div>`).join('');
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
