#!/usr/bin/env python3
"""
Plot All Telemetry — comprehensive plots for all 17 codelet schemas.
Generates one PNG per codelet group with multiple subplots.

Usage:
    python3 plot_all_telemetry.py [decoder_log_file]
    
    Default: /tmp/decoder.log
"""
import json, re, os, sys
from datetime import datetime
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Configuration ────────────────────────────────────────────────────────────
LOG = sys.argv[1] if len(sys.argv) > 1 else "/tmp/decoder.log"
OUT_DIR = "/home/maxim/Desktop/plots"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Style ────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#FAFAFA",
    "axes.grid": True,
    "grid.alpha": 0.35,
    "grid.linestyle": "--",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
    "figure.dpi": 150,
})

COLORS = {
    "blue": "#1565C0", "green": "#2E7D32", "red": "#C62828",
    "orange": "#E65100", "purple": "#6A1B9A", "teal": "#00838F",
    "pink": "#AD1457", "amber": "#FF8F00", "indigo": "#283593",
    "lime": "#558B2F", "cyan": "#00695C", "brown": "#4E342E",
}

# ── Parse all records ────────────────────────────────────────────────────────
print(f"Parsing {LOG} ...")

records_by_schema = defaultdict(list)

with open(LOG, errors='replace') as f:
    for line in f:
        m = re.match(r'^time="([^"]+)".*msg="REC: (.+)"$', line.strip())
        if not m:
            continue
        ts_str, raw = m.group(1), m.group(2)
        ts = datetime.fromisoformat(ts_str)
        raw = raw.replace('\\"', '"')
        if raw.startswith('"'): raw = raw[1:]
        if raw.endswith('"'):   raw = raw[:-1]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        
        schema = data.get("_schema_proto_msg", "unknown")
        pkg = data.get("_schema_proto_package", "")
        # Disambiguate crc_stats (MAC vs FAPI)
        if schema == "crc_stats" and pkg == "fapi_gnb_crc_stats":
            schema = "fapi_crc_stats"
        
        data["_ts"] = ts
        data["_pkg"] = pkg
        records_by_schema[schema].append(data)

# Summary
total = sum(len(v) for v in records_by_schema.values())
print(f"Parsed {total} records across {len(records_by_schema)} schemas:")
for s, recs in sorted(records_by_schema.items(), key=lambda x: -len(x[1])):
    print(f"  {s}: {len(recs)}")

if total == 0:
    print("ERROR: No records parsed. Check log file path.")
    sys.exit(1)

# Time reference
all_ts = []
for recs in records_by_schema.values():
    all_ts.extend(r["_ts"] for r in recs)
t0 = min(all_ts)
t_max = (max(all_ts) - t0).total_seconds()

def rel(ts):
    return (ts - t0).total_seconds()

def safe_div(a, b, default=0):
    return a / b if b else default

plot_count = 0

# ═══════════════════════════════════════════════════════════════════════════════
# 1. MAC CRC Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("crc_stats", [])
if recs:
    print("\nPlotting 1. MAC CRC Stats...")
    fig, axs = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("MAC CRC Stats — PHY Layer Indicators", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]
        if s.get("duUeIndex", 0) == 513 and len(stats) > 1:
            s = stats[1]
        data_points.append({
            "t": rel(r["_ts"]),
            "succTx": s.get("succTx", 0),
            "cntTx": s.get("cntTx", 0),
            "harqFailure": s.get("harqFailure", 0),
            "avgSinr": safe_div(s.get("sumSinr", 0), s.get("cntSinr", 0)),
            "avgRsrp": safe_div(s.get("sumRsrp", 0), s.get("cntRsrp", 0)),
            "maxSinr": s.get("maxSinr", 0),
            "minSinr": s.get("minSinr", 0),
        })
    
    t = [d["t"] for d in data_points]
    
    # Transmissions
    axs[0].plot(t, [d["cntTx"] for d in data_points], color=COLORS["blue"], lw=2, label="Total Tx")
    axs[0].plot(t, [d["succTx"] for d in data_points], color=COLORS["green"], lw=2, ls="--", label="Successful Tx")
    axs[0].set_ylabel("Count")
    axs[0].legend(loc="upper right")
    axs[0].set_title("Transmissions per Period")
    
    # HARQ Failures
    axs[1].bar(t, [d["harqFailure"] for d in data_points], width=max(0.5, t_max/len(t)*0.8) if t else 1,
               color=COLORS["red"], alpha=0.8, label="HARQ Failures")
    axs[1].set_ylabel("Count")
    axs[1].legend(loc="upper right")
    axs[1].set_title("HARQ Failures")
    
    # SINR
    axs[2].plot(t, [d["avgSinr"] for d in data_points], color=COLORS["orange"], lw=2, label="Avg SINR")
    axs[2].fill_between(t, [d["minSinr"] for d in data_points], [d["maxSinr"] for d in data_points],
                        alpha=0.15, color=COLORS["orange"], label="Min–Max Range")
    axs[2].set_ylabel("SINR (dB)")
    axs[2].legend(loc="upper right")
    axs[2].set_title("SINR over Time")
    
    # RSRP
    axs[3].plot(t, [d["avgRsrp"] for d in data_points], color=COLORS["purple"], lw=2, label="Avg RSRP")
    axs[3].set_ylabel("RSRP (dBm)")
    axs[3].set_xlabel("Time (seconds)")
    axs[3].legend(loc="upper right")
    axs[3].set_title("Reference Signal Received Power")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/01_mac_crc_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 01_mac_crc_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. MAC BSR Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("bsr_stats", [])
if recs:
    print("Plotting 2. MAC BSR Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("BSR Stats — Buffer Status Reports", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]
        if s.get("duUeIndex", 0) == 513 and len(stats) > 1:
            s = stats[1]
        b = int(s.get("bytes", 0))
        c = s.get("cnt", 0)
        data_points.append({"t": rel(r["_ts"]), "totalBytes": b, "cnt": c,
                           "avgBytes": safe_div(b, c)})
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["totalBytes"] for d in data_points], alpha=0.3, color=COLORS["blue"])
    axs[0].plot(t, [d["totalBytes"] for d in data_points], color=COLORS["blue"], lw=2, label="Total Buffer Bytes")
    axs[0].set_ylabel("Bytes")
    axs[0].legend(loc="upper right")
    axs[0].set_title("Total Buffer Bytes Reported")
    
    axs[1].bar(t, [d["cnt"] for d in data_points], width=max(0.5, t_max/len(t)*0.8) if t else 1,
               color=COLORS["green"], alpha=0.8, label="BSR Count")
    axs[1].set_ylabel("Count")
    axs[1].legend(loc="upper right")
    axs[1].set_title("BSR Report Count per Period")
    
    axs[2].plot(t, [d["avgBytes"] for d in data_points], color=COLORS["pink"], lw=2, label="Avg Bytes/Report")
    axs[2].set_ylabel("Bytes / Report")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].legend(loc="upper right")
    axs[2].set_title("Average Buffer Size per Report")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/02_mac_bsr_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 02_mac_bsr_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. MAC UCI Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("uci_stats", [])
if recs:
    print("Plotting 3. MAC UCI Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("UCI Stats — Uplink Control Information", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]
        if s.get("duUeIndex", 0) == 513 and len(stats) > 1:
            s = stats[1]
        csi = s.get("csi", {})
        cqi = csi.get("cqi", {})
        ri = csi.get("ri", {})
        ta = s.get("timeAdvanceOffset", {})
        data_points.append({
            "t": rel(r["_ts"]),
            "avgCqi": safe_div(cqi.get("total", 0), cqi.get("count", 0)),
            "avgRi": safe_div(ri.get("total", 0), ri.get("count", 0)),
            "avgTa": safe_div(int(ta.get("total", 0)), ta.get("count", 0)),
            "srDetected": s.get("srDetected", 0),
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].plot(t, [d["avgCqi"] for d in data_points], color=COLORS["blue"], lw=2, marker=".", ms=4, label="Avg CQI")
    axs[0].set_ylabel("CQI (0-15)")
    axs[0].set_ylim(bottom=0, top=16)
    axs[0].legend(loc="upper right")
    axs[0].set_title("Channel Quality Indicator")
    
    axs[1].bar(t, [d["srDetected"] for d in data_points], width=max(0.5, t_max/len(t)*0.8) if t else 1,
               color=COLORS["orange"], alpha=0.8, label="SR Detected")
    axs[1].set_ylabel("Count")
    axs[1].legend(loc="upper right")
    axs[1].set_title("Scheduling Requests Detected")
    
    axs[2].plot(t, [d["avgTa"] for d in data_points], color=COLORS["purple"], lw=2, label="Avg Timing Advance")
    axs[2].set_ylabel("TA Offset")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].legend(loc="upper right")
    axs[2].set_title("Timing Advance Offset")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/03_mac_uci_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 03_mac_uci_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. MAC HARQ Stats (DL + UL combined)
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("harq_stats", [])
if recs:
    print("Plotting 4. MAC HARQ Stats...")
    
    # Separate DL and UL by stream_id pattern
    harq_dl, harq_ul = [], []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]
        if s.get("duUeIndex", 0) == 513 and len(stats) > 1:
            s = stats[1]
        mcs = s.get("mcs", {})
        cr = s.get("consRetx", {})
        phs = s.get("perHarqTypeStats", [{}])
        tbs_total = int(phs[0].get("tbsBytes", {}).get("total", 0)) if phs else 0
        tbs_count = int(phs[0].get("count", 0)) if phs else 0
        entry = {
            "t": rel(r["_ts"]),
            "avgMcs": safe_div(int(mcs.get("total", 0)), int(mcs.get("count", 0))),
            "maxMcs": int(mcs.get("max", 0)),
            "minMcs": int(mcs.get("min", 0)),
            "retxCount": int(cr.get("count", 0)),
            "maxRetx": int(cr.get("max", 0)),
            "tbsKB": tbs_total / 1024,
            "tbsCount": tbs_count,
        }
        # Heuristic: DL has even index in first half, UL in second half
        sid = r.get("_stream_id", "")
        # Use alternating pattern: first harq_stats per period is DL, second is UL
        if len(harq_dl) <= len(harq_ul):
            harq_dl.append(entry)
        else:
            harq_ul.append(entry)
    
    fig, axs = plt.subplots(3, 2, figsize=(16, 11), sharex=True)
    fig.suptitle("HARQ Stats — DL (left) vs UL (right)", fontsize=16, fontweight="bold", y=0.98)
    
    for col, (data, label, c1, c2) in enumerate([
        (harq_dl, "DL", COLORS["blue"], COLORS["green"]),
        (harq_ul, "UL", COLORS["red"], COLORS["orange"]),
    ]):
        if not data: continue
        t = [d["t"] for d in data]
        
        # MCS
        axs[0][col].plot(t, [d["avgMcs"] for d in data], color=c1, lw=2, label=f"Avg MCS")
        axs[0][col].fill_between(t, [d["minMcs"] for d in data], [d["maxMcs"] for d in data],
                                 alpha=0.15, color=c1, label="Min–Max")
        axs[0][col].set_ylabel("MCS Index")
        axs[0][col].set_ylim(bottom=-1, top=30)
        axs[0][col].legend(loc="upper right")
        axs[0][col].set_title(f"{label} — MCS Adaptation")
        
        # TBS throughput
        axs[1][col].fill_between(t, [d["tbsKB"] for d in data], alpha=0.3, color=c2)
        axs[1][col].plot(t, [d["tbsKB"] for d in data], color=c2, lw=2, label="TBS Total (KB)")
        axs[1][col].set_ylabel("KB")
        axs[1][col].legend(loc="upper right")
        axs[1][col].set_title(f"{label} — Transport Block Size (cumulative)")
        
        # Retransmissions
        axs[2][col].bar(t, [d["retxCount"] for d in data], 
                        width=max(0.5, t_max/len(t)*0.8) if t else 1,
                        color=c1, alpha=0.7, label="Retx Count")
        axs[2][col].set_ylabel("Count")
        axs[2][col].set_xlabel("Time (seconds)")
        axs[2][col].legend(loc="upper right")
        axs[2][col].set_title(f"{label} — HARQ Retransmissions")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/04_mac_harq_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 04_mac_harq_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. RLC DL Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("rlc_dl_stats", [])
if recs:
    print("Plotting 5. RLC DL Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("RLC DL Stats — Downlink Radio Link Control", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        # Aggregate across all bearers
        total_pdu_tx = 0
        total_sdu_new = 0
        total_am_retx = 0
        total_sdu_queue = 0
        for s in stats:
            total_pdu_tx += int(s.get("pduTxBytes", {}).get("total", 0))
            total_sdu_new += int(s.get("sduNewBytes", {}).get("total", 0))
            am = s.get("am", {})
            if am:
                total_am_retx += int(am.get("pduRetxCount", {}).get("total", 0))
            total_sdu_queue += int(s.get("sduQueueBytes", {}).get("total", 0))
        data_points.append({
            "t": rel(r["_ts"]),
            "pduTxBytes": total_pdu_tx,
            "sduNewBytes": total_sdu_new,
            "amRetx": total_am_retx,
            "sduQueueBytes": total_sdu_queue,
            "numBearers": len(stats),
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["pduTxBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["blue"])
    axs[0].plot(t, [d["pduTxBytes"]/1024 for d in data_points], color=COLORS["blue"], lw=2, label="PDU TX (KB)")
    axs[0].plot(t, [d["sduNewBytes"]/1024 for d in data_points], color=COLORS["green"], lw=2, ls="--", label="SDU New (KB)")
    axs[0].set_ylabel("KB (cumulative)")
    axs[0].legend(loc="upper left")
    axs[0].set_title("DL Data Volume (cumulative)")
    
    axs[1].bar(t, [d["amRetx"] for d in data_points], width=max(0.5, t_max/len(t)*0.8) if t else 1,
               color=COLORS["red"], alpha=0.8, label="AM Retransmissions")
    axs[1].set_ylabel("Count (cumulative)")
    axs[1].legend(loc="upper left")
    axs[1].set_title("RLC AM Retransmissions (cumulative)")
    
    axs[2].fill_between(t, [d["sduQueueBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["teal"])
    axs[2].plot(t, [d["sduQueueBytes"]/1024 for d in data_points], color=COLORS["teal"], lw=2, label="SDU Queue (KB)")
    axs[2].set_ylabel("KB (cumulative)")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].legend(loc="upper left")
    axs[2].set_title("SDU Queue Bytes (cumulative)")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/05_rlc_dl_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 05_rlc_dl_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 6. RLC UL Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("rlc_ul_stats", [])
if recs:
    print("Plotting 6. RLC UL Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("RLC UL Stats — Uplink Radio Link Control", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        total_pdu_rx = 0
        total_sdu_deliv = 0
        total_sdu_latency_sum = 0
        total_sdu_latency_cnt = 0
        for s in stats:
            total_pdu_rx += int(s.get("pduBytes", {}).get("total", 0))
            total_sdu_deliv += int(s.get("sduDeliveredBytes", {}).get("total", 0))
            lat = s.get("sduDeliveredLatency", {})
            total_sdu_latency_sum += int(lat.get("total", 0))
            total_sdu_latency_cnt += int(lat.get("count", 0))
        data_points.append({
            "t": rel(r["_ts"]),
            "pduRxBytes": total_pdu_rx,
            "sduDeliveredBytes": total_sdu_deliv,
            "avgLatency": safe_div(total_sdu_latency_sum, total_sdu_latency_cnt),
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["pduRxBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["red"])
    axs[0].plot(t, [d["pduRxBytes"]/1024 for d in data_points], color=COLORS["red"], lw=2, label="PDU RX (KB)")
    axs[0].set_ylabel("KB (cumulative)")
    axs[0].legend(loc="upper left")
    axs[0].set_title("UL PDU Received Bytes (cumulative)")
    
    axs[1].fill_between(t, [d["sduDeliveredBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["green"])
    axs[1].plot(t, [d["sduDeliveredBytes"]/1024 for d in data_points], color=COLORS["green"], lw=2, label="SDU Delivered (KB)")
    axs[1].set_ylabel("KB (cumulative)")
    axs[1].legend(loc="upper left")
    axs[1].set_title("UL SDU Delivered Bytes (cumulative)")
    
    axs[2].plot(t, [d["avgLatency"]/1000 for d in data_points], color=COLORS["orange"], lw=2, label="Avg SDU Delivery Latency")
    axs[2].set_ylabel("Latency (µs / 1000)")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].legend(loc="upper left")
    axs[2].set_title("SDU Delivery Latency (cumulative avg)")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/06_rlc_ul_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 06_rlc_ul_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 7. PDCP DL Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("dl_stats", [])
if recs:
    print("Plotting 7. PDCP DL Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("PDCP DL Stats — Downlink Packet Data Convergence", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        total_data_tx = 0
        total_data_retx = 0
        total_ctrl_tx = 0
        total_sdu_latency_sum = 0
        total_sdu_latency_cnt = 0
        total_discarded = 0
        for s in stats:
            total_data_tx += int(s.get("dataPduTxBytes", {}).get("total", 0))
            total_data_retx += int(s.get("dataPduRetxBytes", {}).get("total", 0))
            total_ctrl_tx += int(s.get("controlPduTxBytes", {}).get("total", 0))
            lat = s.get("sduTxLatency", {})
            total_sdu_latency_sum += int(lat.get("total", 0))
            total_sdu_latency_cnt += int(lat.get("count", 0))
            total_discarded += s.get("sduDiscarded", 0)
        data_points.append({
            "t": rel(r["_ts"]),
            "dataTxBytes": total_data_tx,
            "dataRetxBytes": total_data_retx,
            "ctrlTxBytes": total_ctrl_tx,
            "avgLatency": safe_div(total_sdu_latency_sum, total_sdu_latency_cnt),
            "discarded": total_discarded,
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["dataTxBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["blue"])
    axs[0].plot(t, [d["dataTxBytes"]/1024 for d in data_points], color=COLORS["blue"], lw=2, label="Data PDU TX (KB)")
    axs[0].plot(t, [d["dataRetxBytes"]/1024 for d in data_points], color=COLORS["red"], lw=2, ls="--", label="Data Retx (KB)")
    axs[0].set_ylabel("KB (cumulative)")
    axs[0].legend(loc="upper left")
    axs[0].set_title("PDCP DL Data Volume")
    
    axs[1].plot(t, [d["avgLatency"] for d in data_points], color=COLORS["orange"], lw=2, marker="o", ms=5, label="Avg SDU TX Latency")
    axs[1].set_ylabel("Latency (ns)")
    axs[1].legend(loc="upper left")
    axs[1].set_title("PDCP DL SDU TX Latency")
    
    axs[2].bar(t, [d["discarded"] for d in data_points], width=max(0.5, t_max/max(len(t),1)*0.8),
               color=COLORS["red"], alpha=0.8, label="SDUs Discarded")
    axs[2].set_ylabel("Count")
    axs[2].set_xlabel("Time (seconds)")
    axs[2].legend(loc="upper left")
    axs[2].set_title("PDCP DL SDUs Discarded")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/07_pdcp_dl_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 07_pdcp_dl_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 8. PDCP UL Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("ul_stats", [])
if recs:
    print("Plotting 8. PDCP UL Stats...")
    fig, axs = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("PDCP UL Stats — Uplink Packet Data Convergence", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        total_data_rx = 0
        total_sdu_deliv = 0
        total_ctrl_rx = 0
        for s in stats:
            total_data_rx += int(s.get("rxDataPduBytes", {}).get("total", 0))
            total_sdu_deliv += int(s.get("sduDeliveredBytes", {}).get("total", 0))
            total_ctrl_rx += int(s.get("rxControlPduBytes", {}).get("total", 0))
        data_points.append({
            "t": rel(r["_ts"]),
            "dataRxBytes": total_data_rx,
            "sduDeliveredBytes": total_sdu_deliv,
            "ctrlRxBytes": total_ctrl_rx,
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["dataRxBytes"]/1024 for d in data_points], alpha=0.3, color=COLORS["red"])
    axs[0].plot(t, [d["dataRxBytes"]/1024 for d in data_points], color=COLORS["red"], lw=2, label="Data PDU RX (KB)")
    axs[0].plot(t, [d["sduDeliveredBytes"]/1024 for d in data_points], color=COLORS["green"], lw=2, ls="--", label="SDU Delivered (KB)")
    axs[0].set_ylabel("KB (cumulative)")
    axs[0].legend(loc="upper left")
    axs[0].set_title("PDCP UL Data Volume")
    
    axs[1].plot(t, [d["ctrlRxBytes"] for d in data_points], color=COLORS["purple"], lw=2, label="Control PDU RX (bytes)")
    axs[1].set_ylabel("Bytes (cumulative)")
    axs[1].set_xlabel("Time (seconds)")
    axs[1].legend(loc="upper left")
    axs[1].set_title("PDCP UL Control PDU Volume")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/08_pdcp_ul_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 08_pdcp_ul_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 9. FAPI DL Config Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("dl_config_stats", [])
if recs:
    print("Plotting 9. FAPI DL Config Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("FAPI DL Config Stats — PHY-MAC DL Scheduling", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        # Pick UE (rnti > 1000) or first stats entry
        ue_stats = [s for s in stats if s.get("rnti", 0) > 1000]
        if not ue_stats:
            continue
        s = ue_stats[0]
        cnt = max(s.get("l1Cnt", 1), 1)
        data_points.append({
            "t": rel(r["_ts"]),
            "avgMcs": s.get("l1McsAvg", 0) / cnt,
            "minMcs": s.get("l1McsMin", 0),
            "maxMcs": s.get("l1McsMax", 0),
            "avgPrb": s.get("l1PrbAvg", 0) / cnt,
            "minPrb": s.get("l1PrbMin", 0),
            "maxPrb": s.get("l1PrbMax", 0),
            "avgTbs": s.get("l1TbsAvg", 0) / cnt / 1024,  # KB
            "totalTx": s.get("l1DlcTx", 0),
            "cnt": cnt,
        })
    
    if data_points:
        t = [d["t"] for d in data_points]
        
        axs[0].plot(t, [d["avgMcs"] for d in data_points], color=COLORS["blue"], lw=2, label="Avg MCS")
        axs[0].fill_between(t, [d["minMcs"] for d in data_points], [d["maxMcs"] for d in data_points],
                            alpha=0.15, color=COLORS["blue"], label="Min–Max")
        axs[0].set_ylabel("MCS Index")
        axs[0].set_ylim(bottom=-1, top=30)
        axs[0].legend(loc="upper right")
        axs[0].set_title("DL Scheduling MCS (FAPI Layer)")
        
        axs[1].plot(t, [d["avgPrb"] for d in data_points], color=COLORS["green"], lw=2, label="Avg PRBs")
        axs[1].fill_between(t, [d["minPrb"] for d in data_points], [d["maxPrb"] for d in data_points],
                            alpha=0.15, color=COLORS["green"], label="Min–Max")
        axs[1].set_ylabel("PRBs")
        axs[1].legend(loc="upper right")
        axs[1].set_title("DL Physical Resource Blocks Allocated")
        
        axs[2].fill_between(t, [d["avgTbs"] for d in data_points], alpha=0.3, color=COLORS["orange"])
        axs[2].plot(t, [d["avgTbs"] for d in data_points], color=COLORS["orange"], lw=2, label="Avg TBS (KB)")
        axs[2].set_ylabel("KB")
        axs[2].set_xlabel("Time (seconds)")
        axs[2].legend(loc="upper right")
        axs[2].set_title("DL Transport Block Size (avg per TTI)")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/09_fapi_dl_config.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 09_fapi_dl_config.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 10. FAPI UL Config Stats
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("ul_config_stats", [])
if recs:
    print("Plotting 10. FAPI UL Config Stats...")
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle("FAPI UL Config Stats — PHY-MAC UL Scheduling", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]  # UL config typically has one entry
        cnt = max(s.get("l1Cnt", 1), 1)
        data_points.append({
            "t": rel(r["_ts"]),
            "avgMcs": s.get("l1McsAvg", 0) / cnt,
            "minMcs": s.get("l1McsMin", 0),
            "maxMcs": s.get("l1McsMax", 0),
            "avgPrb": s.get("l1PrbAvg", 0) / cnt,
            "minPrb": s.get("l1PrbMin", 0),
            "maxPrb": s.get("l1PrbMax", 0),
            "avgTbs": s.get("l1TbsAvg", 0) / cnt / 1024,
            "cnt": cnt,
        })
    
    if data_points:
        t = [d["t"] for d in data_points]
        
        axs[0].plot(t, [d["avgMcs"] for d in data_points], color=COLORS["red"], lw=2, label="Avg MCS")
        axs[0].fill_between(t, [d["minMcs"] for d in data_points], [d["maxMcs"] for d in data_points],
                            alpha=0.15, color=COLORS["red"], label="Min–Max")
        axs[0].set_ylabel("MCS Index")
        axs[0].set_ylim(bottom=-1, top=30)
        axs[0].legend(loc="upper right")
        axs[0].set_title("UL Scheduling MCS (FAPI Layer)")
        
        axs[1].plot(t, [d["avgPrb"] for d in data_points], color=COLORS["teal"], lw=2, label="Avg PRBs")
        axs[1].fill_between(t, [d["minPrb"] for d in data_points], [d["maxPrb"] for d in data_points],
                            alpha=0.15, color=COLORS["teal"], label="Min–Max")
        axs[1].set_ylabel("PRBs")
        axs[1].legend(loc="upper right")
        axs[1].set_title("UL Physical Resource Blocks Allocated")
        
        axs[2].fill_between(t, [d["avgTbs"] for d in data_points], alpha=0.3, color=COLORS["amber"])
        axs[2].plot(t, [d["avgTbs"] for d in data_points], color=COLORS["amber"], lw=2, label="Avg TBS (KB)")
        axs[2].set_ylabel("KB")
        axs[2].set_xlabel("Time (seconds)")
        axs[2].legend(loc="upper right")
        axs[2].set_title("UL Transport Block Size (avg per TTI)")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/10_fapi_ul_config.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 10_fapi_ul_config.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 11. FAPI CRC Stats (PHY layer SNR & TA)
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("fapi_crc_stats", [])
if recs:
    print("Plotting 11. FAPI CRC Stats...")
    fig, axs = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("FAPI CRC Stats — PHY Layer SNR & Timing Advance", fontsize=16, fontweight="bold", y=0.98)
    
    data_points = []
    for r in recs:
        stats = r.get("stats", [])
        if not stats: continue
        s = stats[0]
        data_points.append({
            "t": rel(r["_ts"]),
            "snrMin": s.get("l1SnrMin", 0),
            "snrMax": s.get("l1SnrMax", 0),
            "taMin": s.get("l1TaMin", 0),
            "taMax": s.get("l1TaMax", 0),
        })
    
    t = [d["t"] for d in data_points]
    
    axs[0].fill_between(t, [d["snrMin"] for d in data_points], [d["snrMax"] for d in data_points],
                        alpha=0.3, color=COLORS["blue"], label="SNR Range")
    axs[0].plot(t, [d["snrMax"] for d in data_points], color=COLORS["blue"], lw=1.5, label="SNR Max", alpha=0.8)
    axs[0].plot(t, [d["snrMin"] for d in data_points], color=COLORS["red"], lw=1.5, label="SNR Min", alpha=0.8)
    axs[0].set_ylabel("SNR (dB × 10)")
    axs[0].legend(loc="upper right")
    axs[0].set_title("FAPI UL CRC SNR Range")
    
    axs[1].fill_between(t, [d["taMin"] for d in data_points], [d["taMax"] for d in data_points],
                        alpha=0.3, color=COLORS["green"], label="TA Range")
    axs[1].plot(t, [d["taMax"] for d in data_points], color=COLORS["green"], lw=1.5, label="TA Max")
    axs[1].plot(t, [d["taMin"] for d in data_points], color=COLORS["teal"], lw=1.5, label="TA Min")
    axs[1].set_ylabel("Timing Advance")
    axs[1].set_xlabel("Time (seconds)")
    axs[1].legend(loc="upper right")
    axs[1].set_title("FAPI UL CRC Timing Advance Range")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{OUT_DIR}/11_fapi_crc_stats.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 11_fapi_crc_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 12. RRC Events Timeline
# ═══════════════════════════════════════════════════════════════════════════════
rrc_add = records_by_schema.get("rrc_ue_add", [])
rrc_proc = records_by_schema.get("rrc_ue_procedure", [])
rrc_rem = records_by_schema.get("rrc_ue_remove", [])
rrc_total = len(rrc_add) + len(rrc_proc) + len(rrc_rem)
if rrc_total > 0:
    print("Plotting 12. RRC Events...")
    fig, ax = plt.subplots(1, 1, figsize=(14, 5))
    fig.suptitle("RRC Events Timeline — UE Lifecycle", fontsize=16, fontweight="bold", y=0.98)
    
    events = []
    for r in rrc_add:
        events.append({"t": rel(r["_ts"]), "label": f"UE Add\ncRnti={r.get('cRnti')}\npci={r.get('pci')}", 
                       "color": COLORS["green"], "type": "UE Add"})
    proc_names = {1: "RRCSetup", 2: "RRCReconfig", 3: "RRCReestab", 4: "SecurityMode"}
    for r in rrc_proc:
        pname = proc_names.get(r.get("procedure"), f"proc_{r.get('procedure')}")
        success = "OK" if r.get("success", 0) else "FAIL"
        events.append({"t": rel(r["_ts"]), "label": f"{pname}\n{success}",
                       "color": COLORS["blue"], "type": "Procedure"})
    for r in rrc_rem:
        events.append({"t": rel(r["_ts"]), "label": "UE Remove",
                       "color": COLORS["red"], "type": "UE Remove"})
    
    events.sort(key=lambda e: e["t"])
    
    for i, e in enumerate(events):
        ax.axvline(e["t"], color=e["color"], lw=2, alpha=0.7)
        y_offset = 0.3 + (i % 3) * 0.2
        ax.annotate(e["label"], (e["t"], y_offset), fontsize=9, fontweight="bold",
                   ha="center", va="bottom", color=e["color"],
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=e["color"], alpha=0.9))
    
    ax.set_xlim(-2, t_max + 2)
    ax.set_ylim(0, 1.2)
    ax.set_xlabel("Time (seconds)")
    ax.set_yticks([])
    ax.set_title(f"RRC Events ({len(events)} total)")
    
    # Legend
    patches = [mpatches.Patch(color=COLORS["green"], label="UE Add"),
               mpatches.Patch(color=COLORS["blue"], label="Procedure"),
               mpatches.Patch(color=COLORS["red"], label="UE Remove")]
    ax.legend(handles=patches, loc="upper right")
    
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(f"{OUT_DIR}/12_rrc_events.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 12_rrc_events.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 13. NGAP Events Timeline
# ═══════════════════════════════════════════════════════════════════════════════
ngap_start = records_by_schema.get("ngap_procedure_started", [])
ngap_comp = records_by_schema.get("ngap_procedure_completed", [])
ngap_total = len(ngap_start) + len(ngap_comp)
if ngap_total > 0:
    print("Plotting 13. NGAP Events...")
    fig, ax = plt.subplots(1, 1, figsize=(14, 5))
    fig.suptitle("NGAP Events Timeline — Core Network Procedures", fontsize=16, fontweight="bold", y=0.98)
    
    ngap_names = {1: "InitialUEMessage", 2: "UEContextRelease", 3: "InitialContextSetup",
                  4: "PDUSessionSetup", 5: "HandoverPrep"}
    
    events = []
    for r in ngap_start:
        pname = ngap_names.get(r.get("procedure"), f"proc_{r.get('procedure')}")
        events.append({"t": rel(r["_ts"]), "label": f"{pname}\nSTARTED",
                       "color": COLORS["indigo"], "type": "Started"})
    for r in ngap_comp:
        pname = ngap_names.get(r.get("procedure"), f"proc_{r.get('procedure')}")
        success = "SUCCESS" if r.get("success") else "FAILED"
        events.append({"t": rel(r["_ts"]), "label": f"{pname}\n{success}",
                       "color": COLORS["green"] if r.get("success") else COLORS["red"], "type": "Completed"})
    
    events.sort(key=lambda e: e["t"])
    
    for i, e in enumerate(events):
        ax.axvline(e["t"], color=e["color"], lw=2, alpha=0.7)
        y_offset = 0.2 + (i % 4) * 0.2
        ax.annotate(e["label"], (e["t"], y_offset), fontsize=9, fontweight="bold",
                   ha="center", va="bottom", color=e["color"],
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=e["color"], alpha=0.9))
    
    ax.set_xlim(-2, t_max + 2)
    ax.set_ylim(0, 1.2)
    ax.set_xlabel("Time (seconds)")
    ax.set_yticks([])
    ax.set_title(f"NGAP Events ({len(events)} total)")
    
    patches = [mpatches.Patch(color=COLORS["indigo"], label="Started"),
               mpatches.Patch(color=COLORS["green"], label="Completed (Success)"),
               mpatches.Patch(color=COLORS["red"], label="Completed (Failed)")]
    ax.legend(handles=patches, loc="upper right")
    
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(f"{OUT_DIR}/13_ngap_events.png", dpi=150)
    plt.close()
    plot_count += 1
    print("  -> 13_ngap_events.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 14. jBPF Perf Stats — Hook Latency
# ═══════════════════════════════════════════════════════════════════════════════
recs = records_by_schema.get("jbpf_out_perf_list", [])
if recs:
    print("Plotting 14. jBPF Perf Stats...")
    
    # Collect per-hook stats over time
    hook_data = defaultdict(list)
    for r in recs:
        t_val = rel(r["_ts"])
        for hp in r.get("hookPerf", []):
            name = hp.get("hookName", "unknown")
            hook_data[name].append({
                "t": t_val,
                "p50": hp.get("p50", 0),
                "p90": hp.get("p90", 0),
                "p99": hp.get("p99", 0),
                "max": hp.get("max", 0),
                "min": hp.get("min", 0),
                "num": hp.get("num", 0),
            })
    
    # Plot: bar chart of latest p50/p90/p99 per hook + time series for top hooks
    if hook_data:
        # Get latest snapshot for each hook
        latest = {}
        for name, points in hook_data.items():
            latest[name] = points[-1]
        
        # Sort by p50 descending
        sorted_hooks = sorted(latest.items(), key=lambda x: x[1].get("p50", 0), reverse=True)
        
        # Fig 1: Bar chart of all hooks (latest snapshot)
        fig, axs = plt.subplots(2, 1, figsize=(16, 12))
        fig.suptitle("jBPF Hook Performance — Execution Latency (ns)", fontsize=16, fontweight="bold", y=0.98)
        
        names = [h[0] for h in sorted_hooks]
        p50s = [h[1]["p50"] for h in sorted_hooks]
        p90s = [h[1]["p90"] for h in sorted_hooks]
        p99s = [h[1]["p99"] for h in sorted_hooks]
        maxs = [h[1]["max"] for h in sorted_hooks]
        nums = [h[1]["num"] for h in sorted_hooks]
        
        x = np.arange(len(names))
        w = 0.22
        
        axs[0].barh(x - w, p50s, w, color=COLORS["blue"], alpha=0.9, label="p50")
        axs[0].barh(x, p90s, w, color=COLORS["orange"], alpha=0.9, label="p90")
        axs[0].barh(x + w, p99s, w, color=COLORS["red"], alpha=0.9, label="p99")
        axs[0].set_yticks(x)
        axs[0].set_yticklabels(names, fontsize=8)
        axs[0].set_xlabel("Latency (ns)")
        axs[0].legend(loc="lower right")
        axs[0].set_title("Hook Execution Latency Percentiles (latest snapshot)")
        axs[0].invert_yaxis()
        
        # Invocation counts
        axs[1].barh(x, nums, color=COLORS["teal"], alpha=0.8)
        axs[1].set_yticks(x)
        axs[1].set_yticklabels(names, fontsize=8)
        axs[1].set_xlabel("Total Invocations")
        axs[1].set_title("Hook Invocation Count (cumulative)")
        axs[1].invert_yaxis()
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.savefig(f"{OUT_DIR}/14_jbpf_perf_stats.png", dpi=150)
        plt.close()
        plot_count += 1
        print("  -> 14_jbpf_perf_stats.png")
        
        # Fig 2: Time series for top 6 hooks by invocation count
        top_hooks = sorted(hook_data.items(), key=lambda x: x[1][-1].get("num", 0), reverse=True)[:6]
        if top_hooks:
            fig, axs = plt.subplots(3, 2, figsize=(16, 12), sharex=True)
            fig.suptitle("jBPF Hook Latency Over Time (Top 6 Hooks)", fontsize=16, fontweight="bold", y=0.98)
            
            colors_list = list(COLORS.values())
            for idx, (name, points) in enumerate(top_hooks):
                row, col = idx // 2, idx % 2
                t_vals = [p["t"] for p in points]
                axs[row][col].fill_between(t_vals, [p["min"] for p in points], [p["max"] for p in points],
                                           alpha=0.1, color=colors_list[idx])
                axs[row][col].plot(t_vals, [p["p50"] for p in points], color=colors_list[idx], lw=2, label="p50")
                axs[row][col].plot(t_vals, [p["p90"] for p in points], color=colors_list[idx], lw=1, ls="--", label="p90", alpha=0.7)
                axs[row][col].set_ylabel("ns")
                axs[row][col].legend(loc="upper right", fontsize=8)
                axs[row][col].set_title(name, fontsize=10)
                if row == 2:
                    axs[row][col].set_xlabel("Time (seconds)")
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            plt.savefig(f"{OUT_DIR}/15_jbpf_perf_timeseries.png", dpi=150)
            plt.close()
            plot_count += 1
            print("  -> 15_jbpf_perf_timeseries.png")



# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  All {plot_count} plots saved to {OUT_DIR}/")
print(f"  Data: {total} records, {len(records_by_schema)} schemas, {t_max:.0f}s")
print(f"{'='*60}")
