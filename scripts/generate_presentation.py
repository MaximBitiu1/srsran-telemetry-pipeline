"""
Generate a self-contained HTML presentation (reveal.js CDN) for the midterm
progress report — structured to match the 12-week Bachelor Project Plan.

Usage:  python3 scripts/generate_presentation.py
Output: docs/MIDTERM_PRESENTATION.html
"""

import base64, os

ROOT    = os.path.dirname(os.path.abspath(__file__)) + "/.."
FIGURES = ROOT + "/docs/figures"
PS      = ROOT + "/datasets/stress_anomaly/plots"
PC      = ROOT + "/datasets/channel/plots"
PCOMP   = ROOT + "/docs/comparison/data"
OUT     = ROOT + "/docs/MIDTERM_PRESENTATION.html"


def b64(path):
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        mime = "image/png" if path.endswith(".png") else "image/jpeg"
        return f"data:{mime};base64,{data}"
    except FileNotFoundError:
        return ""


def img(path, style="max-width:92%;max-height:58vh;"):
    src = b64(path)
    if not src:
        return f'<p style="color:#cc4444;font-size:0.8em">[image not found: {os.path.basename(path)}]</p>'
    return f'<img src="{src}" style="{style}">'


SLIDES = []

def S(title, body, cls=""):
    SLIDES.append(f'<section class="{cls}"><h2>{title}</h2>{body}</section>')

def SR(body, cls=""):
    SLIDES.append(f'<section class="{cls}">{body}</section>')

# ── colour helpers ─────────────────────────────────────────────────────────
def done(text):    return f'<span style="color:#5dd35d">&#10003; {text}</span>'
def inprog(text):  return f'<span style="color:#f0c060">&#9679; {text}</span>'
def todo(text):    return f'<span style="color:#888888">&#9675; {text}</span>'
def tag(t, col):   return f'<span style="background:{col};color:white;border-radius:4px;padding:2px 8px;font-size:0.75em;font-weight:bold">{t}</span>'

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ══════════════════════════════════════════════════════════════════════════════
SR("""
  <h1 style="font-size:1.7em;line-height:1.35;color:#c8c8ff">
    Real-Time Telemetry in Open AI RAN<br>
    <span style="font-size:0.7em;color:#aaaadd">using Microsoft Janus (jBPF)</span>
  </h1>
  <h3 style="color:#888899;margin-top:0.4em;font-weight:normal">Midterm Progress Report</h3>
  <div style="margin-top:1.8em;font-size:0.78em;color:#aaaaaa">
    Maxim Bitiu &nbsp;·&nbsp; Bachelor Thesis &nbsp;·&nbsp; April 2026<br>
    <span style="font-size:0.88em">srsRAN Project &nbsp;·&nbsp; jBPF / Janus &nbsp;·&nbsp; ZMQ &nbsp;·&nbsp; InfluxDB &nbsp;·&nbsp; Grafana</span>
  </div>
""", cls="title-slide")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 2 — PROJECT OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
S("Project Overview", """
<ul style="font-size:0.82em">
  <li><b>Goal:</b> Move beyond "black box" RAN monitoring — insert eBPF codelets
      directly into the srsRAN software stack to capture microsecond-level events</li>
  <li><b>Technology:</b> Microsoft Janus (jBPF) runtime, srsRAN Project gNB, ZMQ virtual radio</li>
</ul>
<table style="width:90%;margin:0.6em auto;font-size:0.78em;border-collapse:collapse">
<tr style="background:#333355;color:white">
  <th style="padding:5px 10px">Objective</th><th style="padding:5px 10px">Deliverable</th>
</tr>
<tr style="background:#22223a">
  <td>1. Environment</td><td>Simulated 5G network (Core + gNB + UE) via srsRAN + ZMQ</td>
</tr>
<tr style="background:#2a2a42">
  <td>2. Telemetry</td><td>C-based jBPF codelets hooked into the RAN stack</td>
</tr>
<tr style="background:#22223a">
  <td>3. Visualisation</td><td>36-panel real-time Grafana dashboard</td>
</tr>
<tr style="background:#2a2a42">
  <td>4. Extension</td><td>In-network pre-processing + AI-ready datasets</td>
</tr>
</table>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 3 — 12-WEEK PLAN OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
S("12-Week Plan — Overall Progress", f"""
<div style="font-size:0.78em;display:grid;grid-template-columns:repeat(5,1fr);gap:0.3em 0.4em;text-align:center">

  <div style="background:#1a3a1a;border:1px solid #5dd35d;border-radius:6px;padding:0.4em">
    <b style="color:#5dd35d">Phase I</b><br>
    <span style="font-size:0.85em">Weeks 1–2<br>Foundation</span><br>
    {tag("DONE","#2d6a2d")}
  </div>

  <div style="background:#1a3a1a;border:1px solid #5dd35d;border-radius:6px;padding:0.4em">
    <b style="color:#5dd35d">Phase II</b><br>
    <span style="font-size:0.85em">Weeks 3–5<br>Codelets</span><br>
    {tag("DONE","#2d6a2d")}
  </div>

  <div style="background:#1a3a1a;border:1px solid #5dd35d;border-radius:6px;padding:0.4em">
    <b style="color:#5dd35d">Phase III</b><br>
    <span style="font-size:0.85em">Weeks 6–7<br>Eval</span><br>
    {tag("DONE","#2d6a2d")}
  </div>

  <div style="background:#1a3a1a;border:1px solid #5dd35d;border-radius:6px;padding:0.4em">
    <b style="color:#5dd35d">Phase IV</b><br>
    <span style="font-size:0.85em">Weeks 8–9<br>Extension</span><br>
    {tag("DONE","#2d6a2d")}
  </div>

  <div style="background:#3a3a1a;border:1px solid #f0c060;border-radius:6px;padding:0.4em">
    <b style="color:#f0c060">Phase V</b><br>
    <span style="font-size:0.85em">Weeks 10–12<br>Conclusion</span><br>
    {tag("IN PROGRESS","#7a6000")}
  </div>

</div>
<p style="font-size:0.72em;margin-top:0.8em;color:#aaaaaa">
  All implementation phases complete. Currently in Phase V — dataset validation done,
  thesis writing in progress.
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 4 — PHASE I: ENVIRONMENT SETUP
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase I — Foundation {tag('Weeks 1–2','#2d6a2d')}", f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5em 2em;font-size:0.78em;text-align:left">
<div>
<b style="color:#5dd35d">Week 1 — Theory</b><br>
{done("3GPP MAC/PHY layer architecture")}
{done("srsRAN Project documentation")}
{done("Microsoft Janus (jBPF) concepts")}
{done("Linux environment setup")}
<br>
<b style="color:#5dd35d">Week 2 — Lab Setup</b><br>
{done("Compiled srsRAN with ZMQ support")}
{done("Launched Open5GS core + gNB + UE")}
{done("Established stable 5G link (ping test)")}
{done("Configured jBPF runtime (jrtc)")}
</div>
<div>
{img(FIGURES+"/fig_system_architecture.png", "max-width:100%;max-height:35vh")}
</div>
</div>
<p style="font-size:0.7em;color:#5dd35d;margin-top:0.4em">
  Milestone achieved: Stable 5G simulation with ZMQ virtual radio on a single machine
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 5 — PHASE II: CODELETS
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase II — Smart Probes {tag('Weeks 3–5','#2d6a2d')}", f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5em 2em;font-size:0.78em;text-align:left">
<div>
<b style="color:#5dd35d">Week 3 — Codelet Anatomy</b><br>
{done("Analysed jbpf_codelet structure")}
{done("Defined Protobuf message formats")}
{done("Hello World codelet working")}<br><br>

<b style="color:#5dd35d">Week 4 — Hook Implementation</b><br>
{done("Attached to MAC scheduler hooks")}
{done("Extracted raw data at call sites")}
{done("11 codelet sets, 22 hook points")}<br><br>

<b style="color:#5dd35d">Week 5 — Serialisation & Output</b><br>
{done("Protobuf serialisation pipeline")}
{done("17 telemetry schemas flowing to decoder")}
{done("Milestone: raw telemetry in terminal")}
</div>
<div style="font-size:0.75em">
<b>Hook Coverage (17 schemas):</b><br>
<table style="width:100%;border-collapse:collapse;margin-top:0.3em">
<tr style="background:#333355"><th>Layer</th><th>Hooks</th></tr>
<tr style="background:#22223a"><td>MAC</td><td>harq_stats, crc_stats, bsr_stats, uci_stats</td></tr>
<tr style="background:#2a2a42"><td>FAPI</td><td>fapi_dl_config, fapi_ul_config, fapi_crc</td></tr>
<tr style="background:#22223a"><td>RLC</td><td>rlc_ul_stats, rlc_dl_stats</td></tr>
<tr style="background:#2a2a42"><td>PDCP</td><td>pdcp_ul_stats, pdcp_dl_stats</td></tr>
<tr style="background:#22223a"><td>Control</td><td>rach_stats, rrc_procedure, ngap_*</td></tr>
<tr style="background:#2a2a42"><td>Meta</td><td><b>jbpf_out_perf_list</b> (hook latency)</td></tr>
</table>
</div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 6 — PHASE III: VISUALISATION
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase III — Visualisation {tag('Week 6','#2d6a2d')}", f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5em 2em;font-size:0.78em;text-align:left">
<div>
{done("Python subscriber listening to jBPF output")}
{done("Live time-series plots with Matplotlib")}
{done("InfluxDB 1.x integration (srsran_telemetry db)")}
{done("36-panel Grafana dashboard")}
<br>
<b>Dashboard panels include:</b>
<ul style="margin-top:0.2em">
  <li>HARQ MCS min/max/avg envelope</li>
  <li>SINR per CRC event</li>
  <li>BSR at sub-second resolution</li>
  <li>Hook execution latency (p50/p90/p95/p99)</li>
  <li>RLC SDU latency per bearer</li>
  <li>UE application throughput (iperf3)</li>
  <li>Ping RTT, jitter, loss</li>
</ul>
</div>
<div>
{img(FIGURES+"/fig_telemetry_flow.png", "max-width:100%;max-height:38vh")}
</div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 7 — PHASE III: EVALUATION
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase III — Evaluation {tag('Week 7','#2d6a2d')}", f"""
{img(FIGURES+"/fig_jbpf_vs_standard.png", "max-width:92%;max-height:55vh")}
<p style="font-size:0.7em;color:#aaaaaa;margin-top:0.3em">
  Compared Janus telemetry vs standard srsRAN metrics (WebSocket :8001) live during
  baseline and scheduler demotion scenarios
</p>
""")

S(f"Phase III — CPU Overhead Measurement {tag('Week 7','#2d6a2d')}", f"""
{img(FIGURES+"/fig_cpu_overhead.png", "max-width:92%;max-height:55vh")}
<p style="font-size:0.7em;color:#aaaaaa;margin-top:0.3em">
  Overhead measured directly from <code>jbpf_out_perf_list</code> — no external profiler.
  Total ~3.3% of one core at 25 Mbps load.
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 9 — PHASE IV: IN-NETWORK LOGIC
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase IV — In-Network Pre-processing {tag('Week 8','#2d6a2d')}", f"""
<div style="display:grid;grid-template-columns:1.1fr 0.9fr;gap:0.5em 1.5em">
<div style="text-align:left;font-size:0.78em">
{done("Custom SINR codelet written in C")}
{done("Hook: mac_sched_crc_indication")}
{done("Running statistics computed inside eBPF:")}
<ul style="margin-top:0.2em">
  <li><b>Variance:</b> Welford's online algorithm<br>
      <code>E[X²] − E[X]²</code>, no stored history</li>
  <li><b>Sliding window avg:</b> 16-entry ring buffer,
      constant-time update (no inner loop)</li>
</ul>
{done("New Grafana panels: SINR variance + sliding avg")}
{done("Demonstrates bandwidth saving by processing at source")}
</div>
<div>
{img(FIGURES+"/fig_custom_codelet.png", "max-width:100%;max-height:42vh")}
</div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 10 — PHASE IV: DATASET PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase IV — AI-Ready Dataset Pipeline {tag('Week 9','#2d6a2d')}", f"""
{img(FIGURES+"/fig_dataset_overview.png", "max-width:92%;max-height:50vh")}
<p style="font-size:0.7em;color:#aaaaaa;margin-top:0.3em">
  Two automated collection scripts (stress_anomaly_collect.sh · collect_channel_realistic.sh)
  with timestamped CSV + HDF5 output. 5 621 labelled samples, 19 features, 4 anomaly classes.
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 11 — KEY RESULT: HOOK LATENCY
# ══════════════════════════════════════════════════════════════════════════════
S("Key Finding — Scheduler Fault Signature", f"""
{img(PS+"/01_hook_latency_comparison.png", "max-width:92%;max-height:52vh")}
<div style="font-size:0.72em;padding:0.4em 1em;background:#2a1a1a;border-left:4px solid #cc3333;border-radius:4px;margin-top:0.4em">
  <b>hook_p99_us_fapi_ul</b> spikes to &gt;7 000 µs during scheduler demotion
  (RT→BATCH) — <b>7× the 1 ms slot budget</b>. Standard metrics see only a minor MCS drop.
  This metric has no equivalent in any standard 5G monitoring interface.
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 12 — ANOMALY HEATMAP
# ══════════════════════════════════════════════════════════════════════════════
S("Anomaly Heatmap — All 23 Stress Scenarios", f"""
{img(PS+"/04_anomaly_heatmap.png", "max-width:92%;max-height:56vh")}
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 13 — CHANNEL SCENARIOS
# ══════════════════════════════════════════════════════════════════════════════
S("Channel Dataset — Realistic RF Conditions", f"""
{img(PC+"/channel_summary.png", "max-width:92%;max-height:56vh")}
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 14 — THROUGHPUT COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
S("Janus vs Standard — Throughput Explained", f"""
{img(FIGURES+"/fig_throughput_stack.png", "max-width:92%;max-height:55vh")}
<p style="font-size:0.7em;color:#aaaaaa">
  ~1.95× throughput difference between Janus (application layer) and Standard (MAC layer) —
  caused by protocol header overhead and scheduling signalling, not a measurement error.
  Radio metrics (SINR, MCS, CQI) agree with r &gt; 0.88.
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 15 — PHASE V STATUS
# ══════════════════════════════════════════════════════════════════════════════
S(f"Phase V — Current Status {tag('Weeks 10–12','#7a6000')}", f"""
<div style="font-size:0.82em;display:grid;grid-template-columns:1fr 1fr;gap:0.5em 2em;text-align:left">
<div>
<b style="color:#5dd35d">Week 10 — Validation</b><br>
{done("Datasets validated (no gaps, correct labels)")}
{done("Train/test split verified (scenario-based)")}
{done("Feature scaler computed and stored")}<br><br>

<b style="color:#f0c060">Week 11 — Thesis Writing</b><br>
{done("System architecture section")}
{done("Telemetry pipeline description")}
{done("jBPF vs standard comparison (with live data)")}
{inprog("Dataset + evaluation chapter")}
{inprog("Conclusion + future work")}<br><br>

<b style="color:#888888">Week 12 — Final Polish</b><br>
{todo("Code cleanup and final README")}
{todo("Presentation slides (this!)")}
{todo("Thesis submission")}
</div>
<div>
<b style="color:#aaaadd">Deliverables Checklist</b>
<ul style="font-size:0.88em">
  <li>{done("Code repo (codelets, scripts, pipeline)")}</li>
  <li>{done("AI-ready datasets (CSV + HDF5)")}</li>
  <li>{done("Setup guide (PROJECT_REFERENCE.md)")}</li>
  <li>{done("Anomaly collection report")}</li>
  <li>{done("Janus vs Standard comparison doc")}</li>
  <li>{done("Custom codelet documentation")}</li>
  <li>{inprog("Bachelor Thesis Report")}</li>
  <li>{inprog("Final presentation slides")}</li>
</ul>
</div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 16 — SUMMARY OF CONTRIBUTIONS
# ══════════════════════════════════════════════════════════════════════════════
S("Summary of Contributions", """
<ol style="font-size:0.8em;text-align:left;max-width:88%;margin:auto">
  <li style="margin-bottom:0.45em">
    <b>Full 5G NR telemetry pipeline</b> — 22 jBPF hook points across MAC/FAPI/RLC/PDCP/Control,
    producing 17 telemetry schemas at 1 ms granularity, with 36-panel Grafana dashboard
  </li>
  <li style="margin-bottom:0.45em">
    <b>ZMQ channel broker</b> — GRC Python broker injecting AWGN, Rician/Rayleigh fading,
    EPA/EVA/ETU profiles, CW interference, CFO, and burst drops with live QT GUI
  </li>
  <li style="margin-bottom:0.45em">
    <b>Two labelled AI-ready datasets</b> — 5 621 samples × 19 features, 4 anomaly classes,
    collected under 35 distinct scenarios (23 stress + 12 channel), scenario-based train/test split
  </li>
  <li style="margin-bottom:0.45em">
    <b>Janus vs Standard evaluation</b> — live side-by-side comparison showing hook latency
    uniquely identifies scheduler faults invisible to the standard metrics channel
  </li>
  <li style="margin-bottom:0.45em">
    <b>Custom in-network codelet</b> — SINR variance and sliding window average computed
    inside the eBPF program at 1 ms granularity with no userspace post-processing
  </li>
</ol>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 17 — CLOSING
# ══════════════════════════════════════════════════════════════════════════════
SR("""
  <h2 style="color:#aaaadd">Thank you</h2>
  <p style="color:#888888;margin-top:1.5em;font-size:0.9em">Questions?</p>
  <div style="margin-top:2em;font-size:0.72em;color:#888888;text-align:left;
       max-width:72%;margin-left:auto;margin-right:auto;
       padding:0.8em 1.2em;background:#1a1a2a;border-radius:8px;line-height:1.8">
    <b>Repository:</b> github.com/MaximBitiu1/srsran-telemetry-pipeline<br>
    <b>Pipeline:</b> srsRAN Project (jBPF fork) · jrtc · ZMQ GRC broker · InfluxDB 1.x · Grafana<br>
    <b>Dataset:</b> 5 621 samples · 19 features · 4 classes · 35 scenarios<br>
    <b>Overhead:</b> ~3.3% of 1 CPU core at 25 Mbps load
  </div>
""", cls="title-slide")

# ══════════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
slides_html = "\n".join(SLIDES)

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Midterm Report — Real-Time Telemetry in Open AI RAN using Microsoft Janus</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/theme/night.min.css">
<style>
  .reveal h1 {{ font-size:1.55em; }}
  .reveal h2 {{ font-size:1.1em; color:#aaaadd;
                border-bottom:1px solid #333355; padding-bottom:0.2em; margin-bottom:0.55em; }}
  .reveal ul, .reveal ol {{ text-align:left; margin-left:1.2em; }}
  .reveal li {{ margin-bottom:0.25em; line-height:1.5; }}
  .reveal code {{ background:#1e1e3a; padding:1px 5px; border-radius:3px;
                  font-size:0.87em; color:#b0d0ff; }}
  .reveal table {{ font-size:0.85em; }}
  .reveal td, .reveal th {{ padding:3px 8px; }}
  .title-slide h1 {{ color:#c8c8ff; }}
  .reveal section {{ padding:0.4em 1.2em; }}
</style>
</head>
<body>
<div class="reveal">
  <div class="slides">
{slides_html}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.min.js"></script>
<script>
  Reveal.initialize({{
    hash: true, slideNumber: 'c/t',
    controls: true, progress: true,
    center: true, transition: 'slide', transitionSpeed: 'fast',
  }});
</script>
</body>
</html>"""

with open(OUT, "w") as f:
    f.write(HTML)

print(f"Saved: {OUT}")
print(f"Slides: {len(SLIDES)}")
print(f"Open:   xdg-open {OUT}")
