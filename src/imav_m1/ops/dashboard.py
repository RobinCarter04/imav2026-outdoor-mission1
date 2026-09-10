"""Operator dashboard — PORTED (slimmed) FROM SaR sarFlightDay4/gui.py.

Single page, polls /api/status every 500 ms, sends {"type": ...} commands through SharedStatus.
Operator-facing only (no spectator view): telemetry, state, checklist, survey progress, detections,
results + submission countdown, a local-metres map of polygon / fence / waypoints / track.
Mission Planner remains the real map and the safety pilot's view.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from ..detection.link import DetectorLink

logging.getLogger("werkzeug").setLevel(logging.ERROR)

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>IMAV M1 operator</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}
header{display:flex;gap:16px;align-items:center;padding:10px 16px;background:#222;border-bottom:1px solid #333}
.dot{width:12px;height:12px;border-radius:50%;background:#c33;display:inline-block}.dot.on{background:#3c3}
.state{font-size:22px;font-weight:700;padding:4px 12px;border-radius:6px;background:#345}
.state.warn{background:#a50}.state.bad{background:#a22}.state.good{background:#264}
main{display:grid;grid-template-columns:360px 1fr 380px;gap:12px;padding:12px}
section{background:#1b1b1b;border:1px solid #333;border-radius:8px;padding:10px}
h3{margin:0 0 8px;font-size:13px;letter-spacing:.08em;color:#9ab;text-transform:uppercase}
button{background:#345;color:#fff;border:0;border-radius:6px;padding:8px 12px;margin:3px;cursor:pointer;font-size:14px}
button.start{background:#264;font-weight:700}button.abort{background:#a22;font-weight:700}button:disabled{opacity:.4}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:3px 4px;border-bottom:1px solid #2a2a2a;text-align:left}
.pass{color:#5d5}.fail{color:#e55}.mono{font-family:ui-monospace,monospace;font-size:12px}
#log{height:200px;overflow:auto;font-size:11px;white-space:pre-wrap}
canvas{width:100%;background:#0b1a0b;border-radius:6px}
.bar{height:14px;background:#333;border-radius:7px;overflow:hidden}.bar>div{height:100%;background:#4a8}
.big{font-size:28px;font-weight:700}
[hidden]{display:none!important}
button.resume{background:#575;font-weight:700}button.resume:disabled{background:#333;color:#888}
#ovr{border:2px solid #d84;background:#2a1f10}#ovr h3{color:#fb6}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;background:#444}
.pill.yes{background:#264;color:#8f8}.pill.no{background:#522;color:#f99}
</style></head><body>
<header><span id="conn" class="dot"></span><span id="state" class="state">…</span>
<span>mode <b id="mode">?</b></span><span>armed <b id="armed">?</b></span><span>alt <b id="alt">?</b> m</span>
<span>sats <b id="sats">?</b></span><span>batt <b id="batt">?</b>%</span><span id="clock" style="margin-left:auto"></span></header>
<main>
<div>
<section><h3>Controls</h3>
<div>KML (optional): <input id="kml" placeholder="/path/areas.kml" style="width:200px"></div>
<button onclick="cmd('setup',{kml:kmlv()})">1 Setup (area → plan → upload)</button>
<button onclick="cmd('plan',{kml:kmlv()})">plan</button><button onclick="cmd('upload')">upload</button>
<br><button onclick="cmd('preflight')">2 Preflight</button>
<label><input type="checkbox" id="pilot" onchange="cmd('pilot_ready',{value:this.checked})"> safety pilot ready</label>
<br><button class="start" id="startbtn" onclick="cmd('start_mission')">3 START MISSION</button>
<button class="abort" onclick="if(confirm('ABORT → RTL?'))cmd('abort')">ABORT</button>
<br><button class="resume" id="resumebtn" onclick="cmd('resume')" disabled>RESUME MISSION</button>
<br><button onclick="cmd('cancel')">cancel</button><button onclick="cmd('reset')">reset</button>
<div id="err" class="fail"></div></section>
<section><h3>Plan</h3><div id="plan" class="mono">—</div></section>
<section><h3>Preflight</h3><table id="pf"></table></section>
<section><h3>Detections <span id="ndet"></span></h3><table id="det"></table></section>
</div>
<div>
<section id="ovr" hidden><h3>Safety pilot has control</h3><div id="ovrtext"></div></section>
<section><h3>Map (local metres)</h3><canvas id="map" width="900" height="640"></canvas></section>
<section><h3>Survey</h3><div class="bar"><div id="pbar" style="width:0"></div></div><div id="survey" class="mono">—</div></section>
</div>
<div>
<section><h3>Results / submission</h3><div id="countdown" class="big">—</div><div id="results" class="mono">—</div></section>
<section><h3>Landing / abort</h3><div id="land" class="mono">—</div></section>
<section><h3>Log</h3><div id="log"></div></section>
</div></main>
<script>
const $=id=>document.getElementById(id);let geom=null,track=[],lastT=null;
function kmlv(){return $('kml').value||undefined}
async function cmd(type,extra){const body=Object.assign({type},extra||{});await fetch('/api/command',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)})}
function fmt(o){return o?JSON.stringify(o,null,1).replace(/[{}"]/g,''):'—'}
async function poll(){try{const s=await(await fetch('/api/status')).json();render(s)}catch(e){}}
function render(s){
 $('conn').className='dot'+(s.connected?' on':'');$('state').textContent=s.current_state;
 $('state').className='state'+(['ABORT'].includes(s.current_state)?' bad':['SURVEY','TAKEOFF','RETURN_LAND'].includes(s.current_state)?' warn':s.current_state==='DONE'?' good':'');
 const t=s.telemetry||{};$('mode').textContent=t.mode||s.current_mode;$('armed').textContent=t.armed;$('alt').textContent=t.alt;$('sats').textContent=t.sats;$('batt').textContent=t.battery_pct;
 $('clock').textContent=new Date().toLocaleTimeString();
 $('err').textContent=(s.idle&&s.idle.last_error)||'';
 $('plan').textContent=fmt(s.plan);
 if(s.preflight){let h='';for(const k in s.preflight){const v=s.preflight[k];if(typeof v==='object'&&v!==null&&'pass'in v)h+=`<tr><td class="${v.pass?'pass':'fail'}">${v.pass?'✔':'✘'} ${k}</td><td>${v.detail}</td></tr>`}$('pf').innerHTML=h;$('startbtn').disabled=!s.preflight.all_ready}
 const o=s.override,ob=$('ovr'),rb=$('resumebtn');
 if(o&&o.paused){ob.hidden=false;
  $('ovrtext').innerHTML=`<div class="big">MISSION PAUSED</div>
   <div>The mission is sending nothing. Aircraft mode <b>${o.mode}</b>.</div>
   <div style="margin-top:6px">pilot handed back <span class="pill ${o.can_resume?'yes':'no'}">${o.can_resume?'YES':'NO — needs GUIDED'}</span>
   &nbsp;waiting for <b>${o.waiting_for}</b>&nbsp;·&nbsp;aborts in ${o.seconds_left}s</div>`;
  rb.disabled=!o.can_resume;rb.textContent=o.can_resume?'RESUME MISSION':'RESUME (pilot must return to GUIDED)';
 }else{ob.hidden=true;rb.disabled=true;rb.textContent='RESUME MISSION';}
 const sv=s.survey||{};$('pbar').style.width=(sv.pct||0)+'%';$('survey').textContent=fmt(sv);
 const d=s.detections||[];$('ndet').textContent=d.length?`(${d.length})`:'';$('det').innerHTML=d.map((x,i)=>`<tr><td>${i+1}</td><td>${x.ident||x.cls}</td><td class="mono">${(+x.lat).toFixed(6)} ; ${(+x.lon).toFixed(6)}</td></tr>`).join('');
 $('land').textContent=fmt(s.landing)+(s.abort?'\nABORT: '+fmt(s.abort):'');
 if(s.results){const r=s.results;const sec=r.seconds_to_deadline;$('countdown').textContent=sec===undefined?'':(sec>=0?`${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')} to submit`:'DEADLINE PASSED');$('countdown').style.color=sec<60?'#e55':'#5d5';
  $('results').innerHTML=`vehicles: ${r.paths&&r.paths.vehicles} · <a href="/api/results/results.zip" style="color:#8cf">results.zip</a> · <a href="/api/results/mission1_vehicles.csv" style="color:#8cf">table</a> · <a href="/api/results/mission1_map.svg" target="_blank" style="color:#8cf">map</a>`}
 $('log').textContent=(s.log_tail||[]).join('\n');$('log').scrollTop=1e9;
 if(s.plan_geometry)geom=s.plan_geometry;if(t.lat&&t.armed){if(!lastT||Math.abs(t.lat-lastT[0])>1e-6||Math.abs(t.lon-lastT[1])>1e-6){track.push([t.lat,t.lon]);lastT=[t.lat,t.lon]}}
 draw(t,d);
}
function draw(t,dets){const c=$('map'),g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);if(!geom)return;
 const all=[].concat(geom.polygon||[],geom.fence||[],geom.waypoints||[]);if(!all.length)return;
 const lat0=all.reduce((a,p)=>a+p[0],0)/all.length,lon0=all.reduce((a,p)=>a+p[1],0)/all.length,kx=111320*Math.cos(lat0*Math.PI/180),ky=111320;
 const L=p=>[(p[1]-lon0)*kx,(p[0]-lat0)*ky];const pts=all.map(L);const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
 const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys),sc=Math.min((c.width-40)/(x1-x0||1),(c.height-40)/(y1-y0||1));
 const S=p=>{const q=L(p);return[(q[0]-x0)*sc+20,c.height-((q[1]-y0)*sc+20)]};
 const path=(arr,style,close,w)=>{if(!arr||arr.length<2)return;g.beginPath();arr.forEach((p,i)=>{const q=S(p);i?g.lineTo(q[0],q[1]):g.moveTo(q[0],q[1])});if(close)g.closePath();g.strokeStyle=style;g.lineWidth=w||1.5;g.stroke()};
 path(geom.fence,'#777',true,1);g.setLineDash([]);path(geom.polygon,'#4af',true,2);path(geom.waypoints,'#8f8',false,1);path(track,'#fa4',false,2);
 if(geom.landing){const q=S(geom.landing);g.fillStyle='#4c4';g.fillRect(q[0]-5,q[1]-5,10,10)}
 (dets||[]).forEach((d,i)=>{const q=S([d.lat,d.lon]);g.fillStyle='#e44';g.beginPath();g.arc(q[0],q[1],6,0,7);g.fill();g.fillStyle='#fff';g.fillText((i+1)+' '+(d.ident||d.cls),q[0]+8,q[1]+4)});
 if(t.lat){const q=S([t.lat,t.lon]);g.fillStyle='#ff0';g.beginPath();g.arc(q[0],q[1],5,0,7);g.fill()}
 g.fillStyle='#ccc';g.fillText('100 m',20,c.height-26);g.fillRect(20,c.height-22,100*sc,3);
}
setInterval(poll,500);poll();
</script></body></html>"""


def create_app(status, run_dir: Path | None = None) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return PAGE

    @app.route("/api/status")
    def api_status():
        return jsonify(status.get_status())

    @app.route("/api/command", methods=["POST"])
    def api_command():
        body = request.get_json(force=True, silent=True) or {}
        if not body.get("type"):
            return jsonify({"ok": False, "error": "missing type"}), 400
        body = {k: v for k, v in body.items() if v is not None}
        status.send_command(body)
        return jsonify({"ok": True})

    @app.route("/api/detection", methods=["POST"])
    def api_detection():
        """Second, equivalent way for a detector to report: POST one JSON detection.

        Same fields as a line of detections.jsonl (docs/DETECTION_INTERFACE.md); it is appended to
        that file, so everything downstream — dashboard, vehicle table, map — is identical.
        """
        if run_dir is None:
            return jsonify({"ok": False, "error": "no run dir"}), 503
        det = request.get_json(force=True, silent=True) or {}
        missing = [k for k in ("lat", "lon", "cls") if det.get(k) is None]
        if missing:
            return jsonify({"ok": False, "error": f"missing fields: {missing}"}), 400
        try:
            det["lat"], det["lon"] = float(det["lat"]), float(det["lon"])
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "lat/lon must be numbers"}), 400
        det.setdefault("t", time.time())
        det.setdefault("source", "http")
        DetectorLink(run_dir).append_detection(det)
        return jsonify({"ok": True})

    @app.route("/api/results/<path:name>")
    def api_results(name: str):
        if run_dir is None:
            return jsonify({"ok": False, "error": "no run dir"}), 404
        p = (run_dir / name) if name == "results.zip" else (run_dir / "results" / name)
        if not p.exists() or ".." in name:
            return jsonify({"ok": False, "error": "not found"}), 404
        return send_file(p, as_attachment=name.endswith(".zip"))

    return app
