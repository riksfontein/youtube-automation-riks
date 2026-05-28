"""
generate_dashboard.py — Generate a static dashboard HTML file from state.json.
Called at the end of every Stage run by GitHub Actions.
Output: docs/index.html (served by GitHub Pages)
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

STATE_FILE = Path(__file__).parent.parent / "state.json"
DOCS_DIR   = Path(__file__).parent.parent / "docs"

CHANNEL_COLORS = {"AE": "#1D9E75", "GIA": "#378ADD", "BF": "#BA7517"}
CHANNEL_ORDER  = ["AE", "GIA", "BF"]


def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)


def generate():
    DOCS_DIR.mkdir(exist_ok=True)
    state    = load_state()
    memory   = state.get("memory", {})
    now_str  = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    # Build summary numbers
    total_videos = sum(
        state.get(ch, {}).get("total_videos_published", 0)
        for ch in CHANNEL_ORDER
    )
    total_comps = sum(
        len([k for k,v in memory.get(ch, {}).get("competitor_scores", {}).items()
             if v.get("count", 0) > 0])
        for ch in CHANNEL_ORDER
    )
    total_angles = sum(
        len([k for k,v in memory.get(ch, {}).get("angle_scores", {}).items()
             if v.get("count", 0) > 0])
        for ch in CHANNEL_ORDER
    )

    # Embed state as JS variable — data is baked in at generation time
    state_json = json.dumps({
        "AE":    state.get("AE", {}),
        "GIA":   state.get("GIA", {}),
        "BF":    state.get("BF", {}),
        "memory": memory
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YouTube Automation Dashboard</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh;padding:2rem 1rem}}
  .wrap{{max-width:1100px;margin:0 auto}}
  h1{{font-size:1.4rem;font-weight:500;color:#f1f5f9;margin-bottom:0.25rem}}
  .updated{{font-size:0.75rem;color:#64748b;margin-bottom:2rem}}
  .section-label{{font-size:0.65rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#475569;margin:2rem 0 0.75rem}}
  .metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:1rem}}
  .metric{{background:#1e2130;border:1px solid #2d3348;border-radius:10px;padding:1rem}}
  .metric .lbl{{font-size:0.72rem;color:#64748b;margin-bottom:6px}}
  .metric .val{{font-size:1.8rem;font-weight:500;color:#f1f5f9}}
  .metric .sub{{font-size:0.68rem;color:#475569;margin-top:3px}}
  .card{{background:#1e2130;border:1px solid #2d3348;border-radius:12px;padding:1.25rem;margin-bottom:12px}}
  .ch-header{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
  .ch-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .ch-name{{font-size:0.9rem;font-weight:500;color:#f1f5f9}}
  .ch-sub{{font-size:0.72rem;color:#64748b}}
  .prog-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .prog-label{{font-size:0.72rem;color:#64748b;min-width:90px}}
  .prog-track{{flex:1;height:6px;background:#2d3348;border-radius:3px;overflow:hidden}}
  .prog-fill{{height:100%;border-radius:3px;transition:width 1s ease}}
  .prog-count{{font-size:0.72rem;color:#94a3b8;min-width:40px;text-align:right}}
  .rot-pills{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
  .pill{{font-size:0.68rem;padding:3px 10px;border-radius:20px;border:1px solid #2d3348;color:#64748b}}
  .pill.active{{color:#f1f5f9;border-color:transparent}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  @media(max-width:600px){{.two-col{{grid-template-columns:1fr}}}}
  .comp-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #2d3348}}
  .comp-row:last-child{{border-bottom:none}}
  .comp-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
  .comp-name{{flex:1;font-size:0.8rem;color:#cbd5e1}}
  .comp-track{{width:80px;height:4px;background:#2d3348;border-radius:2px;overflow:hidden}}
  .comp-fill{{height:100%;border-radius:2px}}
  .comp-val{{font-size:0.7rem;color:#64748b;min-width:70px;text-align:right}}
  .angle-row{{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #2d3348;font-size:0.78rem}}
  .angle-row:last-child{{border-bottom:none}}
  .angle-name{{color:#cbd5e1;flex:1;padding-right:8px}}
  .angle-badge{{background:#14532d;color:#4ade80;font-size:0.65rem;padding:2px 8px;border-radius:20px;white-space:nowrap}}
  .vid-row{{padding:10px 0;border-bottom:1px solid #2d3348}}
  .vid-row:last-child{{border-bottom:none}}
  .vid-title{{font-size:0.85rem;color:#f1f5f9;font-weight:500;margin-bottom:4px}}
  .vid-meta{{font-size:0.72rem;color:#64748b}}
  .views-tag{{display:inline-block;font-size:0.68rem;padding:1px 7px;border-radius:20px;margin-left:6px}}
  .tag-green{{background:#14532d;color:#4ade80}}
  .tag-amber{{background:#431407;color:#fb923c}}
  .empty{{font-size:0.78rem;color:#475569;text-align:center;padding:1.5rem 0}}
  .footer{{margin-top:3rem;padding-top:1rem;border-top:1px solid #1e2130;font-size:0.7rem;color:#334155;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
  <h1>YouTube Automation</h1>
  <div class="updated">Last updated: {now_str}</div>

  <div class="section-label">overview</div>
  <div class="metric-grid">
    <div class="metric"><div class="lbl">videos produced</div><div class="val" id="m-total">{total_videos}</div><div class="sub">all channels</div></div>
    <div class="metric"><div class="lbl">active channels</div><div class="val">3</div><div class="sub">AE · GIA · BF</div></div>
    <div class="metric"><div class="lbl">competitors tracked</div><div class="val">{total_comps}</div><div class="sub">with performance data</div></div>
    <div class="metric"><div class="lbl">angles learned</div><div class="val">{total_angles}</div><div class="sub">with performance data</div></div>
  </div>

  <div class="section-label">channel rotation progress</div>
  <div id="channel-cards"></div>

  <div class="two-col">
    <div>
      <div class="section-label">top competitor sources</div>
      <div class="card" id="comp-card"><div class="empty">No performance data yet</div></div>
    </div>
    <div>
      <div class="section-label">top performing angles</div>
      <div class="card" id="angle-card"><div class="empty">No angle data yet</div></div>
    </div>
  </div>

  <div class="section-label">recent videos</div>
  <div class="card" id="recent-card"><div class="empty">No videos produced yet</div></div>

  <div class="footer">riksfontein/youtube-automation · auto-generated after each stage run</div>
</div>

<script>
const STATE = {state_json};
const COLORS = {{"AE":"#1D9E75","GIA":"#378ADD","BF":"#BA7517"}};
const CHANNELS = ["AE","GIA","BF"];

function fmt(n){{ return Number(n).toLocaleString(); }}

function renderChannels(){{
  const el = document.getElementById('channel-cards');
  el.innerHTML = CHANNELS.map(ch => {{
    const d = STATE[ch]||{{}};
    const pct = Math.min(100, Math.round((d.videos_in_rotation||0)/(d.rotation_threshold||15)*100));
    const color = COLORS[ch];
    const rots = d.rotations||{{}};
    const cur = d.current_rotation||1;
    const pills = Object.entries(rots).map(([n,name]) =>
      `<span class="pill${{parseInt(n)===cur?' active':''}}" style="${{parseInt(n)===cur?`background:${{color}}22;color:${{color}};border-color:${{color}}44`:''}}">
        ${{n}}. ${{name}}</span>`).join('');
    return `<div class="card">
      <div class="ch-header">
        <div class="ch-dot" style="background:${{color}}"></div>
        <div class="ch-name">${{d.channel_name||ch}}</div>
        <div class="ch-sub" style="margin-left:auto">${{d.total_videos_published||0}} published</div>
      </div>
      <div class="prog-row">
        <div class="prog-label">R${{cur}} — ${{d.rotation_name||''}}</div>
        <div class="prog-track"><div class="prog-fill" style="width:${{pct}}%;background:${{color}}"></div></div>
        <div class="prog-count">${{d.videos_in_rotation||0}}/${{d.rotation_threshold||15}}</div>
      </div>
      <div class="rot-pills">${{pills}}</div>
    </div>`;
  }}).join('');
}}

function renderCompetitors(){{
  const all = [];
  CHANNELS.forEach(ch => {{
    const m = (STATE.memory||{{}})[ch]||{{}};
    Object.entries(m.competitor_scores||{{}}).forEach(([name,data]) => {{
      if((data.count||0)>0) all.push({{name,score:data.score||0,best:data.best_views||0,count:data.count||0,ch}});
    }});
  }});
  const el = document.getElementById('comp-card');
  if(!all.length){{ el.innerHTML='<div class="empty">No performance data yet</div>'; return; }}
  all.sort((a,b)=>b.score-a.score);
  const max = all[0].score||1;
  el.innerHTML = all.slice(0,6).map(c=>`
    <div class="comp-row">
      <div class="comp-dot" style="background:${{COLORS[c.ch]}}"></div>
      <div class="comp-name">${{c.name}}</div>
      <div class="comp-track"><div class="comp-fill" style="width:${{Math.round(c.score/max*100)}}%;background:${{COLORS[c.ch]}}"></div></div>
      <div class="comp-val">${{fmt(c.best)}} best</div>
    </div>`).join('');
}}

function renderAngles(){{
  const all = [];
  CHANNELS.forEach(ch => {{
    const m = (STATE.memory||{{}})[ch]||{{}};
    Object.entries(m.angle_scores||{{}}).forEach(([angle,data]) => {{
      if((data.count||0)>0) all.push({{angle,score:data.score||0,count:data.count||0,ch}});
    }});
  }});
  const el = document.getElementById('angle-card');
  if(!all.length){{ el.innerHTML='<div class="empty">No angle data yet</div>'; return; }}
  all.sort((a,b)=>b.score-a.score);
  el.innerHTML = all.slice(0,5).map(a=>`
    <div class="angle-row">
      <span class="angle-name">${{a.angle}}</span>
      <span class="angle-badge">${{(a.score/1000).toFixed(0)}}k avg · ${{a.count}}×</span>
    </div>`).join('');
}}

function renderRecent(){{
  const all = [];
  CHANNELS.forEach(ch => {{
    const m = (STATE.memory||{{}})[ch]||{{}};
    (m.produced_videos||[]).forEach(v => all.push({{...v,ch}}));
  }});
  const el = document.getElementById('recent-card');
  if(!all.length){{ el.innerHTML='<div class="empty">No videos produced yet</div>'; return; }}
  all.sort((a,b)=>new Date(b.produced_at||0)-new Date(a.produced_at||0));
  el.innerHTML = all.slice(0,8).map(v => {{
    const views = v.performance_7d?.views;
    const tag = views
      ? `<span class="views-tag tag-green">${{fmt(views)}} views (7d)</span>`
      : `<span class="views-tag tag-amber">pending</span>`;
    const date = v.produced_at ? new Date(v.produced_at).toLocaleDateString('en-GB',{{day:'numeric',month:'short'}}) : '';
    return `<div class="vid-row">
      <div class="vid-title">${{v.title||'Untitled'}} ${{tag}}</div>
      <div class="vid-meta"><span style="color:${{COLORS[v.ch]}}">${{v.ch}}</span> · ${{v.rotation||''}} · ${{v.competitor_channel||''}} · ${{date}}</div>
    </div>`;
  }}).join('');
}}

renderChannels();
renderCompetitors();
renderAngles();
renderRecent();
</script>
</body>
</html>"""

    output = Path(DOCS_DIR / "index.html")
    output.write_text(html, encoding="utf-8")
    print(f"[Dashboard] Generated: {output}")
    return str(output)


if __name__ == "__main__":
    path = generate()
    print(f"[Dashboard] Done: {path}")
