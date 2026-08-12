"""
generate_dashboard.py
Reads all PAI time series CSVs, generates a self-contained HTML dashboard,
and pushes to GitHub (main branch, served via GitHub Pages).

Usage:
    python generate_dashboard.py

Config:
    PAI_DIR   — directory containing PAI output CSVs
    REPO_DIR  — local clone of leaf_monitor repo
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
PAI_DIR  = Path("/Stor1/karun/data/pai_timeseries")
REPO_DIR = Path("/home/kdayal/Documents/projects/qfl/leaf_monitor")

# ── Load all CSVs ─────────────────────────────────────────────────────────────
def load_scanners():
    scanners = {}
    for csv in sorted(PAI_DIR.glob("*.csv")):
        df = pd.read_csv(csv, parse_dates=["date"])
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        df = df.where(pd.notnull(df), None)
        # attach stable global index
        df["_idx"] = range(len(df))
        scanners[csv.stem] = df.to_dict(orient="records")
    return scanners

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LEAF PAI Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.26.0/plotly.min.js"></script>
<style>
  :root {
    --bg:        #f5f7f2;
    --surface:   #ffffff;
    --border:    #d6ddd0;
    --accent:    #2d6a4f;
    --accent2:   #52b788;
    --text:      #1b2e22;
    --muted:     #7a9181;
    --grid:      #e8ede4;
    --hinge:     #2d6a4f;
    --hemi:      #1a6b8a;
    --linear:    #7b5ea7;
    --flag-bad:  #c0392b;
    --flag-good: #27ae60;
    --font:      'Inter', 'Segoe UI', system-ui, sans-serif;
    --mono:      'JetBrains Mono', 'Fira Mono', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 13px; }

  header {
    background: var(--surface);
    padding: 12px 24px;
    border-bottom: 2px solid var(--accent);
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  header h1 {
    font-size: 14px; font-weight: 700; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--accent);
  }
  .updated { margin-left: auto; font-size: 11px; color: var(--muted); font-family: var(--mono); }

  .layout { display: flex; height: calc(100vh - 51px); }

  nav {
    width: 210px; min-width: 210px; background: var(--surface);
    border-right: 1px solid var(--border); overflow-y: auto; padding: 8px 0;
  }
  nav .group-label {
    font-size: 10px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.08em; padding: 12px 16px 4px; font-weight: 600;
  }
  nav button {
    display: block; width: 100%; text-align: left;
    font-family: var(--mono); font-size: 11px;
    padding: 7px 16px 7px 20px; border: none; background: none;
    color: var(--text); cursor: pointer; transition: background 0.1s;
    border-left: 3px solid transparent;
  }
  nav button:hover { background: var(--bg); }
  nav button.active { color: var(--accent); background: var(--bg); border-left-color: var(--accent); font-weight: 600; }
  .badge-bad  { float: right; color: var(--flag-bad);  font-size: 10px; }
  .badge-good { float: right; color: var(--flag-good); font-size: 10px; margin-right: 4px; }

  .main { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }

  .controls {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 8px 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    position: sticky; top: 0; z-index: 10;
  }
  .control-group { display: flex; gap: 6px; align-items: center; }
  .ctrl-label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }

  button.tog {
    font-family: var(--font); font-size: 11px; padding: 4px 10px;
    border-radius: 4px; border: 1.5px solid var(--border);
    background: var(--bg); color: var(--muted); cursor: pointer; transition: all 0.15s;
  }
  button.tog.active { border-color: var(--accent); color: var(--accent); background: #e8f5ee; font-weight: 600; }
  button.tog.link-active { border-color: var(--accent2); color: var(--accent2); background: #eaf7f2; font-weight: 600; }

  button.action {
    font-family: var(--font); font-size: 11px; padding: 5px 12px;
    border-radius: 4px; border: 1.5px solid var(--border);
    background: var(--surface); color: var(--text); cursor: pointer; transition: all 0.15s;
  }
  button.action:hover { border-color: var(--accent); color: var(--accent); }
  button.action.danger { border-color: var(--flag-bad); color: var(--flag-bad); }
  button.action.danger:hover { background: #fdf0ee; }
  button.action.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  button.action.primary:hover { background: #245c43; }

  .sep { width: 1px; height: 20px; background: var(--border); }

  .flag-summary { font-size: 11px; font-family: var(--mono); }
  .flag-summary .bad  { color: var(--flag-bad); }
  .flag-summary .good { color: var(--flag-good); }

  /* 4-column grid: row-label + 3 scan types */
  .grid {
    display: grid;
    grid-template-columns: 28px repeat(3, 1fr);
    gap: 8px;
    padding: 12px 16px;
    align-items: start;
  }

  .col-header {
    text-align: center; font-size: 11px; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em;
    padding: 4px 0;
  }

  .corner { /* top-left spacer */ }

  .plot-panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; overflow: hidden;
  }
  .plot-row-label {
    font-size: 10px; font-weight: 700; color: var(--surface);
    text-transform: uppercase; letter-spacing: 0.06em;
    padding: 4px 10px;
  }
  .plot-div { width: 100%; height: 200px; }

  #status {
    font-size: 11px; color: var(--muted); padding: 6px 20px 4px;
    font-family: var(--mono); border-top: 1px solid var(--border);
    background: var(--surface);
  }

  /* Flag choice popup */
  #flag-popup {
    display: none; position: fixed; z-index: 100;
    background: var(--surface); border: 1.5px solid var(--border);
    border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);
    padding: 14px 16px; min-width: 200px;
  }
  #flag-popup .popup-title { font-size: 11px; color: var(--muted); margin-bottom: 10px; font-weight: 600; }
  #flag-popup .popup-row { display: flex; gap: 8px; }
  #flag-popup button {
    flex: 1; font-family: var(--font); font-size: 12px; padding: 7px 10px;
    border-radius: 4px; cursor: pointer; border: 1.5px solid; font-weight: 600;
  }
  #flag-popup .btn-bad  { background: #fdf0ee; border-color: var(--flag-bad);  color: var(--flag-bad);  }
  #flag-popup .btn-good { background: #eaf7f0; border-color: var(--flag-good); color: var(--flag-good); }
  #flag-popup .btn-cancel { background: var(--bg); border-color: var(--border); color: var(--muted); font-weight: 400; margin-top: 6px; width: 100%; }
</style>
</head>
<body>

<header>
  <h1>LEAF PAI Monitor</h1>
  <span class="updated">Updated __UPDATED__</span>
</header>

<div class="layout">
  <nav id="nav"></nav>
  <div class="main">
    <div class="controls">
      <div class="control-group">
        <span class="ctrl-label">Estimator</span>
        <button class="tog active" id="tog-hinge"  onclick="toggleEst('hinge',  this)">Hinge</button>
        <button class="tog active" id="tog-hemi"   onclick="toggleEst('hemi',   this)">Hemi</button>
        <button class="tog active" id="tog-linear" onclick="toggleEst('linear', this)">Linear</button>
      </div>
      <div class="sep"></div>
      <div class="control-group">
        <span class="ctrl-label">Axes</span>
        <button class="tog" id="link-all" onclick="toggleLinkAll(this)" title="Sync zoom/pan across all panels">Link all</button>
      </div>
      <div class="sep"></div>
      <div class="control-group">
        <span class="ctrl-label">Mode</span>
        <button class="tog active" id="mode-lasso" onclick="setMode('lasso', this)" title="Lasso to select and flag points">Lasso</button>
        <button class="tog" id="mode-zoom"  onclick="setMode('zoom',  this)" title="Drag to zoom in">Zoom</button>
      </div>
      <div class="sep"></div>
      <div class="control-group">
        <button class="action" onclick="resetZoom()">Reset zoom</button>
        <button class="action" onclick="autoFlag()">Auto-flag 3×IQR</button>
        <button class="action danger" onclick="clearFlags()">Clear flags</button>
      </div>
      <div style="margin-left:auto; display:flex; gap:8px; align-items:center;">
        <span class="flag-summary" id="flag-summary"></span>
        <button class="action primary" onclick="downloadCSV()">Download CSV</button>
      </div>
    </div>

    <div class="grid" id="grid"></div>
    <div id="status">Select a scanner from the sidebar.</div>
  </div>
</div>

<!-- Flag colour popup -->
<div id="flag-popup">
  <div class="popup-title" id="popup-title">Flag selected points as:</div>
  <div class="popup-row">
    <button class="btn-bad"  onclick="applyFlag('bad')">⚑ Bad</button>
    <button class="btn-good" onclick="applyFlag('good')">✔ Good</button>
  </div>
  <button class="btn-cancel" onclick="closePopup()">Cancel</button>
</div>

<script>
const ALL_DATA = __ALL_DATA__;

const SCAN_TYPES  = ["hinge_hi", "hemi_hi", "hemi_low"];
const ESTIMATORS  = {
  hinge:  { col: "pai_hinge",  std: "pai_hinge_std",  color: "#2d6a4f", label: "Hinge",  bg: "#2d6a4f" },
  hemi:   { col: "pai_hemi",   std: "pai_hemi_std",   color: "#1a6b8a", label: "Hemi",   bg: "#1a6b8a" },
  linear: { col: "pai_linear", std: "pai_linear_std", color: "#7b5ea7", label: "Linear", bg: "#7b5ea7" },
};
const EST_KEYS    = ["hinge", "hemi", "linear"];

let currentScanner = null;
let activeEst      = new Set(["hinge", "hemi", "linear"]);
let linkAll        = false;
let dragMode       = 'lasso';   // 'lasso' | 'zoom'
let isSyncing      = false;     // prevent relayout feedback loops

// flags[scanner][idx] = 'bad' | 'good' | undefined
let flags = {};

// pending lasso selection
let pendingPoints  = null;
let pendingScanType = null;

// ── Nav ───────────────────────────────────────────────────────────────────────
function buildNav() {
  const nav = document.getElementById('nav');
  const groups = {};
  Object.keys(ALL_DATA).forEach(s => {
    const p = s.split('_')[0];
    (groups[p] = groups[p] || []).push(s);
  });
  Object.entries(groups).forEach(([prefix, names]) => {
    const lbl = document.createElement('div');
    lbl.className = 'group-label';
    lbl.textContent = prefix;
    nav.appendChild(lbl);
    names.forEach(name => {
      const btn = document.createElement('button');
      btn.id = 'nav-' + name;
      btn.textContent = name.replace(prefix + '_', '');
      btn.onclick = () => selectScanner(name);
      nav.appendChild(btn);
      if (!flags[name]) flags[name] = {};
    });
  });
}

function updateNavBadges() {
  Object.keys(ALL_DATA).forEach(name => {
    const btn = document.getElementById('nav-' + name);
    if (!btn) return;
    const f = flags[name] || {};
    const nBad  = Object.values(f).filter(v => v === 'bad').length;
    const nGood = Object.values(f).filter(v => v === 'good').length;
    // clear existing badges
    btn.querySelectorAll('.badge-bad,.badge-good').forEach(b => b.remove());
    if (nGood) btn.innerHTML += `<span class="badge-good">✔${nGood}</span>`;
    if (nBad)  btn.innerHTML += `<span class="badge-bad">⚑${nBad}</span>`;
  });
}

// ── Scanner selection ─────────────────────────────────────────────────────────
function selectScanner(name) {
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('nav-' + name)?.classList.add('active');
  currentScanner = name;
  if (!flags[name]) flags[name] = {};
  buildGrid();
  setStatus('');
}

// ── Grid build ────────────────────────────────────────────────────────────────
function buildGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  // Header row: corner + 3 scan type labels
  const corner = document.createElement('div');
  corner.className = 'corner';
  grid.appendChild(corner);
  SCAN_TYPES.forEach(st => {
    const h = document.createElement('div');
    h.className = 'col-header';
    h.textContent = st.replace(/_/g, ' ');
    grid.appendChild(h);
  });

  // Data rows: one per active estimator
  EST_KEYS.forEach(est => {
    if (!activeEst.has(est)) return;
    const cfg = ESTIMATORS[est];

    // Row label (rotated, 28px wide)
    const rowLabel = document.createElement('div');
    rowLabel.style.cssText = [
      'display:flex', 'align-items:center', 'justify-content:center',
      'writing-mode:vertical-rl', 'transform:rotate(180deg)',
      `font-size:11px`, 'font-weight:700', `color:${cfg.color}`,
      'text-transform:uppercase', 'letter-spacing:0.06em',
      'height:200px',
    ].join(';');
    rowLabel.textContent = cfg.label;
    grid.appendChild(rowLabel);

    // 3 plot cells
    SCAN_TYPES.forEach(st => {
      const rows = (ALL_DATA[currentScanner] || []).filter(r => r.scan_type === st);
      const panel = document.createElement('div');
      panel.className = 'plot-panel';
      panel.style.borderTop = `3px solid ${cfg.color}`;
      if (rows.length) {
        panel.innerHTML = `<div class="plot-div" id="plot-${est}-${st}"></div>`;
      } else {
        panel.innerHTML = `<div style="height:200px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;">no data</div>`;
      }
      grid.appendChild(panel);
      if (rows.length) renderPlot(est, st, rows);
    });
  });

  updateFlagSummary();
}

// ── Plot rendering ─────────────────────────────────────────────────────────────
function renderPlot(est, scan_type, sub) {
  const cfg = ESTIMATORS[est];
  const f   = flags[currentScanner] || {};
  const divId = `plot-${est}-${scan_type}`;

  // attach stable index from _idx column
  sub.forEach(r => { if (r._idx === undefined) r._idx = sub.indexOf(r); });

  const normal = sub.filter(r => !f[r._idx]);
  const bads   = sub.filter(r => f[r._idx] === 'bad');
  const goods  = sub.filter(r => f[r._idx] === 'good');

  const traces = [];

  if (normal.length) traces.push({
    x: normal.map(r => r.date), y: normal.map(r => r[cfg.col]),
    error_y: { type:'data', array: normal.map(r => r[cfg.std]||0), visible:true, color:cfg.color, thickness:0.8, width:2 },
    mode:'markers', type:'scatter', name: cfg.label, showlegend:false,
    marker: { color: cfg.color, size: 5, opacity: 0.8 },
    customdata: normal.map(r => r._idx),
    hovertemplate: `%{x}<br>PAI: %{y:.3f}<extra></extra>`,
  });

  if (bads.length) traces.push({
    x: bads.map(r => r.date), y: bads.map(r => r[cfg.col]),
    mode:'markers', type:'scatter', name:'bad', showlegend:false,
    marker: { color:'#c0392b', size:7, symbol:'x', line:{width:2,color:'#c0392b'} },
    customdata: bads.map(r => r._idx),
    hovertemplate: `%{x}<br>PAI: %{y:.3f} ⚑ bad<extra></extra>`,
  });

  if (goods.length) traces.push({
    x: goods.map(r => r.date), y: goods.map(r => r[cfg.col]),
    mode:'markers', type:'scatter', name:'good', showlegend:false,
    marker: { color:'#27ae60', size:6, symbol:'circle', line:{width:1.5,color:'#27ae60'} },
    customdata: goods.map(r => r._idx),
    hovertemplate: `%{x}<br>PAI: %{y:.3f} ✔ good<extra></extra>`,
  });

  const layout = {
    paper_bgcolor:'transparent', plot_bgcolor:'transparent',
    margin:{t:6,b:36,l:46,r:10},
    xaxis:{ color:'#7a9181', gridcolor:'#e8ede4', tickfont:{size:9}, tickformat:'%b %Y', zeroline:false },
    yaxis:{ color:'#7a9181', gridcolor:'#e8ede4', tickfont:{size:9}, title:{text:'PAI',font:{size:9,color:'#7a9181'}}, zeroline:false },
    hovermode:'closest',
    dragmode: dragMode,
  };

  const el = document.getElementById(divId);
  if (!el) return;
  Plotly.newPlot(divId, traces, layout, { displayModeBar:false, responsive:true });

  // Axis sync via relayout events
  el.on('plotly_relayout', eventData => {
    if (!linkAll || isSyncing) return;
    const xRange = (eventData['xaxis.range[0]'] !== undefined)
      ? [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']] : null;
    const yRange = (eventData['yaxis.range[0]'] !== undefined)
      ? [eventData['yaxis.range[0]'], eventData['yaxis.range[1]']] : null;
    const xAuto = eventData['xaxis.autorange'] === true;
    const yAuto = eventData['yaxis.autorange'] === true;
    if (!xRange && !yRange && !xAuto && !yAuto) return;
    isSyncing = true;
    EST_KEYS.forEach(e => {
      if (!activeEst.has(e)) return;
      SCAN_TYPES.forEach(s => {
        const otherId = `plot-${e}-${s}`;
        if (otherId === divId || !document.getElementById(otherId)) return;
        const update = {};
        if (xAuto)  update['xaxis.autorange'] = true;
        if (yAuto)  update['yaxis.autorange'] = true;
        if (xRange) update['xaxis.range'] = xRange;
        if (yRange) update['yaxis.range'] = yRange;
        Plotly.relayout(otherId, update);
      });
    });
    isSyncing = false;
  });

  // click = cycle flag: none → bad → good → none
  el.on('plotly_click', data => {
    if (dragMode !== 'lasso') return;  // in zoom mode, don't intercept clicks
    const idx = data.points[0].customdata;
    const cur = f[idx];
    if (!cur)          f[idx] = 'bad';
    else if (cur==='bad')  f[idx] = 'good';
    else               delete f[idx];
    rerenderPlot(est, scan_type);
    updateFlagSummary(); updateNavBadges();
  });

  // lasso/box → popup
  el.on('plotly_selected', data => {
    if (!data?.points?.length) return;
    pendingPoints   = data.points.map(p => p.customdata);
    pendingScanType = scan_type;
    pendingEst      = est;
    showPopup(data.points.length);
  });
}

function rerenderPlot(est, scan_type) {
  const sub = (ALL_DATA[currentScanner] || []).filter(r => r.scan_type === scan_type);
  renderPlot(est, scan_type, sub);
}

// ── Popup ─────────────────────────────────────────────────────────────────────
let pendingEst = null;

function showPopup(n) {
  const popup = document.getElementById('flag-popup');
  document.getElementById('popup-title').textContent = `Flag ${n} point${n>1?'s':''} as:`;
  popup.style.display = 'block';
  // position near centre
  popup.style.left = '50%'; popup.style.top = '40%';
  popup.style.transform = 'translate(-50%, -50%)';
}

function closePopup() {
  document.getElementById('flag-popup').style.display = 'none';
  pendingPoints = null; pendingScanType = null; pendingEst = null;
  // deselect
  if (currentScanner && pendingScanType && pendingEst) {
    const divId = `plot-${pendingEst}-${pendingScanType}`;
    Plotly.restyle(divId, { selectedpoints: [null] });
  }
}

function applyFlag(type) {
  if (!pendingPoints || !currentScanner) { closePopup(); return; }
  const f = flags[currentScanner];
  pendingPoints.forEach(idx => {
    if (type === 'bad')  f[idx] = 'bad';
    if (type === 'good') f[idx] = 'good';
  });
  const st  = pendingScanType;
  const est = pendingEst;
  closePopup();
  rerenderPlot(est, st);
  updateFlagSummary(); updateNavBadges();
  setStatus(`Marked ${pendingPoints?.length ?? 0} points as ${type}.`);
}

// ── Reset zoom ────────────────────────────────────────────────────────────────
function resetZoom() {
  isSyncing = true;
  const promises = [];
  EST_KEYS.forEach(e => {
    if (!activeEst.has(e)) return;
    SCAN_TYPES.forEach(s => {
      const divId = `plot-${e}-${s}`;
      if (document.getElementById(divId))
        promises.push(Plotly.relayout(divId, { 'xaxis.autorange': true, 'yaxis.autorange': true }));
    });
  });
  Promise.all(promises).then(() => { isSyncing = false; });
}

// Escape: cancel lasso selection and close popup
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closePopup();
    // clear selection highlight on all plots
    EST_KEYS.forEach(est => {
      SCAN_TYPES.forEach(st => {
        const divId = `plot-${est}-${st}`;
        const el = document.getElementById(divId);
        if (el) Plotly.restyle(divId, { selectedpoints: [null] });
      });
    });
    setStatus('Selection cleared.');
  }
});
function toggleLinkAll(btn) {
  linkAll = !linkAll;
  btn.classList.toggle('link-active', linkAll);
}

// ── Lasso / Zoom mode ─────────────────────────────────────────────────────────
function setMode(mode, btn) {
  dragMode = mode;
  document.getElementById('mode-lasso').classList.toggle('active', mode === 'lasso');
  document.getElementById('mode-zoom').classList.toggle('active',  mode === 'zoom');
  // update dragmode on all live plots without full rebuild
  EST_KEYS.forEach(e => {
    if (!activeEst.has(e)) return;
    SCAN_TYPES.forEach(s => {
      const divId = `plot-${e}-${s}`;
      const el = document.getElementById(divId);
      if (el) Plotly.relayout(divId, { dragmode: mode === 'zoom' ? 'zoom' : 'lasso' });
    });
  });
}

// ── Estimator toggle ──────────────────────────────────────────────────────────
function toggleEst(est, btn) {
  if (activeEst.has(est)) { if (activeEst.size===1) return; activeEst.delete(est); btn.classList.remove('active'); }
  else { activeEst.add(est); btn.classList.add('active'); }
  buildGrid();
}

// ── Auto-flag ─────────────────────────────────────────────────────────────────
function autoFlag() {
  if (!currentScanner) return;
  const f = flags[currentScanner];
  let n = 0;
  SCAN_TYPES.forEach(st => {
    const sub = (ALL_DATA[currentScanner]||[]).filter(r => r.scan_type === st);
    EST_KEYS.forEach(est => {
      const cfg = ESTIMATORS[est];
      const vals = sub.map(r=>r[cfg.col]).filter(v=>v!=null&&isFinite(v)).sort((a,b)=>a-b);
      if (vals.length<4) return;
      const q1=vals[Math.floor(vals.length*0.25)], q3=vals[Math.floor(vals.length*0.75)], iqr=q3-q1;
      sub.forEach(r => {
        const v=r[cfg.col];
        if (v!=null&&isFinite(v)&&(v<q1-3*iqr||v>q3+3*iqr)) { f[r._idx]='bad'; n++; }
      });
    });
  });
  buildGrid(); updateNavBadges();
  setStatus(`Auto-flagged ${n} outliers as bad (3×IQR).`);
}

// ── Clear flags ───────────────────────────────────────────────────────────────
function clearFlags() {
  if (!currentScanner) return;
  flags[currentScanner] = {};
  buildGrid(); updateNavBadges(); updateFlagSummary();
  setStatus('All flags cleared.');
}

// ── Download ──────────────────────────────────────────────────────────────────
function downloadCSV() {
  if (!currentScanner) return;
  const rows = ALL_DATA[currentScanner];
  const f    = flags[currentScanner] || {};
  const cols = Object.keys(rows[0]).filter(k => !k.startsWith('_') && k !== 'flag');
  const header = [...cols, 'flag'].join(',');
  const lines  = rows.map(r => {
    const vals = cols.map(c => r[c]===null||r[c]===undefined ? '' : r[c]);
    vals.push(f[r._idx] || '');
    return vals.join(',');
  });
  const blob = new Blob([[header,...lines].join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = currentScanner+'_flagged.csv'; a.click();
  setStatus(`Downloaded ${currentScanner}_flagged.csv`);
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function updateFlagSummary() {
  if (!currentScanner) return;
  const f = flags[currentScanner]||{};
  const nBad  = Object.values(f).filter(v=>v==='bad').length;
  const nGood = Object.values(f).filter(v=>v==='good').length;
  const el = document.getElementById('flag-summary');
  el.innerHTML = [
    nGood ? `<span class="good">✔ ${nGood} good</span>` : '',
    nBad  ? `<span class="bad">⚑ ${nBad} bad</span>`   : '',
  ].filter(Boolean).join(' &nbsp; ');
}

function setStatus(msg) { document.getElementById('status').textContent = msg; }

// ── Init ──────────────────────────────────────────────────────────────────────
buildNav();
const first = Object.keys(ALL_DATA)[0];
if (first) selectScanner(first);
</script>
</body>
</html>
"""

# ── Generate HTML ─────────────────────────────────────────────────────────────
def generate_html(scanners):
    all_data_json = json.dumps(scanners, default=str)
    updated = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    html = HTML_TEMPLATE.replace("__ALL_DATA__", all_data_json)
    html = html.replace("__UPDATED__", updated)
    return html

# ── Write HTML ────────────────────────────────────────────────────────────────
def write_html(repo_dir, html_content):
    index_path = repo_dir / "index.html"
    index_path.write_text(html_content, encoding="utf-8")
    print(f"Written: {index_path}")

# ── Git push ──────────────────────────────────────────────────────────────────
def git_push(repo_dir):
    subprocess.run(["git", "-C", str(repo_dir), "add", "index.html"], check=True)
    msg = f"Update dashboard {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", msg],
        capture_output=True, text=True
    )
    if "nothing to commit" in result.stdout:
        print("Nothing changed, skipping push.")
        return
    subprocess.run(["git", "-C", str(repo_dir), "push", "origin", "main"], check=True)
    print(f"Pushed: {msg}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading CSVs...")
    scanners = load_scanners()
    print(f"  {len(scanners)} scanners: {', '.join(scanners)}")

    print("Generating HTML...")
    html = generate_html(scanners)

    print("Writing HTML...")
    write_html(REPO_DIR, html)

    print("Pushing to GitHub...")
    git_push(REPO_DIR)

    print("Done.")