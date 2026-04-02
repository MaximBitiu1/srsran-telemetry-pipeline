#!/usr/bin/env python3
"""
compare_jbpf_vs_standard.py
=============================================
Extracts live data from both telemetry sources and produces a
side-by-side comparison table + analysis.

Sources:
  - jBPF:     InfluxDB 1.x at localhost:8086 (db: srsran_telemetry)
  - Standard: /tmp/standard_metrics.jsonl (WebSocket capture)
"""

import json
import requests
import sys
from collections import defaultdict

INFLUX_URL = "http://localhost:8086/query"
INFLUX_DB = "srsran_telemetry"
WS_FILE = "/tmp/standard_metrics.jsonl"

def query_influx(measurement, limit=5):
    q = f"SELECT * FROM {measurement} ORDER BY time DESC LIMIT {limit}"
    r = requests.get(INFLUX_URL, params={"db": INFLUX_DB, "q": q})
    data = r.json()
    try:
        series = data["results"][0]["series"][0]
        cols = series["columns"]
        rows = [dict(zip(cols, v)) for v in series["values"]]
        return rows
    except (KeyError, IndexError):
        return []

def load_standard_metrics():
    records = []
    try:
        with open(WS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        print(f"ERROR: {WS_FILE} not found. Run capture_standard_metrics.py first.")
        sys.exit(1)
    return records

def extract_ue_metrics(records):
    """Extract per-UE metrics from standard records that have ue_list."""
    ue_samples = []
    for rec in records:
        if "cells" not in rec:
            continue
        for cell in rec["cells"]:
            if "ue_list" in cell:
                for ue in cell["ue_list"]:
                    ue["timestamp"] = rec.get("timestamp", "")
                    ue["cell_metrics"] = cell.get("cell_metrics", {})
                    ue_samples.append(ue)
    return ue_samples

# ─── Main ────────────────────────────────────────────────────────────────────
print("=" * 80)
print("  jBPF vs srsRAN Standard Metrics — Live Comparison")
print("=" * 80)

# Load standard metrics
std_records = load_standard_metrics()
ue_samples = extract_ue_metrics(std_records)
print(f"\nStandard metrics: {len(std_records)} records, {len(ue_samples)} with UE data")

# Load jBPF data
jbpf_harq = query_influx("mac_harq_stats", 5)
jbpf_crc = query_influx("mac_crc_stats", 5)
jbpf_bsr = query_influx("mac_bsr_stats", 5)
jbpf_perf = query_influx("jbpf_perf", 30)
jbpf_rlc_ul = query_influx("rlc_ul_stats", 5)
jbpf_rlc_dl = query_influx("rlc_dl_stats", 5)
jbpf_pdcp_ul = query_influx("pdcp_ul_stats", 5)
jbpf_pdcp_dl = query_influx("pdcp_dl_stats", 5)
jbpf_fapi_ul = query_influx("fapi_ul_config", 5)
jbpf_fapi_dl = query_influx("fapi_dl_config", 5)
jbpf_fapi_crc = query_influx("fapi_crc_stats", 5)
jbpf_rach = query_influx("fapi_rach_stats", 5)
print(f"jBPF measurements: {sum(1 for x in [jbpf_harq, jbpf_crc, jbpf_bsr, jbpf_perf, jbpf_rlc_ul, jbpf_rlc_dl, jbpf_pdcp_ul, jbpf_pdcp_dl, jbpf_fapi_ul, jbpf_fapi_dl, jbpf_fapi_crc, jbpf_rach] if x)} active tables with data")

# ═══════════════════════════════════════════════════════════════════════════
# Section 1 — Overlapping Metrics (available in BOTH systems)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  SECTION 1: OVERLAPPING METRICS (both systems provide)")
print("=" * 80)

if ue_samples:
    s = ue_samples[-1]  # latest
    print(f"\n  Latest standard sample: {s['timestamp']}")
else:
    s = {}
    print("\n  WARNING: No UE samples in standard metrics!")

h = jbpf_harq[0] if jbpf_harq else {}
c = jbpf_crc[0] if jbpf_crc else {}
b = jbpf_bsr[0] if jbpf_bsr else {}
ru = jbpf_rlc_ul[0] if jbpf_rlc_ul else {}

print(f"\n{'Metric':<40} {'Standard (WS :8001)':<25} {'jBPF (eBPF codelets)':<25}")
print("-" * 90)

rows = [
    ("DL MCS (avg)",
     f"{s.get('dl_mcs', 'N/A')}",
     f"{h.get('avg_mcs', 'N/A'):.1f}" if h.get('avg_mcs') else "N/A"),
    ("UL MCS",
     f"{s.get('ul_mcs', 'N/A')}",
     "(in fapi_ul_config)"),
    ("PUSCH SINR (dB)",
     f"{s.get('pusch_snr_db', 'N/A'):.1f}" if s.get('pusch_snr_db') else "N/A",
     f"{c.get('avg_sinr', 'N/A'):.1f}" if c.get('avg_sinr') else "N/A"),
    ("HARQ DL OK / NOK",
     f"{s.get('dl_nof_ok', 'N/A')} / {s.get('dl_nof_nok', 'N/A')}",
     f"{h.get('tbs_count', 'N/A')} ok, {h.get('retx_count', 'N/A')} retx" if h else "N/A"),
    ("HARQ UL OK / NOK",
     f"{s.get('ul_nof_ok', 'N/A')} / {s.get('ul_nof_nok', 'N/A')}",
     f"succ={c.get('succ_tx', 'N/A')}/{c.get('cnt_tx', 'N/A')}" if c else "N/A"),
    ("CRC Success Rate (%)",
     "N/A (computed from nof_ok/nof_nok)",
     f"{c.get('tx_success_rate', 'N/A')}" if c else "N/A"),
    ("BSR (bytes)",
     f"{s.get('bsr', 'N/A')}",
     f"(in mac_bsr_stats — raw BSR index)"),
    ("DL Bitrate (bps)",
     f"{s.get('dl_brate', 'N/A'):.0f}" if s.get('dl_brate') else "N/A",
     f"(pdcp_dl: {jbpf_pdcp_dl[0].get('data_tx_bytes', 'N/A')} B/s)" if jbpf_pdcp_dl else "N/A"),
    ("UL Bitrate (bps)",
     f"{s.get('ul_brate', 'N/A'):.0f}" if s.get('ul_brate') else "N/A",
     f"(pdcp_ul: {jbpf_pdcp_ul[0].get('data_rx_bytes', 'N/A')} B/s)" if jbpf_pdcp_ul else "N/A"),
    ("Timing Advance (ns)",
     f"{s.get('ta_ns', 'N/A'):.1f}" if s.get('ta_ns') else "N/A",
     "(in fapi_rach_stats per RACH event)"),
    ("CQI",
     f"{s.get('cqi', 'N/A')}",
     "N/A (not instrumented by jBPF)"),
    ("Rank Indicator (RI)",
     f"DL={s.get('dl_ri', 'N/A')} UL={s.get('ul_ri', 'N/A')}",
     "N/A"),
]

for label, std_val, jbpf_val in rows:
    print(f"  {label:<38} {std_val:<25} {jbpf_val:<25}")

# ═══════════════════════════════════════════════════════════════════════════
# Section 2 — jBPF-ONLY Metrics (NOT available in standard)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  SECTION 2: jBPF-ONLY METRICS (NOT available in standard srsRAN)")
print("=" * 80)

# Hook latencies
perf_by_hook = defaultdict(list)
for p in jbpf_perf:
    perf_by_hook[p.get("hook", "unknown")].append(p)

print(f"\n  {'Hook Name':<35} {'p50 (ns)':<12} {'p90 (ns)':<12} {'p95':<12} {'p99 (ns)':<12} {'Max (ns)':<12} {'Invocations':<12}")
print("  " + "-" * 95)
for hook_name, samples in sorted(perf_by_hook.items()):
    s0 = samples[0]
    print(f"  {hook_name:<35} {s0.get('p50',''):<12} {s0.get('p90',''):<12} {s0.get('p95',''):<12} {s0.get('p99',''):<12} {s0.get('max_ns',''):<12} {s0.get('invocations',''):<12}")

print(f"\n  Additional jBPF-only data fields:")
print(f"  {'Measurement':<30} {'Key Fields'}")
print("  " + "-" * 60)
jbpf_only = [
    ("jbpf_perf", "per-hook p50/p90/p95/p99/max latency (ns)"),
    ("mac_harq_stats", "min_mcs, max_mcs, max_retx, tbs_bytes"),
    ("mac_crc_stats", "min_sinr, max_sinr, avg_rsrp"),
    ("rlc_ul_stats", "avg_sdu_latency (us), pdu_rx_bytes"),
    ("rlc_dl_stats", "sdu_delivered_bytes, pdu_tx_bytes"),
    ("pdcp_ul_stats", "ctrl_rx_bytes, sdu_delivered_bytes"),
    ("pdcp_dl_stats", "ctrl_tx_bytes, data_tx_bytes"),
    ("fapi_ul_config", "per-slot UL scheduler MCS/PRB/TBS"),
    ("fapi_dl_config", "per-slot DL scheduler MCS/PRB/TBS"),
    ("fapi_crc_stats", "PHY-level CRC per SFN/slot"),
    ("fapi_rach_stats", "preamble SNR + TA per RACH attempt"),
    ("rrc_events", "RRC procedure type + timing"),
    ("ngap_events", "NG-AP procedure start/complete/reset"),
    ("mac_uci_stats", "UCI HARQ-ACK/NACK details"),
]
for meas, desc in jbpf_only:
    print(f"  {meas:<30} {desc}")

# ═══════════════════════════════════════════════════════════════════════════
# Section 3 — Standard-ONLY Metrics (NOT in jBPF)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  SECTION 3: STANDARD-ONLY METRICS (NOT available in jBPF)")
print("=" * 80)

cell_m = s.get("cell_metrics", {}) if s else {}
std_only = [
    ("cqi", s.get("cqi", "N/A"), "Channel Quality Indicator"),
    ("dl_ri / ul_ri", f"{s.get('dl_ri','N/A')} / {s.get('ul_ri','N/A')}", "Rank Indicator (MIMO layers)"),
    ("dl_bs", s.get("dl_bs", "N/A"), "DL buffer status (pending bytes)"),
    ("last_phr", s.get("last_phr", "N/A"), "Last Power Headroom Report"),
    ("nof_pucch_f0f1_invalid_harqs", s.get("nof_pucch_f0f1_invalid_harqs", "N/A"), "Invalid PUCCH HARQ count"),
    ("average_latency", cell_m.get("average_latency", "N/A"), "Cell-level avg scheduling latency (us)"),
    ("max_latency", cell_m.get("max_latency", "N/A"), "Cell-level max scheduling latency (us)"),
    ("latency_histogram", str(cell_m.get("latency_histogram", "N/A"))[:40], "Scheduling latency distribution"),
    ("late_dl_harqs", cell_m.get("late_dl_harqs", "N/A"), "Late DL HARQ feedback count"),
    ("nof_failed_pdcch_allocs", cell_m.get("nof_failed_pdcch_allocs", "N/A"), "Failed PDCCH allocations"),
    ("pucch_tot_rb_usage_avg", f"{cell_m.get('pucch_tot_rb_usage_avg', 'N/A')}", "Average PUCCH RB usage"),
]
print(f"\n  {'Field':<38} {'Value':<20} {'Description'}")
print("  " + "-" * 80)
for field, val, desc in std_only:
    print(f"  {field:<38} {str(val):<20} {desc}")

# ═══════════════════════════════════════════════════════════════════════════
# Section 4 — Key Differences Summary
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  SECTION 4: KEY DIFFERENCES SUMMARY")
print("=" * 80)

print("""
  ┌────────────────────────────────┬──────────────────────┬──────────────────────┐
  │ Capability                     │ Standard (WS :8001)  │ jBPF (eBPF codelets) │
  ├────────────────────────────────┼──────────────────────┼──────────────────────┤
  │ Update rate                    │ ~1 Hz (1s aggregate) │ ~1 Hz (configurable) │
  │ Per-slot (1ms) resolution      │ NO                   │ YES (fapi_ul/dl)     │
  │ Hook function latency (p99)    │ NO                   │ YES (7 steady hooks) │
  │ Per-layer RLC/PDCP byte counts │ NO                   │ YES                  │
  │ RLC SDU latency (avg/max)      │ NO                   │ YES (avg_sdu_latency)│
  │ RACH preamble SNR + TA         │ NO                   │ YES (per-event)      │
  │ RRC/NGAP procedure events      │ NO                   │ YES (per-event)      │
  │ Infrastructure fault detection │ NO (only radio-layer)│ YES (hook latency)   │
  │ CQI / Rank Indicator           │ YES                  │ NO                   │
  │ Cell-level scheduling latency  │ YES (histogram)      │ NO (hook-level only) │
  │ PUCCH RB usage                 │ YES                  │ NO                   │
  │ Power Headroom (PHR)           │ YES                  │ NO                   │
  │ Buffer Status (dl_bs)          │ YES                  │ NO                   │
  │ CPU overhead                   │ ~0% (built-in)       │ ~3.3% (eBPF hooks)   │
  │ Requires code modification     │ NO (standard config) │ YES (jBPF codelets)  │
  │ Runtime loadable/unloadable    │ N/A (always on)      │ YES (jrtc-ctl)       │
  └────────────────────────────────┴──────────────────────┴──────────────────────┘

  KEY THESIS FINDING:
  The jBPF hook latency metric (jbpf_perf) provides visibility into
  infrastructure-level processing delays that are completely invisible to the
  standard metrics channel. For example, hook_p99_us_fapi_ul_tti_request
  spikes to 7000+ us during a scheduler demotion fault, while the standard
  metrics show only a minor MCS/BSR change indistinguishable from channel
  degradation.
""")

print("=" * 80)
print("  Comparison complete.")
print("=" * 80)
