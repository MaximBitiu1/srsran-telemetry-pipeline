"""
Generate a self-contained HTML presentation (reveal.js CDN) for the midterm
progress report of the srsRAN 5G NR jBPF Telemetry Thesis Project.

Usage:  python3 scripts/generate_presentation.py
Output: docs/MIDTERM_PRESENTATION.html
"""

import base64
import os
import json

ROOT = os.path.dirname(os.path.abspath(__file__)) + "/.."
FIGURES = ROOT + "/docs/figures"
PLOTS_STRESS = ROOT + "/datasets/stress_anomaly/plots"
PLOTS_CHANNEL = ROOT + "/datasets/channel/plots"
OUT = ROOT + "/docs/MIDTERM_PRESENTATION.html"


def b64(path):
    """Embed an image as a base64 data URI so the HTML is self-contained."""
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "image/png")
        return f"data:{mime};base64,{data}"
    except FileNotFoundError:
        return ""


def img(path, style="max-width:90%;max-height:60vh;"):
    src = b64(path)
    if not src:
        return f'<p style="color:#cc4444">[image not found: {os.path.basename(path)}]</p>'
    return f'<img src="{src}" style="{style}">'


# ── Load class distribution from class_map.json + dataset sizes ─────────────
CLASS_MAP = {0: "normal", 1: "scheduler_fault", 2: "traffic_flood", 3: "channel_degradation"}
COUNTS = {0: 2063, 1: 462, 2: 936, 3: 2160}   # from combined_labelled.csv

SLIDES = []

def slide(title, content, extra_class=""):
    SLIDES.append(f"""
<section class="{extra_class}">
  <h2>{title}</h2>
  {content}
</section>""")

def slide_raw(content, extra_class=""):
    SLIDES.append(f"""
<section class="{extra_class}">
  {content}
</section>""")

# ══════════════════════════════════════════════════════════════════════════════
# TITLE SLIDE
# ══════════════════════════════════════════════════════════════════════════════
slide_raw("""
  <h1 style="font-size:1.8em;line-height:1.3">
    Runtime eBPF Telemetry for<br>
    5G NR Anomaly Detection
  </h1>
  <h3 style="color:#aaaadd;margin-top:0.5em">Midterm Progress Report</h3>
  <p style="margin-top:2em;color:#cccccc">
    Maxim Bitiu — Thesis Project<br>
    <span style="font-size:0.8em">srsRAN Project + jBPF · ZMQ Virtual Radio · InfluxDB · Grafana</span>
  </p>
  <p style="font-size:0.7em;color:#888888;margin-top:2em">April 2026</p>
""", extra_class="title-slide")

# ══════════════════════════════════════════════════════════════════════════════
# MOTIVATION
# ══════════════════════════════════════════════════════════════════════════════
slide("Motivation", """
<ul>
  <li>5G NR gNB software is a <b>complex real-time system</b> — anomalies can come from the radio channel <em>or</em> the infrastructure (OS scheduler, memory pressure, traffic overload)</li>
  <li>Standard srsRAN Grafana dashboard provides <b>~1 s MAC-layer aggregates</b> only — insufficient to distinguish fault types</li>
  <li><b>eBPF</b> (extended Berkeley Packet Filter) allows zero-copy instrumentation of any kernel or userspace function at runtime, without modifying source code</li>
  <li><b>jBPF</b> extends eBPF to userspace gNB software, enabling 1 ms per-slot telemetry from 22 function call sites</li>
  <li><b>Research question:</b> Can jBPF hook telemetry distinguish infrastructure faults from channel impairments in a 5G NR system?</li>
</ul>
""")

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
slide("System Architecture", f"""
{img(FIGURES + "/fig_system_architecture.png")}
<p style="font-size:0.65em;color:#aaaaaa">
  Full pipeline on a single Ubuntu 22.04 machine — no physical RF hardware
</p>
""")

slide("Telemetry Data Flow", f"""
{img(FIGURES + "/fig_telemetry_flow.png")}
<ul style="font-size:0.75em;margin-top:0.5em">
  <li>~60 eBPF codelets fire on every function call — 1 ms per-slot granularity</li>
  <li>Protobuf serialised → decoder → <code>telemetry_to_influxdb.py</code> → InfluxDB 1.x</li>
  <li>End-to-end latency to Grafana: ~2–5 s (InfluxDB write interval + refresh)</li>
</ul>
""")

# ══════════════════════════════════════════════════════════════════════════════
# CHANNEL BROKER
# ══════════════════════════════════════════════════════════════════════════════
slide("ZMQ Channel Broker", f"""
{img(FIGURES + "/fig_channel_broker.png")}
<p style="font-size:0.7em;color:#cccccc">
  GRC Python broker intercepts IQ samples between gNB and srsUE — injects calibrated RF impairments
  without modifying either endpoint
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# JBPF HOOKS
# ══════════════════════════════════════════════════════════════════════════════
slide("jBPF Hook Coverage — 17 Telemetry Schemas", """
<div style="font-size:0.72em;display:grid;grid-template-columns:1fr 1fr;gap:0.3em 2em;text-align:left">
  <div>
    <b style="color:#9b8fd6">MAC Layer</b><br>
    mac_harq_stats — MCS, retransmissions, HARQ state<br>
    mac_crc_stats — SINR, CRC pass/fail rate<br>
    mac_bsr_stats — UE uplink buffer occupancy<br>
    mac_uci_stats — CQI, timing advance<br>
    fapi_dl/ul_config — per-slot scheduler decisions<br>
    fapi_crc_stats — PHY-layer CRC events
  </div>
  <div>
    <b style="color:#6ab4a8">RLC / PDCP</b><br>
    rlc_ul/dl_stats — SDU latency, retx bytes<br>
    pdcp_ul/dl_stats — per-bearer byte counters<br><br>
    <b style="color:#e87722">Control Plane</b><br>
    rach_stats — per-RACH-attempt SNR + TA<br>
    rrc_ue_procedure — procedure timing<br>
    ngap_procedure — core network round-trip
  </div>
</div>
<div style="margin-top:0.8em;padding:0.5em;background:#2a2a4a;border-radius:8px;font-size:0.72em">
  <b style="color:#f0c060">jbpf_out_perf_list</b> — execution latency of each hook (p50/p90/p95/p99/max)
  at every 1 ms slot. <em>This schema has no equivalent in standard monitoring.</em>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# jBPF VS STANDARD
# ══════════════════════════════════════════════════════════════════════════════
slide("jBPF vs Standard Metrics", f"""
{img(FIGURES + "/fig_jbpf_vs_standard.png")}
""")

slide("CPU Overhead — Measured from Live Telemetry", f"""
{img(FIGURES + "/fig_cpu_overhead.png")}
<p style="font-size:0.7em;color:#cccccc">
  Overhead computed directly from <code>jbpf_out_perf_list</code> — no external profiler needed.
  <b>Total: ~3.3% of one CPU core</b> at 25 Mbps load. Dominant hooks are the data-path ones
  (RLC UL, PDCP UL, FAPI). Event hooks (RACH, RRC, NGAP) contribute &lt;0.03%.
</p>
""")

# ══════════════════════════════════════════════════════════════════════════════
# DATASETS
# ══════════════════════════════════════════════════════════════════════════════
slide("Datasets Collected", f"""
{img(FIGURES + "/fig_dataset_overview.png")}
""")

slide("Stress Anomaly Dataset — 23 Scenarios", """
<div style="font-size:0.72em;display:grid;grid-template-columns:1fr 1fr;gap:0.2em 1.5em;text-align:left">
  <div>
    <b style="color:#2e8b57">Normal (label 0)</b><br>
    Baseline clean, CPU pinned 50–95%, memory 40–80%,
    CPU limit 300–600%, RT preempt competitor, cpulimit+mem<br><br>
    <b style="color:#b22222">Scheduler Fault (label 1)</b><br>
    RT→BATCH demotion (threads, +CPU),
    RT→OTHER demotion,
    demote+traffic flood
  </div>
  <div>
    <b style="color:#e65c00">Traffic Flood (label 2)</b><br>
    UDP 100 M/150 M, TCP, netem delay,
    burst aggressive, netem burst, RT preempt+traffic<br><br>
    <b style="color:#1a6faf">Channel Degradation (label 3)</b><br>
    10 channel scenarios (see next slide)
  </div>
</div>
<p style="margin-top:0.8em;font-size:0.7em">
  2 892 rows × 49 features (stress_features.csv) · ~120 s per scenario
</p>
""")

slide("Key Result — Hook Latency Discriminates Scheduler Faults",
      img(PLOTS_STRESS + "/01_hook_latency_comparison.png"))

slide("Anomaly Heatmap — All 23 Scenarios",
      img(PLOTS_STRESS + "/04_anomaly_heatmap.png"))

slide("Channel Dataset — 12 Realistic RF Scenarios", """
<div style="font-size:0.72em;display:grid;grid-template-columns:1fr 1fr;gap:0.3em 2em;text-align:left">
  <div>
    <b style="color:#2e8b57">Baseline</b><br>
    B1 — Indoor LOS (clean)<br>
    B2 — Pedestrian NLOS (EPA)<br><br>
    <b style="color:#1a6faf">Time-varying / Drive-by</b><br>
    T1 — Drive-by vehicular (EPA, Doppler 5 Hz)<br>
    T2 — High-speed mobility (EVA, Doppler 20 Hz)<br>
    T3 — Rician flat fading (K=3 dB)<br>
    T4 — Rayleigh flat fading<br>
    T5 — EPA Rayleigh high Doppler
  </div>
  <div>
    <b style="color:#8b6914">Steady Impairment</b><br>
    S1 — Cell edge + CW interference<br>
    S2 — Deep Rayleigh fade (normal label)<br>
    S3 — High-speed train (EPA)<br><br>
    <b style="color:#6a0dad">RLF Cycles</b><br>
    L1 — RLF cycle, clean channel<br>
    L2 — RLF cycle, degraded EPA<br><br>
    2 729 rows × 49 features (channel_features.csv)
  </div>
</div>
""")

slide("Channel Scenarios — Overview",
      img(PLOTS_CHANNEL + "/channel_summary.png"))

# ══════════════════════════════════════════════════════════════════════════════
# ML-READY DATASET
# ══════════════════════════════════════════════════════════════════════════════
slide("Finalised ML-Ready Dataset", """
<div style="font-size:0.78em">
<table style="width:90%;margin:auto;border-collapse:collapse">
<tr style="background:#333355;color:white">
  <th style="padding:6px 12px;text-align:left">File</th>
  <th style="padding:6px 12px;text-align:right">Rows</th>
  <th style="padding:6px 12px">Description</th>
</tr>
<tr style="background:#22223a">
  <td><code>combined_labelled.csv</code></td><td style="text-align:right">5 621</td>
  <td>Both datasets merged, 4-class labels, 26 cols</td>
</tr>
<tr style="background:#2a2a42">
  <td><code>train_features.csv</code></td><td style="text-align:right">4 487</td>
  <td>Scenario-based split (stratified)</td>
</tr>
<tr style="background:#22223a">
  <td><code>test_features.csv</code></td><td style="text-align:right">1 134</td>
  <td>Held-out scenarios per class</td>
</tr>
<tr style="background:#2a2a42">
  <td><code>feature_scaler.json</code></td><td style="text-align:right">—</td>
  <td>Min/max scaler parameters (19 features)</td>
</tr>
</table>
</div>
<div style="margin-top:0.8em;font-size:0.72em;text-align:left;max-width:80%;margin-left:auto;margin-right:auto">
<b>19 features:</b>
hook_p99_us (7 hooks) · hook_max_us_fapi_ul · harq_mcs_avg · harq_mcs_min ·
harq_cons_retx · harq_fail_rate · crc_sinr_avg · crc_harq_fail ·
crc_success_rate · bsr_kb · rlc_throughput_kb · rlc_lat_avg_us · rlc_lat_max_us
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM CODELET
# ══════════════════════════════════════════════════════════════════════════════
slide("Custom SINR Codelet — In-Network Analytics", """
<ul style="font-size:0.8em">
  <li>Implemented a custom jBPF codelet for <code>fapi_ul_tti_request</code></li>
  <li>Computes two running statistics <b>inside the eBPF program</b> (no userspace post-processing):
    <ul>
      <li><b>Sliding window average</b> — SINR over last N=10 slots (circular buffer)</li>
      <li><b>Running variance</b> — Welford's online algorithm, no stored history</li>
    </ul>
  </li>
  <li>Both values streamed via jBPF output channel → Decoder → InfluxDB → Grafana</li>
  <li>Demonstrates that <b>lightweight anomaly detection logic can run inside the gNB itself</b>,
      with sub-ms latency and no additional infrastructure</li>
</ul>
<div style="margin-top:0.8em;padding:0.5em 1em;background:#1a2a1a;border-left:4px solid #2e8b57;
     font-size:0.72em;text-align:left;border-radius:4px">
  Source: <code>jrtc-apps/codelets/custom_sinr_codelet/</code><br>
  Documentation: <code>docs/custom-codelet/CUSTOM_SINR_CODELET.md</code>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# RESULTS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
slide("Key Findings So Far", """
<ol style="font-size:0.8em;text-align:left;max-width:85%;margin:auto">
  <li style="margin-bottom:0.5em">
    <b>Hook latency is the only discriminator for infrastructure faults.</b>
    <code>hook_p99_us_fapi_ul</code> spikes to &gt;7 000 µs during scheduler demotion
    (7× the 1 ms slot budget), while MCS and SINR show only a minor, channel-like degradation.
    Standard metrics cannot see this at all.
  </li>
  <li style="margin-bottom:0.5em">
    <b>Standard metrics confirm radio-layer readings.</b>
    SINR, MCS, CQI, and BLER agree with jBPF equivalents (r &gt; 0.88). Throughput
    numbers differ by 10–15% due to measuring at different protocol layers — expected, not a bug.
  </li>
  <li style="margin-bottom:0.5em">
    <b>jBPF overhead is acceptable.</b>
    ~3.3% of one CPU core at 25 Mbps load. Overhead is proportional to traffic,
    dominated by the data-path hooks (RLC UL, PDCP UL, FAPI).
  </li>
  <li style="margin-bottom:0.5em">
    <b>Two labelled datasets ready.</b>
    5 621 samples, 19 features, 4 classes. Scenario-based train/test split.
    Feature scaler stored for ML pipeline ingestion.
  </li>
  <li>
    <b>In-network analytics demonstrated.</b>
    Sliding window SINR average and variance computed inside the eBPF codelet
    at 1 ms granularity — no userspace compute required.
  </li>
</ol>
""")

# ══════════════════════════════════════════════════════════════════════════════
# NEXT STEPS
# ══════════════════════════════════════════════════════════════════════════════
slide("Remaining Work", """
<div style="font-size:0.8em;display:grid;grid-template-columns:1fr 1fr;gap:0.5em 2em;text-align:left">
  <div>
    <b style="color:#f0c060">Task 2 — Live Comparison (80% done)</b><br>
    Run both telemetry channels simultaneously during a scheduler demotion event,
    generate side-by-side plots showing what each channel sees.<br><br>
    <b style="color:#aaddaa">Task 4 — Thesis Report</b><br>
    Write up all findings: architecture, datasets, comparison, overhead analysis,
    codelet math demonstration.
  </div>
  <div>
    <b style="color:#aaaadd">Possible Extensions</b><br>
    · Train a lightweight classifier (RF / LSTM) on the collected dataset<br>
    · Extend custom codelet to compute per-hook anomaly scores in-network<br>
    · Test with multiple UEs or higher traffic loads<br>
    · Evaluate overhead at varying traffic rates (10 / 25 / 50 Mbps)
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# CLOSING
# ══════════════════════════════════════════════════════════════════════════════
slide_raw("""
  <h2>Thank you</h2>
  <p style="color:#aaaadd;font-size:0.9em;margin-top:1.5em">Questions?</p>
  <div style="margin-top:2em;font-size:0.7em;color:#888888;text-align:left;
       max-width:70%;margin-left:auto;margin-right:auto;
       padding:0.8em;background:#1a1a2a;border-radius:8px">
    <b>Repository:</b> github.com/MaximBitiu1/srsran-telemetry-pipeline<br>
    <b>Pipeline:</b> srsRAN Project (jBPF fork) · jrtc · ZMQ channel broker · InfluxDB 1.x · Grafana<br>
    <b>Dataset:</b> 5 621 samples · 19 features · 4 anomaly classes · scenario-based split
  </div>
""", extra_class="title-slide")

# ══════════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
slides_html = "\n".join(SLIDES)

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Midterm Progress Report — srsRAN 5G NR jBPF Telemetry</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.min.css">
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/theme/night.min.css">
<style>
  .reveal h1 {{ font-size: 1.6em; }}
  .reveal h2 {{ font-size: 1.15em; color: #aaaadd; border-bottom: 1px solid #444466;
                padding-bottom: 0.2em; margin-bottom: 0.6em; }}
  .reveal ul, .reveal ol {{ text-align: left; margin-left: 1.5em; }}
  .reveal li {{ margin-bottom: 0.3em; line-height: 1.5; }}
  .reveal code {{ background: #1e1e3a; padding: 2px 6px; border-radius: 4px;
                  font-size: 0.88em; color: #b0d0ff; }}
  .reveal table {{ font-size: 0.85em; }}
  .reveal td, .reveal th {{ padding: 4px 10px; }}
  .title-slide h1 {{ color: #c8c8ff; }}
  .reveal section {{ padding: 0.5em 1.5em; }}
  .reveal .slides {{ text-align: center; }}
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
    hash: true,
    slideNumber: 'c/t',
    controls: true,
    progress: true,
    center: true,
    transition: 'slide',
    transitionSpeed: 'fast',
  }});
</script>
</body>
</html>"""

with open(OUT, "w") as f:
    f.write(HTML)

print(f"Saved {OUT}")
print(f"Total slides: {len(SLIDES)}")
print(f"Open in browser: file://{OUT}")
