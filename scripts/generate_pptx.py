"""
Generate a PowerPoint (.pptx) midterm presentation for the srsRAN jBPF thesis.
Structured to match the 12-week Bachelor Project Plan.
Target: 20 minutes (~17 content slides at ~1–1.5 min each).

Usage:  python3 scripts/generate_pptx.py
Output: docs/MIDTERM_PRESENTATION.pptx
"""

import os, io
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import pptx.oxml.ns as nsmap
from lxml import etree

# ── paths ──────────────────────────────────────────────────────────────────
ROOT   = os.path.dirname(os.path.abspath(__file__)) + "/.."
FIG    = ROOT + "/docs/figures"
PS     = ROOT + "/datasets/stress_anomaly/plots"
PC     = ROOT + "/datasets/channel/plots"
OUT    = ROOT + "/docs/MIDTERM_PRESENTATION.pptx"

# ── colour palette ──────────────────────────────────────────────────────────
NAVY   = RGBColor(0x1a, 0x1a, 0x3a)   # slide background
BLUE   = RGBColor(0x1a, 0x6f, 0xaf)
GREEN  = RGBColor(0x2e, 0x8b, 0x57)
PURPLE = RGBColor(0x6a, 0x0d, 0xad)
ORANGE = RGBColor(0xe6, 0x5c, 0x00)
RED    = RGBColor(0xb2, 0x22, 0x22)
GOLD   = RGBColor(0x8b, 0x69, 0x14)
WHITE  = RGBColor(0xff, 0xff, 0xff)
LGREY  = RGBColor(0xcc, 0xcc, 0xdd)
YELLOW = RGBColor(0xf0, 0xc0, 0x60)
TEAL   = RGBColor(0x1a, 0x8c, 0x8c)

# slide dimensions: 16:9
W = Inches(13.33)
H = Inches(7.5)

prs = Presentation()
prs.slide_width  = W
prs.slide_height = H

BLANK = prs.slide_layouts[6]   # completely blank layout


# ── helpers ────────────────────────────────────────────────────────────────

def new_slide():
    return prs.slides.add_slide(BLANK)

def bg(slide, color=NAVY):
    """Set slide background colour."""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color

def txbox(slide, text, x, y, w, h,
          size=18, bold=False, color=WHITE, align=PP_ALIGN.LEFT,
          italic=False, wrap=True):
    """Add a text box. Returns the text frame."""
    tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf.text_frame.word_wrap = wrap
    p = tf.text_frame.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return tf

def txbox_multi(slide, lines, x, y, w, h, size=16, color=WHITE, indent=False):
    """Add a text box with multiple bullet lines."""
    tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf.text_frame.word_wrap = True
    first = True
    for bullet, line in lines:
        if first:
            p = tf.text_frame.paragraphs[0]
            first = False
        else:
            p = tf.text_frame.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        if bullet:
            p.level = 1 if indent else 0
        run = p.add_run()
        run.text = ("  • " if bullet else "") + line
        run.font.size = Pt(size)
        run.font.color.rgb = color
    return tf

def rect(slide, x, y, w, h, fill_color, text="", tsize=14, tbold=False, tcolor=WHITE,
         line_color=None, radius=0):
    """Add a filled rectangle with optional label."""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(1.5)
    else:
        shape.line.fill.background()
    if text:
        tf = shape.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = text
        run.font.size = Pt(tsize)
        run.font.bold = tbold
        run.font.color.rgb = tcolor
    return shape

def img(slide, path, x, y, w, h=None):
    """Add image at position. h=None → auto aspect ratio."""
    if not os.path.exists(path):
        rect(slide, x, y, w, h or 1.5, RED, f"[missing: {os.path.basename(path)}]", 10)
        return
    if h:
        slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    else:
        slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w))

def divider(slide, y, color=BLUE):
    """Thin horizontal rule."""
    ln = slide.shapes.add_shape(1, Inches(0.5), Inches(y), Inches(12.33), Inches(0.03))
    ln.fill.solid()
    ln.fill.fore_color.rgb = color
    ln.line.fill.background()

def slide_header(slide, title, subtitle="", title_color=WHITE):
    """Standard slide header: coloured rule + title."""
    rect(slide, 0, 0, 13.33, 1.0, BLUE)
    txbox(slide, title, 0.3, 0.08, 12.5, 0.75, size=28, bold=True,
          color=title_color, align=PP_ALIGN.LEFT)
    if subtitle:
        txbox(slide, subtitle, 0.3, 0.72, 12.5, 0.35, size=13,
              color=LGREY, italic=True)

def tag_rect(slide, label, x, y, w=1.4, h=0.28, color=GREEN):
    rect(slide, x, y, w, h, color, label, tsize=11, tbold=True)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl, NAVY)
rect(sl, 0, 0, 13.33, 7.5, RGBColor(0x0d, 0x0d, 0x22))
rect(sl, 0, 2.5, 13.33, 0.06, BLUE)
rect(sl, 0, 4.8, 13.33, 0.06, BLUE)

txbox(sl, "Real-Time Telemetry in Open AI RAN", 0.5, 1.1, 12.3, 1.2,
      size=38, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
txbox(sl, "using Microsoft Janus (jBPF)", 0.5, 2.15, 12.3, 0.7,
      size=26, bold=False, color=LGREY, align=PP_ALIGN.CENTER)
txbox(sl, "Midterm Progress Report", 0.5, 3.0, 12.3, 0.55,
      size=20, italic=True, color=YELLOW, align=PP_ALIGN.CENTER)
txbox(sl, "Maxim Bitiu   ·   Bachelor Thesis   ·   April 2026",
      0.5, 4.95, 12.3, 0.5, size=16, color=LGREY, align=PP_ALIGN.CENTER)
txbox(sl, "srsRAN Project  ·  jBPF / Microsoft Janus  ·  ZMQ Virtual Radio  ·  InfluxDB  ·  Grafana",
      0.5, 5.5, 12.3, 0.4, size=13, color=RGBColor(0x88, 0x88, 0xaa),
      align=PP_ALIGN.CENTER)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 2 — MOTIVATION
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Why Build This?",
             "The problem with standard 5G network monitoring")

txbox_multi(sl, [
    (False, "Standard 5G monitoring gives you ~1-second averages at the MAC layer only:"),
    (True,  '"MCS dropped from 27 to 22" — but why? Radio problem? Scheduler overloaded? Traffic flood?'),
    (True,  "No way to tell from standard metrics alone"),
    (False, ""),
    (False, "eBPF (extended Berkeley Packet Filter) lets us inject probes into any running program:"),
    (True,  "Zero kernel changes — probes load and unload at runtime"),
    (True,  "Per-event granularity at every 1 ms radio slot"),
    (True,  "Multiple protocol layers simultaneously"),
    (False, ""),
    (False, "Microsoft Janus (jBPF) extends eBPF to userspace gNB software:"),
    (True,  "Hook directly into the srsRAN gNB source code at 22 function call sites"),
    (True,  "Capture microsecond-level events invisible to any standard interface"),
], 0.4, 1.1, 8.5, 5.8, size=15)

rect(sl, 9.2, 1.2, 3.8, 5.5, RGBColor(0x10, 0x10, 0x2a),
     line_color=BLUE)
txbox(sl, "Research Question", 9.3, 1.35, 3.6, 0.4, size=13, bold=True, color=YELLOW)
txbox(sl, "Can jBPF hook telemetry distinguish infrastructure faults from channel impairments in a live 5G NR system?",
      9.3, 1.8, 3.5, 2.5, size=13, color=WHITE)
txbox(sl, "Answer: Yes — and the standard metrics channel cannot do this at all.",
      9.3, 5.0, 3.5, 1.3, size=12, bold=True, color=GREEN)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 3 — SYSTEM OVERVIEW (WHAT WE BUILT)
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "What We Built",
             "A complete 5G NR telemetry pipeline — no physical radio hardware required")

img(sl, FIG + "/fig_system_architecture.png", 0.3, 1.1, 12.7, 5.7)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 4 — BAREMETAL INSTALLATION CHALLENGES
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Getting It to Run — Baremetal Installation Challenges",
             "Several non-trivial fixes were needed before any telemetry could flow")

# Left column
txbox(sl, "Challenge 1: eBPF Verifier Failures", 0.4, 1.15, 6.1, 0.4,
      size=15, bold=True, color=YELLOW)
txbox_multi(sl, [
    (True, "All 10 MAC codelets had eBPF verifier errors and refused to load"),
    (True, "Hash map relocation types didn't match runtime expectations"),
    (True, "JBPF_HASHMAP_CLEAR loops rejected (too complex for verifier)"),
    (True, "Fix: corrected map definitions + removed clear loops → stats now cumulative"),
], 0.4, 1.55, 6.1, 2.0, size=13)

txbox(sl, "Challenge 2: jrtc-ctl Bug — HARQ Schema Collision", 0.4, 3.65, 6.1, 0.4,
      size=15, bold=True, color=YELLOW)
txbox_multi(sl, [
    (True, "DL and UL HARQ share the same .proto schema name"),
    (True, "jrtc-ctl's map[string][]byte overwrote DL with UL at registration"),
    (True, 'Fix: changed to map[string][][]byte + append() in Go source'),
], 0.4, 4.1, 6.1, 1.7, size=13)

txbox(sl, "Challenge 3: Context Cancellation Race", 0.4, 5.85, 6.1, 0.4,
      size=15, bold=True, color=YELLOW)
txbox_multi(sl, [
    (True, "errgroup context cancelled phase-2 codelet load when phase-1 (decoder) finished"),
    (True, "Fix: split into two sequential errgroups with independent contexts"),
], 0.4, 6.25, 6.1, 0.9, size=13)

# Right column
txbox(sl, "Challenge 4: gNB Config YAML Keys", 6.8, 1.15, 6.1, 0.4,
      size=15, bold=True, color=YELLOW)
txbox_multi(sl, [
    (True, "enable_json_metrics and enable_metrics_subscription do NOT exist"),
    (True, "Correct key is metrics: enable_json: true"),
    (True, "Wrong keys cause silent gNB startup failure (IPC socket never appears)"),
], 6.8, 1.55, 6.1, 1.6, size=13)

txbox(sl, "Challenge 5: IPC Socket Timing", 6.8, 3.25, 6.1, 0.4,
      size=15, bold=True, color=YELLOW)
txbox_multi(sl, [
    (True, "jrtc must start before gNB — IPC socket /tmp/jbpf/jbpf_lcm_ipc"),
    (True, "created by gNB only after connecting to jrtc shared memory"),
    (True, "Kill-9 leaves stale socket → launch script waits forever"),
    (True, "Fix: clean shutdown script + 20s timeout with permission fix"),
], 6.8, 3.65, 6.1, 2.0, size=13)

rect(sl, 6.8, 5.8, 6.1, 0.9, RGBColor(0x0a, 0x2a, 0x0a),
     "Result: after all fixes — zero missing-schema errors, all 17 streams flowing",
     tsize=13, tbold=True, tcolor=GREEN, line_color=GREEN)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 5 — JBPF HOOK COVERAGE
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "What We Hooked — 22 Instrumentation Points, 17 Schemas",
             "Coverage across every layer of the 5G gNB software stack")

layers = [
    # (x, y, w, h, label, sub, color)
    (0.3, 1.2, 2.5, 4.8, "MAC Scheduler", "", BLUE),
    (3.1, 1.2, 2.3, 4.8, "FAPI\n(PHY↔MAC)", "", RGBColor(0x0a, 0x5a, 0x8a)),
    (5.7, 1.2, 2.3, 4.8, "RLC / PDCP", "", PURPLE),
    (8.3, 1.2, 2.3, 4.8, "Control Plane\nRRC / NGAP", "", TEAL),
    (10.9, 1.2, 2.1, 4.8, "Performance\nMeta", "", RED),
]
for x, y, w, h, lbl, sub, col in layers:
    rect(sl, x, y, w, h, col, "", line_color=WHITE)
    txbox(sl, lbl, x+0.05, y+0.1, w-0.1, 0.5, size=13, bold=True, color=WHITE,
          align=PP_ALIGN.CENTER)

# MAC items
mac_items = ["harq_stats\n(MCS, retx,\nHARQ state)",
             "crc_stats\n(SINR, CRC\nsuccess rate)",
             "bsr_stats\n(UE buffer\noccupancy)",
             "uci_stats\n(CQI, SR,\nTiming advance)"]
for i, item in enumerate(mac_items):
    rect(sl, 0.35, 1.85 + i*0.9, 2.4, 0.82, RGBColor(0x0d, 0x3a, 0x6a), item,
         tsize=11, line_color=LGREY)

# FAPI items
fapi_items = ["fapi_dl_config\n(DL MCS, PRB,\nTBS per slot)",
              "fapi_ul_config\n(UL scheduler\ndecisions)",
              "fapi_crc_stats\n(PHY CRC,\nSNR hist)"]
for i, item in enumerate(fapi_items):
    rect(sl, 3.15, 1.85 + i*1.1, 2.2, 0.95, RGBColor(0x05, 0x30, 0x5a), item,
         tsize=11, line_color=LGREY)

# RLC/PDCP items
rlc_items = ["rlc_ul/dl_stats\n(SDU latency,\nretx bytes)",
             "pdcp_ul/dl_stats\n(per-bearer\nbyte counters)"]
for i, item in enumerate(rlc_items):
    rect(sl, 5.75, 1.85 + i*1.4, 2.2, 1.2, RGBColor(0x38, 0x07, 0x60), item,
         tsize=11, line_color=LGREY)

# Control items
ctrl_items = ["rach_stats\n(per-RACH SNR\n+ timing adv.)",
              "rrc_procedure\n(setup, reconfig,\nreestablishment)",
              "ngap_procedure\n(core network\nround-trip)"]
for i, item in enumerate(ctrl_items):
    rect(sl, 8.35, 1.85 + i*1.05, 2.2, 0.9, RGBColor(0x07, 0x42, 0x42), item,
         tsize=11, line_color=LGREY)

# Meta
rect(sl, 10.95, 1.85, 2.0, 2.3,
     RGBColor(0x5a, 0x10, 0x10),
     "jbpf_out_\nperf_list\n\np50/p90/\np95/p99\nper hook\n\n★ Novel metric\nno standard\nequivalent",
     tsize=11, line_color=YELLOW)

txbox(sl, "★  jbpf_out_perf_list is the ONLY signal sensitive to infrastructure faults — "
         "completely invisible to any standard 5G monitoring interface",
      0.3, 6.15, 12.7, 0.6, size=13, bold=True, color=YELLOW, align=PP_ALIGN.CENTER)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 6 — GRAFANA DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "45-Panel Real-Time Dashboard",
             "Live Grafana dashboard — every metric from every layer in one view")

txbox_multi(sl, [
    (False, "Dashboard sections:"),
    (True, "MAC layer (8 panels) — HARQ, SINR, MCS, CRC, BSR, CQI"),
    (True, "RLC / PDCP (10 panels) — SDU latency, throughput bytes, queue depth"),
    (True, "FAPI (6 panels) — per-slot scheduler decisions, PRB utilisation"),
    (True, "jBPF hook latency (8 panels) — p50/p90/p95/p99 per hook"),
    (True, "RRC / NGAP events (5 panels) — attach/detach, procedure timing"),
    (True, "UE application layer (5 panels) — iperf3 UL/DL Mbps, ping RTT, jitter, loss"),
    (True, "Summary + histograms (9 panels) — at-a-glance health"),
    (False, ""),
    (False, "Auto-refresh: 5 s  ·  InfluxDB 1.x backend  ·  InfluxQL queries"),
], 0.4, 1.15, 5.8, 5.6, size=14)

img(sl, FIG + "/fig_telemetry_flow.png", 6.3, 1.1, 6.8, 5.7)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 7 — CHANNEL BROKER
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "ZMQ Channel Broker — Simulating Real RF Conditions",
             "GRC Python broker intercepts IQ samples between gNB and UE")

img(sl, FIG + "/fig_channel_broker.png", 0.3, 1.1, 8.5, 5.6)

txbox_multi(sl, [
    (False, "Two broker implementations:"),
    (True, "C broker: AWGN + Rician/Rayleigh flat fading (fast, stable)"),
    (True, "GRC Python: + EPA/EVA/ETU 3GPP profiles, CFO, burst drops, live GUI"),
    (False, ""),
    (False, "Recommended config:"),
    (True, "K=3 dB Rician, SNR=28 dB, fd=5 Hz"),
    (True, "Pure Rayleigh crashes UE in ~2 min"),
    (False, ""),
    (False, "Processing budget:"),
    (True, "DL: 413 µs  ·  UL: 503 µs"),
    (True, "< 1 ms slot budget with 500 µs headroom"),
], 8.9, 1.2, 4.2, 5.6, size=13)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 8 — JANUS VS STANDARD: WHAT EACH SEES
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Janus vs Standard Metrics — What Each Channel Sees",
             "Live side-by-side comparison run during Week 7 evaluation")

img(sl, FIG + "/fig_jbpf_vs_standard.png", 0.3, 1.1, 12.7, 5.7)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 9 — THROUGHPUT GAP EXPLAINED
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "The 1.95× Throughput Difference — Not a Bug",
             "Both systems are correct — they measure at different protocol layers")

img(sl, FIG + "/fig_throughput_stack.png", 0.3, 1.1, 7.0, 5.6)

txbox_multi(sl, [
    (False, "iperf3 sends 10 Mbps of UDP payload."),
    (False, "The standard srsRAN dashboard reads the MAC-layer bitrate: 19.45 Mbps."),
    (False, ""),
    (False, "The extra 9.45 Mbps comes from:"),
    (True, "Protocol headers: IP (20B) + UDP (8B) + GTP-U (16B) + PDCP (3B) + RLC (2B)"),
    (True, "MAC control elements: BSR, PHR, timing advance"),
    (True, "HARQ overhead: scheduled bytes count even for retransmissions"),
    (True, "PDCCH/reference signals: resource grant signalling"),
    (False, ""),
    (False, "Radio metrics (SINR, MCS, CQI, BLER) agree with r > 0.88."),
    (False, "The mismatch is in throughput only — expected, not an error."),
], 7.5, 1.2, 5.6, 5.4, size=13)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 10 — CPU OVERHEAD
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "CPU Overhead — Measured from the Telemetry Itself",
             "jbpf_out_perf_list records hook execution time — no external profiler needed")

img(sl, FIG + "/fig_cpu_overhead.png", 0.3, 1.1, 12.7, 5.7)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 11 — ANOMALY DATASETS (ONE SLIDE OVERVIEW)
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Anomaly Datasets — 35 Scenarios, 5 621 Labelled Samples",
             "Week 9 deliverable: AI-ready CSV + HDF5 with microsecond timestamps")

img(sl, FIG + "/fig_dataset_overview.png", 0.3, 1.1, 7.5, 3.8)

# Right: key numbers
txbox_multi(sl, [
    (False, "4 anomaly classes:"),
    (True,  "normal (0) — 2 063 samples — clean baseline"),
    (True,  "scheduler_fault (1) — 462 samples — RT thread demotion"),
    (True,  "traffic_flood (2) — 936 samples — UDP/TCP flood"),
    (True,  "channel_degradation (3) — 2 160 samples — RF impairments"),
    (False, ""),
    (False, "19 features per 1-second window:"),
    (True,  "7 × hook_p99_us (per steady-state hook)"),
    (True,  "HARQ: mcs_avg, mcs_min, cons_retx, fail_rate"),
    (True,  "CRC: sinr_avg, harq_fail, success_rate"),
    (True,  "BSR: bsr_kb"),
    (True,  "RLC: throughput_kb, lat_avg_us, lat_max_us"),
], 7.9, 1.2, 5.2, 3.6, size=12)

# Bottom bar
txbox_multi(sl, [
    (False, "Scenario-based train/test split  ·  train: 4 487 rows  ·  test: 1 134 rows  ·  Feature scaler saved"),
], 0.3, 5.1, 12.7, 0.5, size=12)

# Key finding box
rect(sl, 0.3, 5.7, 12.7, 1.05, RGBColor(0x1a, 0x0a, 0x0a),
     "", line_color=RED)
txbox(sl, "Key finding: 14 of 23 stress scenarios produce signatures invisible to standard metrics.",
      0.4, 5.75, 12.5, 0.45, size=14, bold=True, color=YELLOW)
txbox(sl, "hook_p99_us_fapi_ul spikes to >7 000 µs (7× the 1 ms slot budget) during scheduler demotion "
          "while SINR/MCS remain normal — impossible to detect without hook latency.",
      0.4, 6.2, 12.5, 0.45, size=12, color=WHITE)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 12 — THE KEY RESULT: HOOK LATENCY SIGNATURE
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "The Core Result — Hook Latency Identifies Infrastructure Faults",
             "A metric that exists nowhere in standard 5G monitoring")

img(sl, PS + "/01_hook_latency_comparison.png", 0.3, 1.1, 8.5, 5.2)

txbox_multi(sl, [
    (False, "What happened:"),
    (True,  "gNB threads demoted from SCHED_FIFO:96 to SCHED_BATCH"),
    (True,  "OS scheduler deprioritises them — slot processing delayed"),
    (True,  "hook_p99_us_fapi_ul: 6 µs → 7 289 µs (1200× spike)"),
    (False, ""),
    (False, "What standard metrics show:"),
    (True,  "Slight MCS drop (looks like minor channel fading)"),
    (True,  "BSR increase (looks like congestion)"),
    (True,  "No indication of a software fault"),
    (False, ""),
    (False, "What hook latency shows:"),
    (True,  "Unmistakable spike — 7× the 1 ms slot budget"),
    (True,  "Pure infrastructure signature — SINR unchanged"),
    (True,  "No channel probe can see this"),
], 9.0, 1.2, 4.1, 5.4, size=12)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 13 — IN-NETWORK CODELET (WEEK 8)
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "In-Network Pre-Processing — Week 8 Extension",
             "Computing statistics inside the eBPF program — no userspace required")

img(sl, FIG + "/fig_custom_codelet.png", 0.3, 1.1, 8.0, 5.5)

txbox_multi(sl, [
    (False, "Custom SINR codelet (C code):"),
    (True,  "Hook: mac_sched_crc_indication — fires on every UL CRC PDU"),
    (False, ""),
    (False, "Two algorithms inside the eBPF program:"),
    (True,  "Variance: Welford online algorithm"),
    (True,  "  E[X²] − E[X]² — no stored history needed"),
    (True,  "Sliding avg: 16-entry ring buffer"),
    (True,  "  Constant time update (no inner loop)"),
    (False, ""),
    (False, "Why it matters:"),
    (True,  "Anomaly detection logic runs at the gNB itself"),
    (True,  "Sub-millisecond latency — no network hop to userspace"),
    (True,  "Bandwidth saving: send avg/variance, not every raw sample"),
    (True,  "New Grafana panels: SINR variance + sliding average"),
], 8.5, 1.2, 4.6, 5.6, size=12)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 14 — PROGRESS VS PLAN
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Progress vs 12-Week Plan",
             "All implementation phases complete — in Phase V (writing)")

phases = [
    ("Phase I\nWks 1–2\nFoundation",    "Setup 5G sim\n+ ZMQ link",   "DONE",    GREEN),
    ("Phase II\nWks 3–5\nCorelets",     "22 hooks\n17 schemas",        "DONE",    GREEN),
    ("Phase III\nWks 6–7\nEvaluation",  "Dashboard\nComparison",       "DONE",    GREEN),
    ("Phase IV\nWks 8–9\nExtension",    "Codelet math\nAI datasets",   "DONE",    GREEN),
    ("Phase V\nWks 10–12\nConclusion",  "Validation\nThesis writing",  "IN PROG", YELLOW),
]
for i, (title, sub, status, col) in enumerate(phases):
    x = 0.4 + i * 2.55
    rect(sl, x, 1.15, 2.4, 3.0, col if status == "DONE" else RGBColor(0x2a, 0x2a, 0x0a),
         line_color=col)
    txbox(sl, title, x+0.05, 1.2, 2.3, 1.3, size=12, bold=True, color=WHITE,
          align=PP_ALIGN.CENTER)
    txbox(sl, sub, x+0.05, 2.5, 2.3, 0.8, size=11, color=LGREY,
          align=PP_ALIGN.CENTER)
    rect(sl, x+0.3, 3.85, 1.8, 0.35, col if status == "DONE" else YELLOW,
         status, tsize=12, tbold=True)

# Deliverables table
txbox(sl, "Deliverables", 0.4, 4.4, 12.5, 0.4, size=16, bold=True, color=WHITE)
deliverables = [
    ("Source code (codelets, scripts, pipeline)", True),
    ("AI-ready datasets (CSV + HDF5, 5 621 samples)", True),
    ("Setup guide and all documentation", True),
    ("Anomaly collection report (35 scenarios)", True),
    ("Janus vs Standard comparison (live data)", True),
    ("Custom codelet documentation", True),
    ("Bachelor Thesis Report", False),
    ("Final presentation", False),
]
cols = [deliverables[:4], deliverables[4:]]
for ci, col_items in enumerate(cols):
    for ri, (item, done) in enumerate(col_items):
        mark = "✓" if done else "○"
        col  = GREEN if done else RGBColor(0x88, 0x88, 0x88)
        txbox(sl, f"{mark}  {item}", 0.4 + ci*6.5, 4.85 + ri*0.42,
              6.3, 0.4, size=13, color=col)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 15 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Summary of Contributions")

contributions = [
    (BLUE,   "1. Full 5G NR Telemetry Pipeline",
             "22 jBPF hook points · 17 schemas · 1 ms granularity · 45-panel Grafana dashboard"),
    (GOLD,   "2. ZMQ Channel Broker",
             "GRC Python broker: AWGN + Rician/Rayleigh + EPA/EVA/ETU + interference + time-varying scenarios"),
    (PURPLE, "3. Baremetal Installation",
             "Fixed 10 eBPF verifier failures + 2 jrtc-ctl bugs + YAML config keys to get the full stack running"),
    (GREEN,  "4. Two Labelled AI-Ready Datasets",
             "5 621 samples · 19 features · 4 classes · 35 scenarios · scenario-based train/test split"),
    (RED,    "5. Key Finding — Hook Latency as Fault Detector",
             "Only metric that distinguishes scheduler faults from channel impairments · 7× spike · invisible to standard"),
    (TEAL,   "6. Custom In-Network Codelet",
             "SINR variance + sliding window computed inside eBPF at 1 ms — no userspace post-processing"),
]
for i, (col, title, body) in enumerate(contributions):
    y = 1.1 + i * 0.98
    rect(sl, 0.3, y, 0.08, 0.75, col)
    txbox(sl, title, 0.5, y, 12.5, 0.38, size=15, bold=True, color=WHITE)
    txbox(sl, body,  0.5, y+0.35, 12.5, 0.45, size=12, color=LGREY)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 16 — WHAT REMAINS
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl)
slide_header(sl, "Remaining Work — Phase V")

txbox_multi(sl, [
    (False, "Thesis Writing (Week 11):"),
    (True,  "Chapter: System architecture and implementation"),
    (True,  "Chapter: Evaluation — jBPF vs standard comparison with live plots"),
    (True,  "Chapter: Anomaly detection — dataset description, key findings"),
    (True,  "Chapter: Conclusion and future work"),
    (False, ""),
    (False, "Optional extensions (if time permits):"),
    (True,  "Train a lightweight anomaly classifier on the collected dataset"),
    (True,  "Evaluate CPU overhead at multiple traffic rates (10/25/50 Mbps)"),
    (True,  "Extend custom codelet to output an anomaly score directly"),
], 0.4, 1.2, 6.5, 5.5, size=15)

rect(sl, 7.1, 1.2, 5.9, 5.5, RGBColor(0x10, 0x10, 0x2a), line_color=BLUE)
txbox(sl, "Hardware (USRP) Bonus", 7.2, 1.3, 5.7, 0.4, size=14, bold=True, color=YELLOW)
txbox_multi(sl, [
    (False, "Project plan explicitly designs for ZMQ simulation."),
    (False, "Hardware (USRP B210/X310) is optional bonus only."),
    (False, ""),
    (False, "If time permits after thesis draft:"),
    (True,  "Replace ZMQ with real USRP radio"),
    (True,  "Run codelets on live air interface"),
    (True,  "Compare simulated vs real-world hook latency"),
    (False, ""),
    (False, "Risk mitigation: do NOT attempt if it jeopardises the report deadline."),
], 7.2, 1.75, 5.6, 4.7, size=12)

# ══════════════════════════════════════════════════════════════════════════════
# SLIDE 17 — THANK YOU
# ══════════════════════════════════════════════════════════════════════════════
sl = new_slide()
bg(sl, RGBColor(0x0d, 0x0d, 0x22))
rect(sl, 0, 2.8, 13.33, 0.06, BLUE)
txbox(sl, "Thank You", 0.5, 1.3, 12.3, 1.1,
      size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
txbox(sl, "Questions?", 0.5, 2.3, 12.3, 0.6,
      size=22, color=LGREY, align=PP_ALIGN.CENTER)
txbox(sl, "github.com/MaximBitiu1/srsran-telemetry-pipeline",
      0.5, 3.1, 12.3, 0.45, size=16, color=LGREY, align=PP_ALIGN.CENTER)

stats = [
    ("22",     "jBPF hook\npoints"),
    ("17",     "Telemetry\nschemas"),
    ("45",     "Grafana\npanels"),
    ("5 621",  "Labelled\nsamples"),
    ("3.3%",   "CPU\noverhead"),
    ("7 000+", "µs fault\nspike"),
]
for i, (num, lbl) in enumerate(stats):
    x = 0.7 + i * 2.0
    txbox(sl, num, x, 3.8, 1.8, 0.6, size=26, bold=True, color=YELLOW,
          align=PP_ALIGN.CENTER)
    txbox(sl, lbl, x, 4.35, 1.8, 0.5, size=11, color=LGREY,
          align=PP_ALIGN.CENTER)

# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════
prs.save(OUT)
print(f"Saved: {OUT}")
print(f"Slides: {len(prs.slides)}")
