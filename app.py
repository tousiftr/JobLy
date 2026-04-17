import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import logging
import threading
from flask import Flask, jsonify, request, Response

from job_engine import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-22s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")

app   = Flask(__name__)
_state = {"running": False, "progress": {}, "total_found": 0, "error": None}
_lock  = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DataScope — Analytics Job Radar</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07080f;--surf:#0d0f1a;--card:#131624;--b1:#1a1d2e;--b2:#252a40;
  --g:#00e5a0;--b:#38bdf8;--y:#fbbf24;--r:#f87171;--p:#a78bfa;--o:#fb923c;
  --txt:#e2e8f0;--m:#64748b;--m2:#94a3b8;--rad:6px;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--txt);font:13px/1.6 'Segoe UI',system-ui,Arial,sans-serif;min-height:100vh;overflow-x:hidden}
body::after{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(0,229,160,.02) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(0,229,160,.02) 1px,transparent 1px);
  background-size:48px 48px}
#app{position:relative;z-index:1;max-width:1480px;margin:0 auto;padding:0 20px 80px}

/* ── Header ── */
header{display:flex;align-items:center;justify-content:space-between;
       padding:20px 0 16px;border-bottom:1px solid var(--b1);flex-wrap:wrap;gap:12px}
.brand{display:flex;align-items:baseline;gap:10px}
.brand-name{font-size:22px;font-weight:800;letter-spacing:-.5px;color:var(--g)}
.brand-tag{font-size:10px;color:var(--m);letter-spacing:3px;text-transform:uppercase}
.hdr-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.scan-info{font-size:11px;color:var(--m)}
.scan-info b{color:var(--g)}

/* ── Scan button ── */
#scanBtn{
  display:flex;align-items:center;gap:7px;
  background:var(--g);color:#000;border:none;border-radius:var(--rad);
  padding:10px 20px;font:700 11px/1 inherit;letter-spacing:1px;text-transform:uppercase;
  cursor:pointer;transition:all .18s;box-shadow:0 0 20px rgba(0,229,160,.35);white-space:nowrap
}
#scanBtn:hover:not(:disabled){background:#00ffb3;box-shadow:0 0 32px rgba(0,229,160,.55);transform:translateY(-1px)}
#scanBtn:disabled{background:var(--b2);color:var(--m);box-shadow:none;cursor:not-allowed}
.dot{width:7px;height:7px;border-radius:50%;background:#000;flex-shrink:0}
#scanBtn:not(:disabled) .dot{animation:blink 1.4s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}

/* ── Banner ── */
.banner{
  margin:14px 0;padding:12px 16px;border-radius:var(--rad);font-size:12px;
  display:flex;align-items:center;gap:10px;
}
.banner-info{background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.2);color:var(--b)}
.banner-warn{background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.2);color:var(--y)}
.banner-ok  {background:rgba(0,229,160,.07);border:1px solid rgba(0,229,160,.2);color:var(--g)}
.banner-icon{font-size:16px;flex-shrink:0}

/* ── Progress ── */
#progressPanel{display:none;margin:12px 0;background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);padding:14px 16px}
#progressPanel.show{display:block;animation:fadeIn .25s ease}
.prog-hdr{display:flex;justify-content:space-between;font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:2px;margin-bottom:10px}
.prog-bar-wrap{height:3px;background:var(--b1);border-radius:2px;margin-bottom:12px}
.prog-bar-fill{height:100%;background:linear-gradient(90deg,var(--g),var(--b));border-radius:2px;transition:width .5s ease;box-shadow:0 0 10px rgba(0,229,160,.4)}
.prog-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:5px}
.prog-item{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--m)}
.prog-item.done{color:var(--g)}.prog-item.running{color:var(--y)}.prog-item.err{color:var(--r)}
.prog-item .pd{width:5px;height:5px;border-radius:50%;background:var(--b2);flex-shrink:0}
.prog-item.done .pd{background:var(--g)}.prog-item.running .pd{background:var(--y);animation:blink 1s infinite}
.prog-item.err .pd{background:var(--r)}

/* ── Stats ── */
#stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:18px 0}
.stat{background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);padding:14px;position:relative;overflow:hidden;cursor:default}
.stat::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.stat:nth-child(1)::before{background:var(--g)}.stat:nth-child(2)::before{background:var(--b)}
.stat:nth-child(3)::before{background:var(--y)}.stat:nth-child(4)::before{background:var(--p)}
.stat:nth-child(5)::before{background:var(--o)}
.stat-lbl{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px}
.stat-val{font-size:26px;font-weight:800;line-height:1}
.stat:nth-child(1) .stat-val{color:var(--g)}.stat:nth-child(2) .stat-val{color:var(--b)}
.stat:nth-child(3) .stat-val{color:var(--y)}.stat:nth-child(4) .stat-val{color:var(--p)}
.stat:nth-child(5) .stat-val{color:var(--o)}
.stat-sub{font-size:10px;color:var(--m);margin-top:4px}

/* ── Filters ── */
#filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.search-wrap{flex:1;min-width:240px;position:relative}
.search-wrap input{
  width:100%;background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);
  padding:8px 10px 8px 32px;color:var(--txt);font:12px/1 inherit;outline:none;transition:border-color .15s
}
.search-wrap input:focus{border-color:var(--g)}
.search-wrap input::placeholder{color:var(--m)}
.search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--m);font-size:14px;pointer-events:none}
.chip{display:flex;align-items:center;gap:5px;background:var(--surf);border:1px solid var(--b1);border-radius:20px;padding:6px 12px;font:11px/1 inherit;color:var(--m2);cursor:pointer;white-space:nowrap;transition:all .15s}
.chip:hover{border-color:var(--b2);color:var(--txt)}
.chip.on{background:rgba(0,229,160,.08);border-color:var(--g);color:var(--g)}
.chip.on.blue{background:rgba(56,189,248,.08);border-color:var(--b);color:var(--b)}
.chip.on.yellow{background:rgba(251,191,36,.08);border-color:var(--y);color:var(--y)}
.chip .cdot{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0}
select.sel{background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);padding:7px 10px;color:var(--m2);font:11px/1 inherit;outline:none;cursor:pointer;transition:border-color .15s;max-width:200px}
select.sel:focus{border-color:var(--g)}
select.sel.active{border-color:var(--g);color:var(--g)}
.clear-btn{background:none;border:1px solid var(--b1);border-radius:var(--rad);padding:6px 12px;color:var(--m);font:11px/1 inherit;cursor:pointer;transition:all .15s}
.clear-btn:hover{border-color:var(--r);color:var(--r)}
.filter-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%}
.filter-label{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:1.5px;white-space:nowrap}

/* ── Table ── */
#tableBox{background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);overflow:hidden}
.tbl-hdr{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--b1);font-size:11px;color:var(--m);gap:12px;flex-wrap:wrap}
.tbl-count strong{color:var(--g)}
.tbl-note{color:var(--m);font-size:10px}
table{width:100%;border-collapse:collapse}
thead th{padding:9px 12px;text-align:left;font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:1.2px;border-bottom:1px solid var(--b1);white-space:nowrap;user-select:none}
tbody tr{border-bottom:1px solid var(--b1);transition:background .1s}
tbody tr:hover{background:rgba(255,255,255,.025)}
tbody tr:last-child{border-bottom:none}
tbody td{padding:10px 12px;font-size:12px;vertical-align:middle}

.job-title a{color:var(--txt);text-decoration:none;font-weight:700;font-size:13px}
.job-title a:hover{color:var(--g)}
.job-co{color:var(--m2);font-size:11px;margin-top:2px}
.loc-cell{color:var(--m2);max-width:160px}
.date-cell{color:var(--m);white-space:nowrap}
.desc-cell{color:var(--m2);font-size:11px;max-width:260px;overflow:hidden;
           display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}

/* ATS badges */
.ats{display:inline-block;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.3px;text-transform:uppercase;white-space:nowrap}
.ats-Greenhouse{background:rgba(34,197,94,.12);color:#22c55e}
.ats-Lever{background:rgba(56,189,248,.12);color:var(--b)}
.ats-Ashby{background:rgba(167,139,250,.12);color:var(--p)}
.ats-Workable{background:rgba(251,191,36,.12);color:var(--y)}
.ats-SmartRecruiters{background:rgba(248,113,113,.12);color:var(--r)}
.ats-BreezyHR{background:rgba(0,229,160,.12);color:var(--g)}
.ats-Recruitee{background:rgba(100,200,255,.12);color:#64c8ff}
.ats-Teamtailor{background:rgba(255,165,0,.12);color:orange}
.ats-Jobvite{background:rgba(200,100,255,.12);color:#c864ff}
.ats-BambooHR{background:rgba(80,200,120,.12);color:#50c878}
.ats-Workday{background:rgba(70,130,180,.12);color:#4682b4}

/* Tags */
.tags{display:flex;flex-wrap:wrap;gap:3px}
.tag{display:inline-flex;align-items:center;gap:2px;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600}
.tag-visa  {background:rgba(0,229,160,.1);color:var(--g);border:1px solid rgba(0,229,160,.2)}
.tag-reloc {background:rgba(56,189,248,.1);color:var(--b);border:1px solid rgba(56,189,248,.2)}
.tag-remote{background:rgba(251,191,36,.1);color:var(--y);border:1px solid rgba(251,191,36,.2)}

/* Apply button */
.apply-btn{
  display:inline-flex;align-items:center;gap:4px;
  padding:6px 12px;background:var(--g);border-radius:var(--rad);
  color:#000;font:700 11px/1 inherit;text-decoration:none;
  white-space:nowrap;transition:all .15s;letter-spacing:.5px
}
.apply-btn:hover{background:#00ffb3;transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,229,160,.3)}

/* Pagination */
#pagination{display:flex;align-items:center;justify-content:center;gap:6px;padding:18px 0;flex-wrap:wrap}
.pager{background:var(--surf);border:1px solid var(--b1);border-radius:var(--rad);padding:6px 11px;color:var(--m2);font:11px/1 inherit;cursor:pointer;transition:all .15s}
.pager:hover:not(:disabled){border-color:var(--b2);color:var(--txt)}
.pager.on{background:rgba(0,229,160,.08);border-color:var(--g);color:var(--g)}
.pager:disabled{opacity:.3;cursor:not-allowed}

/* Empty / Skeleton */
.empty{padding:60px 20px;text-align:center}
.empty-icon{font-size:36px;margin-bottom:12px}
.empty-title{font-size:16px;font-weight:700;color:var(--m2);margin-bottom:6px}
.empty-sub{font-size:12px;color:var(--m)}
.skel{background:linear-gradient(90deg,var(--b1) 25%,var(--b2) 50%,var(--b1) 75%);background-size:200% 100%;animation:shimmer 1.4s infinite;border-radius:3px;height:11px}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}

/* Toast */
#toast{position:fixed;bottom:22px;right:22px;z-index:9999;background:var(--card);border:1px solid var(--b1);border-radius:var(--rad);padding:12px 16px;font-size:12px;max-width:340px;opacity:0;transform:translateY(60px);transition:all .3s cubic-bezier(.34,1.56,.64,1);pointer-events:none}
#toast.show{opacity:1;transform:none}
#toast.ok{border-left:3px solid var(--g)}
#toast.err{border-left:3px solid var(--r)}
#toast.info{border-left:3px solid var(--b)}

@keyframes fadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
@media(max-width:1100px){#stats{grid-template-columns:repeat(3,1fr)}.hm{display:none}}
@media(max-width:700px){#stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:500px){#stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div id="app">

<!-- Header -->
<header>
  <div class="brand">
    <span class="brand-name">DataScope</span>
    <span class="brand-tag">Analytics Job Radar</span>
  </div>
  <div class="hdr-right">
    <div class="scan-info" id="scanInfo">No scan yet</div>
    <button id="scanBtn" onclick="triggerScan()">
      <span class="dot"></span>&nbsp;Scan Live Jobs
    </button>
  </div>
</header>

<!-- Banner -->
<div class="banner banner-info" id="banner">
  <span class="banner-icon">&#128269;</span>
  <span>
    Click <strong>Scan Live Jobs</strong> to fetch real job listings from Greenhouse, Lever, Ashby,
    Workable and 7 other ATS platforms — with real apply links directly to each company's careers page.
    Scan takes ~60–90 seconds.
  </span>
</div>

<!-- Progress -->
<div id="progressPanel">
  <div class="prog-hdr">
    <span>Scanning ATS platforms for live jobs…</span>
    <span id="progCounter">0 / 11</span>
  </div>
  <div class="prog-bar-wrap"><div class="prog-bar-fill" id="progFill" style="width:0%"></div></div>
  <div class="prog-grid" id="progGrid"></div>
</div>

<!-- Stats -->
<div id="stats">
  <div class="stat">
    <div class="stat-lbl">Total Jobs</div>
    <div class="stat-val" id="sTotal">—</div>
    <div class="stat-sub" id="sSubTotal">Run a scan to fetch live results</div>
  </div>
  <div class="stat">
    <div class="stat-lbl">Visa Sponsorship</div>
    <div class="stat-val" id="sVisa">—</div>
    <div class="stat-sub">Jobs mentioning visa support</div>
  </div>
  <div class="stat">
    <div class="stat-lbl">Relocation Support</div>
    <div class="stat-val" id="sReloc">—</div>
    <div class="stat-sub">Jobs with relocation package</div>
  </div>
  <div class="stat">
    <div class="stat-lbl">Remote Roles</div>
    <div class="stat-val" id="sRemote">—</div>
    <div class="stat-sub">Fully remote positions</div>
  </div>
  <div class="stat">
    <div class="stat-lbl">Platforms Live</div>
    <div class="stat-val" id="sPlats">—</div>
    <div class="stat-sub">ATS sources with results</div>
  </div>
</div>

<!-- Filters Row 1: search + quick chips -->
<div id="filters">
  <div class="filter-row">
    <div class="search-wrap">
      <span class="search-icon">&#9906;</span>
      <input id="qInput" type="text" placeholder="Search title, company, location…" oninput="debouncedSearch()"/>
    </div>
    <button class="chip"        id="chipVisa"   onclick="toggleChip('visa')">  <span class="cdot"></span>Visa Sponsorship</button>
    <button class="chip blue"   id="chipReloc"  onclick="toggleChip('relocation')"><span class="cdot"></span>Relocation</button>
    <button class="chip yellow" id="chipRemote" onclick="toggleChip('remote')"><span class="cdot"></span>Remote Only</button>
    <button class="clear-btn"   onclick="clearFilters()">✕ Clear all</button>
  </div>
  <div class="filter-row" style="margin-top:4px">
    <span class="filter-label">Country / Region:</span>
    <select class="sel" id="countryFilter" onchange="onCountryChange()">
      <option value="">🌐 All Countries</option>
      <optgroup label="── EU Core ──────────────────">
        <option value="germany">🇩🇪 Germany</option>
        <option value="netherlands">🇳🇱 Netherlands</option>
        <option value="france">🇫🇷 France</option>
        <option value="sweden">🇸🇪 Sweden</option>
        <option value="denmark">🇩🇰 Denmark</option>
        <option value="finland">🇫🇮 Finland</option>
        <option value="norway">🇳🇴 Norway</option>
        <option value="ireland">🇮🇪 Ireland</option>
        <option value="spain">🇪🇸 Spain</option>
        <option value="portugal">🇵🇹 Portugal</option>
        <option value="italy">🇮🇹 Italy</option>
        <option value="belgium">🇧🇪 Belgium</option>
        <option value="austria">🇦🇹 Austria</option>
        <option value="switzerland">🇨🇭 Switzerland</option>
        <option value="poland">🇵🇱 Poland</option>
        <option value="czechia">🇨🇿 Czechia</option>
        <option value="romania">🇷🇴 Romania</option>
        <option value="hungary">🇭🇺 Hungary</option>
        <option value="greece">🇬🇷 Greece</option>
        <option value="bulgaria">🇧🇬 Bulgaria</option>
        <option value="croatia">🇭🇷 Croatia</option>
        <option value="slovakia">🇸🇰 Slovakia</option>
        <option value="slovenia">🇸🇮 Slovenia</option>
        <option value="estonia">🇪🇪 Estonia</option>
        <option value="latvia">🇱🇻 Latvia</option>
        <option value="lithuania">🇱🇹 Lithuania</option>
        <option value="luxembourg">🇱🇺 Luxembourg</option>
      </optgroup>
      <optgroup label="── UK ─────────────────────────">
        <option value="uk">🇬🇧 United Kingdom</option>
      </optgroup>
      <optgroup label="── Asia-Pacific ───────────────">
        <option value="japan">🇯🇵 Japan</option>
        <option value="singapore">🇸🇬 Singapore</option>
        <option value="thailand">🇹🇭 Thailand</option>
        <option value="malaysia">🇲🇾 Malaysia</option>
        <option value="southkorea">🇰🇷 South Korea</option>
        <option value="indonesia">🇮🇩 Indonesia</option>
        <option value="vietnam">🇻🇳 Vietnam</option>
        <option value="philippines">🇵🇭 Philippines</option>
        <option value="australia">🇦🇺 Australia</option>
      </optgroup>
      <optgroup label="── Middle East ────────────────">
        <option value="uae">🇦🇪 UAE / Dubai</option>
      </optgroup>
      <optgroup label="── North America ──────────────">
        <option value="canada">🇨🇦 Canada</option>
      </optgroup>
      <optgroup label="── Remote ─────────────────────">
        <option value="remote">🌍 Remote / Global</option>
      </optgroup>
    </select>
    <select class="sel" id="atsFilter" onchange="loadJobs(1)">
      <option value="">All Platforms</option>
    </select>
    <span id="activeCountryBadge" style="display:none;font-size:11px;color:var(--g);background:rgba(0,229,160,.08);border:1px solid rgba(0,229,160,.25);border-radius:20px;padding:4px 10px"></span>
  </div>
</div>

<!-- Table -->
<div id="tableBox">
  <div class="tbl-hdr">
    <div class="tbl-count">Showing <strong id="showCount">0</strong> of <strong id="totalCount">0</strong> jobs</div>
    <div class="tbl-note" id="tblNote">All links open the real application page on the company's ATS</div>
  </div>
  <table>
    <thead>
      <tr>
        <th style="min-width:220px">Role / Company</th>
        <th class="hm" style="min-width:130px">Location</th>
        <th class="hm" style="min-width:120px">Platform</th>
        <th style="min-width:130px">Tags</th>
        <th class="hm" style="min-width:200px">Description</th>
        <th class="hm" style="min-width:80px">Posted</th>
        <th style="min-width:90px">Apply</th>
      </tr>
    </thead>
    <tbody id="jobsBody"></tbody>
  </table>
</div>

<div id="pagination"></div>
</div>

<div id="toast"></div>

<script>
const S = {
  page:1, perPage:50, q:'', ats:'', country:'',
  filters:{visa:false, relocation:false, remote:false},
  polling:null,
};
const TOTAL_COLLECTORS = 11;

document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadJobs(1);
  loadAtsList();
});

// ── API ───────────────────────────────────────────────────────────────────────
async function api(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── Scan ──────────────────────────────────────────────────────────────────────
async function triggerScan() {
  const btn = document.getElementById('scanBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="dot"></span>&nbsp;Scanning…';

  // Hide info banner, show progress
  document.getElementById('banner').style.display = 'none';
  document.getElementById('progressPanel').classList.add('show');

  try {
    const r = await fetch('/api/scan', {method:'POST'});
    if (r.status === 409) {
      toast('Scan already running — please wait', 'info');
      resetBtn();
      return;
    }
    S.polling = setInterval(pollScan, 1800);
  } catch(e) {
    toast('Could not start scan: ' + e.message, 'err');
    resetBtn();
  }
}

function resetBtn() {
  const btn = document.getElementById('scanBtn');
  btn.disabled = false;
  btn.innerHTML = '<span class="dot"></span>&nbsp;Scan Live Jobs';
}

async function pollScan() {
  try {
    const d = await api('/api/scan/status');
    renderProgress(d.progress || {});

    if (!d.running) {
      clearInterval(S.polling); S.polling = null;
      resetBtn();

      if (d.error) {
        toast('Scan error: ' + d.error, 'err');
      } else {
        const msg = d.total_found > 0
          ? `✓ Scan complete — ${d.total_found} real jobs found with live apply links!`
          : 'Scan complete. Some platforms may have no matching jobs right now — try again tomorrow.';
        toast(msg, 'ok');

        // Show success banner
        const b = document.getElementById('banner');
        b.className = d.total_found > 0 ? 'banner banner-ok' : 'banner banner-warn';
        b.innerHTML = d.total_found > 0
          ? `<span class="banner-icon">&#10003;</span><span>Found <strong>${d.total_found} real jobs</strong> from live ATS feeds. All Apply buttons link directly to the company's job page.</span>`
          : `<span class="banner-icon">&#9888;</span><span>Scan complete but few jobs matched your filters. ATS platforms are live — try broadening your search or scan again tomorrow when new roles are posted.</span>`;
        b.style.display = 'flex';

        await loadStats();
        await loadJobs(1);
        await loadAtsList();
      }

      setTimeout(() => document.getElementById('progressPanel').classList.remove('show'), 5000);
    }
  } catch(e) {}
}

function renderProgress(progress) {
  const entries = Object.entries(progress);
  const done    = entries.filter(([,v]) => v.done).length;
  document.getElementById('progCounter').textContent = `${done} / ${TOTAL_COLLECTORS}`;
  document.getElementById('progFill').style.width    = `${(done / TOTAL_COLLECTORS) * 100}%`;
  document.getElementById('progGrid').innerHTML = entries.map(([name, info]) => {
    const cls   = info.done ? 'done' : 'running';
    const label = info.done ? `${name} (${info.count} jobs)` : `${name}…`;
    return `<div class="prog-item ${cls}"><span class="pd"></span>${label}</div>`;
  }).join('');
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const d = await api('/api/stats');
    countUp('sTotal',  d.total   || 0);
    countUp('sVisa',   d.visa    || 0);
    countUp('sReloc',  d.reloc   || 0);
    countUp('sRemote', d.remote  || 0);
    countUp('sPlats',  Object.keys(d.ats_breakdown || {}).length);

    if (d.last_scan) {
      const dt = new Date(d.last_scan.timestamp);
      document.getElementById('scanInfo').innerHTML =
        `Last scan: <b>${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</b>`;
      document.getElementById('sSubTotal').textContent = `across ${d.last_scan.collectors || 11} platforms`;
    }
  } catch(e) {}
}

function countUp(id, target) {
  const el   = document.getElementById(id);
  const from = parseInt(el.textContent) || 0;
  if (from === target) { el.textContent = target.toLocaleString(); return; }
  const step = Math.max(1, Math.ceil(Math.abs(target - from) / 30));
  let cur = from;
  const t = setInterval(() => {
    cur = Math.min(cur + step, target);
    el.textContent = cur.toLocaleString();
    if (cur >= target) clearInterval(t);
  }, 20);
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
async function loadJobs(page) {
  S.page = page;
  const params = new URLSearchParams({
    page, per_page: S.perPage, q: S.q,
    ats:     document.getElementById('atsFilter').value,
    country: S.country,
    ...(S.filters.visa       ? {visa:'1'}       : {}),
    ...(S.filters.relocation ? {relocation:'1'} : {}),
    ...(S.filters.remote     ? {remote:'1'}     : {}),
  });
  showSkeleton();
  try {
    const d = await api('/api/jobs?' + params);
    document.getElementById('showCount').textContent  = d.jobs.length.toLocaleString();
    document.getElementById('totalCount').textContent = d.total.toLocaleString();
    renderRows(d.jobs);
    renderPager(d.page, d.pages);
  } catch(e) {
    document.getElementById('jobsBody').innerHTML =
      `<tr><td colspan="7"><div class="empty">
        <div class="empty-icon">&#9888;</div>
        <div class="empty-title">Could not load jobs</div>
        <div class="empty-sub">${esc(e.message)}</div>
      </div></td></tr>`;
  }
}

function showSkeleton() {
  document.getElementById('jobsBody').innerHTML = Array(8).fill(
    `<tr>${[70,50,60,40,80,35,25].map(w =>
      `<td><div class="skel" style="width:${w}%"></div></td>`).join('')}</tr>`
  ).join('');
}

function renderRows(jobs) {
  const tbody = document.getElementById('jobsBody');
  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty">
      <div class="empty-icon">&#9711;</div>
      <div class="empty-title">No jobs match your current filters</div>
      <div class="empty-sub">Try clearing some filters, or run a new scan to get fresh results</div>
    </div></td></tr>`;
    return;
  }

  tbody.innerHTML = jobs.map(j => {
    const tags = [];
    if (j.has_visa)       tags.push(`<span class="tag tag-visa">&#10022; Visa</span>`);
    if (j.has_relocation) tags.push(`<span class="tag tag-reloc">&#8599; Reloc</span>`);
    if (j.remote)         tags.push(`<span class="tag tag-remote">&#9701; Remote</span>`);
    const ats      = (j.ats_source || '').replace(/\s/g, '');
    const applyUrl = j.url || '#';
    const desc     = (j.description || '').replace(/"/g,'&quot;').slice(0, 180);

    return `<tr>
      <td>
        <div class="job-title">
          <a href="${esc(applyUrl)}" target="_blank" rel="noopener noreferrer"
             title="Open at ${esc(j.ats_source)}">${esc(j.title)}</a>
        </div>
        <div class="job-co">${esc(j.company)}${j.department ? ' &middot; <em>' + esc(j.department) + '</em>' : ''}</div>
      </td>
      <td class="loc-cell hm">${esc(j.location || '—')}</td>
      <td class="hm"><span class="ats ats-${esc(ats)}">${esc(j.ats_source)}</span></td>
      <td><div class="tags">${tags.join('') || '<span style="color:var(--m);font-size:10px">—</span>'}</div></td>
      <td class="desc-cell hm" title="${esc(desc)}">${esc(desc.slice(0, 120))}${desc.length > 120 ? '…' : ''}</td>
      <td class="date-cell hm">${fmtDate(j.posted_date, j.posted_timestamp)}</td>
      <td>
        <a class="apply-btn" href="${esc(applyUrl)}" target="_blank" rel="noopener noreferrer">
          Apply &#8594;
        </a>
      </td>
    </tr>`;
  }).join('');
}

function renderPager(cur, total) {
  const el = document.getElementById('pagination');
  if (total <= 1) { el.innerHTML = ''; return; }
  let pages = new Set([1]);
  for (let i = Math.max(2, cur-2); i <= Math.min(total-1, cur+2); i++) pages.add(i);
  pages.add(total);
  pages = [...pages].sort((a, b) => a - b);
  let html = `<button class="pager" onclick="loadJobs(${cur-1})" ${cur===1?'disabled':''}>&#8592; Prev</button>`;
  let prev = null;
  for (const p of pages) {
    if (prev && p - prev > 1) html += `<span class="pager" style="cursor:default;opacity:.3">…</span>`;
    html += `<button class="pager ${p===cur?'on':''}" onclick="loadJobs(${p})">${p}</button>`;
    prev = p;
  }
  html += `<button class="pager" onclick="loadJobs(${cur+1})" ${cur===total?'disabled':''}>Next &#8594;</button>`;
  el.innerHTML = html;
}

async function loadAtsList() {
  try {
    const sources = await api('/api/ats_sources');
    const sel = document.getElementById('atsFilter');
    sel.innerHTML = '<option value="">All Platforms</option>' +
      sources.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
  } catch(e) {}
}

const CHIP_MAP = {visa:'chipVisa', relocation:'chipReloc', remote:'chipRemote'};
function toggleChip(key) {
  S.filters[key] = !S.filters[key];
  document.getElementById(CHIP_MAP[key]).classList.toggle('on', S.filters[key]);
  loadJobs(1);
}

function onCountryChange() {
  const sel = document.getElementById('countryFilter');
  S.country = sel.value;
  const badge = document.getElementById('activeCountryBadge');
  if (S.country) {
    const label = sel.options[sel.selectedIndex].text;
    badge.textContent = label;
    badge.style.display = 'inline';
    sel.classList.add('active');
  } else {
    badge.style.display = 'none';
    sel.classList.remove('active');
  }
  loadJobs(1);
}

function clearFilters() {
  S.q = ''; S.country = '';
  S.filters = {visa:false, relocation:false, remote:false};
  document.getElementById('qInput').value = '';
  document.getElementById('atsFilter').value = '';
  document.getElementById('countryFilter').value = '';
  document.getElementById('activeCountryBadge').style.display = 'none';
  document.getElementById('countryFilter').classList.remove('active');
  Object.values(CHIP_MAP).forEach(id => document.getElementById(id).classList.remove('on'));
  loadJobs(1);
}

let _st;
function debouncedSearch() {
  clearTimeout(_st);
  _st = setTimeout(() => { S.q = document.getElementById('qInput').value; loadJobs(1); }, 320);
}

function fmtDate(raw, ts) {
  if (ts) {
    const diff = Math.floor((Date.now() - ts * 1000) / 1000);
    if (diff < 3600)   return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400)  return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return new Date(ts * 1000).toLocaleDateString();
  }
  return (raw || '—').slice(0, 10);
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = 'show ' + (type || 'ok');
  setTimeout(() => { t.className = type || 'ok'; }, 4500);
}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.route("/api/jobs")
def api_jobs():
    from config import COUNTRY_GROUP_MAP
    jobs = engine.load_cache()
    visa_only  = request.args.get("visa")       == "1"
    reloc_only = request.args.get("relocation") == "1"
    rem_only   = request.args.get("remote")     == "1"
    ats_f      = request.args.get("ats",  "").strip().lower()
    country_f  = request.args.get("country", "").strip().lower()
    q          = request.args.get("q",    "").strip().lower()
    page       = max(1, int(request.args.get("page", 1)))
    per_page   = min(100, max(10, int(request.args.get("per_page", 50))))

    out = jobs
    if visa_only:  out = [j for j in out if j.has_visa]
    if reloc_only: out = [j for j in out if j.has_relocation]
    if rem_only:   out = [j for j in out if j.remote]
    if ats_f:      out = [j for j in out if ats_f in j.ats_source.lower()]
    if country_f:
        terms = COUNTRY_GROUP_MAP.get(country_f, [country_f])
        def matches_country(j):
            loc_desc = (j.location + " " + j.description).lower()
            return any(t in loc_desc for t in terms)
        out = [j for j in out if matches_country(j)]
    if q:
        out = [j for j in out if q in j.title.lower()
               or q in j.company.lower() or q in j.location.lower()
               or q in j.description.lower()]

    total  = len(out)
    sliced = out[(page - 1) * per_page : page * per_page]
    return jsonify({
        "jobs":     [j.to_dict() for j in sliced],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, -(-total // per_page)),
    })


@app.route("/api/countries")
def api_countries():
    from config import COUNTRY_GROUPS
    return jsonify([{"label": lbl, "key": key} for lbl, key, _ in COUNTRY_GROUPS])


@app.route("/api/stats")
def api_stats():
    jobs = engine.load_cache()
    meta = engine.load_meta()
    ats_bd: dict = {}
    visa = reloc = remote = 0
    for j in jobs:
        ats_bd[j.ats_source] = ats_bd.get(j.ats_source, 0) + 1
        if j.has_visa:       visa   += 1
        if j.has_relocation: reloc  += 1
        if j.remote:         remote += 1
    return jsonify({
        "total":         len(jobs),
        "visa":          visa,
        "reloc":         reloc,
        "remote":        remote,
        "ats_breakdown": ats_bd,
        "last_scan":     meta,
        "scan_running":  _state["running"],
    })


@app.route("/api/ats_sources")
def api_ats_sources():
    jobs = engine.load_cache()
    return jsonify(sorted({j.ats_source for j in jobs}))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    with _lock:
        if _state["running"]:
            return jsonify({"status": "already_running"}), 409
        _state.update(running=True, progress={}, error=None, total_found=0)

    def _run():
        try:
            def cb(name, count):
                with _lock:
                    _state["progress"][name] = {"done": True, "count": count}
            jobs = engine.scan(on_progress=cb)
            with _lock:
                _state["total_found"] = len(jobs)
        except Exception as e:
            logger.error("Scan failed: %s", e, exc_info=True)
            with _lock:
                _state["error"] = str(e)
        finally:
            with _lock:
                _state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/scan/status")
def api_scan_status():
    with _lock:
        return jsonify(dict(_state))


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   DataScope — Analytics Job Radar  v2       ║")
    print("  ║   Open browser: http://localhost:5000       ║")
    print("  ║   Click 'Scan Live Jobs' for real results   ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
