#!/usr/bin/env python3
"""
Plot MAC Telemetry — one clean, readable PNG per codelet.
Each plot has its own subplots so nothing overlaps.
"""
import json, re, os
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LOG = "/tmp/decoder.log"
OUT_DIR = "/home/maxim/Desktop/plots"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Parse ────────────────────────────────────────────────────────────────────
crc, bsr, uci, harq_dl, harq_ul = [], [], [], [], []
DL_STREAM = "4e1ae9d5f08e"
UL_STREAM = "2a440fdb"

with open(LOG) as f:
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

        msg = data.get("_schema_proto_msg", "")
        sid = data.get("_stream_id", "")
        stats = data.get("stats", [])
        if not stats:
            continue
        s = stats[0]
        if s.get("duUeIndex", 0) == 513 and len(stats) > 1:
            s = stats[1]

        if msg == "crc_stats":
            crc.append({
                "ts": ts,
                "succTx": s.get("succTx", 0),
                "cntTx": s.get("cntTx", 0),
                "harqFailure": s.get("harqFailure", 0),
                "avgSinr": s.get("sumSinr", 0) / max(s.get("cntSinr", 1), 1),
                "avgRsrp": s.get("sumRsrp", 0) / max(s.get("cntRsrp", 1), 1),
                "retxHist": s.get("retxHist", []),
            })
        elif msg == "bsr_stats":
            b = int(s.get("bytes", 0))
            c = s.get("cnt", 0)
            bsr.append({
                "ts": ts,
                "totalBytes": b,
                "cnt": c,
                "avgBytes": b / max(c, 1),
            })
        elif msg == "uci_stats":
            csi = s.get("csi", {})
            cqi = csi.get("cqi", {})
            ri = csi.get("ri", {})
            ta = s.get("timeAdvanceOffset", {})
            uci.append({
                "ts": ts,
                "srDetected": s.get("srDetected", 0),
                "avgCqi": cqi.get("total", 0) / max(cqi.get("count", 1), 1),
                "avgRi": ri.get("total", 0) / max(ri.get("count", 1), 1),
                "avgTa": int(ta.get("total", 0)) / max(ta.get("count", 1), 1),
                "cqiCount": cqi.get("count", 0),
            })
        elif msg == "harq_stats":
            mcs = s.get("mcs", {})
            cr = s.get("consRetx", {})
            phs = s.get("perHarqTypeStats", [{}])
            tbs_total = int(phs[0].get("tbsBytes", {}).get("total", 0)) if phs else 0
            tbs_count = int(phs[0].get("count", 0)) if phs else 0
            entry = {
                "ts": ts,
                "avgMcs": int(mcs.get("total", 0)) / max(int(mcs.get("count", 1)), 1),
                "maxMcs": int(mcs.get("max", 0)),
                "minMcs": int(mcs.get("min", 0)),
                "retxCount": int(cr.get("count", 0)),
                "maxRetx": int(cr.get("max", 0)),
                "tbsTotal": tbs_total,
                "tbsCount": tbs_count,
            }
            if DL_STREAM in sid:
                harq_dl.append(entry)
            elif UL_STREAM in sid:
                harq_ul.append(entry)

print(f"Parsed: CRC={len(crc)}, BSR={len(bsr)}, UCI={len(uci)}, "
      f"HARQ_DL={len(harq_dl)}, HARQ_UL={len(harq_ul)}")

all_ts = ([e["ts"] for e in crc] + [e["ts"] for e in bsr] +
          [e["ts"] for e in uci] + [e["ts"] for e in harq_dl] +
          [e["ts"] for e in harq_ul])
t0 = min(all_ts)
def rel(ts):
    return (ts - t0).total_seconds()

# ── Style ────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#FAFAFA",
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
})

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CRC Stats
# ═══════════════════════════════════════════════════════════════════════════════
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("CRC Stats", fontsize=18, fontweight="bold", y=0.98)
t = [rel(e["ts"]) for e in crc]

axs[0].plot(t, [e["succTx"] for e in crc], color="#1B5E20", lw=2, label="Successful Tx")
axs[0].plot(t, [e["cntTx"] for e in crc], color="#1565C0", lw=2, ls="--", label="Total Tx")
axs[0].set_ylabel("Transmission Count")
axs[0].legend(fontsize=10, loc="upper right")
axs[0].set_title("Transmissions per Period")

axs[1].plot(t, [e["harqFailure"] for e in crc], color="#C62828", lw=2, marker="o", ms=4, label="HARQ Failures")
axs[1].set_ylabel("Failure Count")
axs[1].legend(fontsize=10, loc="upper right")
axs[1].set_title("HARQ Failures")

axs[2].plot(t, [e["avgSinr"] for e in crc], color="#E65100", lw=2, label="Avg SINR")
axs[2].set_ylabel("SINR (dB)")
axs[2].set_xlabel("Time (seconds)")
axs[2].legend(fontsize=10, loc="upper right")
axs[2].set_title("Average SINR")

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f"{OUT_DIR}/1_crc_stats.png", dpi=150)
plt.close()
print("  -> 1_crc_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. BSR Stats
# ═══════════════════════════════════════════════════════════════════════════════
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("BSR Stats", fontsize=18, fontweight="bold", y=0.98)
t = [rel(e["ts"]) for e in bsr]

axs[0].fill_between(t, [e["totalBytes"] for e in bsr], alpha=0.3, color="#1565C0")
axs[0].plot(t, [e["totalBytes"] for e in bsr], color="#1565C0", lw=2, label="Total Buffer Bytes")
axs[0].set_ylabel("Bytes")
axs[0].legend(fontsize=10, loc="upper right")
axs[0].set_title("Total Buffer Bytes Reported")

axs[1].bar(t, [e["cnt"] for e in bsr], width=0.8, color="#2E7D32", alpha=0.8, label="BSR Report Count")
axs[1].set_ylabel("Count")
axs[1].legend(fontsize=10, loc="upper right")
axs[1].set_title("BSR Report Count per Period")

axs[2].plot(t, [e["avgBytes"] for e in bsr], color="#AD1457", lw=2, label="Avg Bytes per Report")
axs[2].set_ylabel("Bytes / Report")
axs[2].set_xlabel("Time (seconds)")
axs[2].legend(fontsize=10, loc="upper right")
axs[2].set_title("Average Buffer Size per Report")

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f"{OUT_DIR}/2_bsr_stats.png", dpi=150)
plt.close()
print("  -> 2_bsr_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. UCI Stats
# ═══════════════════════════════════════════════════════════════════════════════
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("UCI Stats", fontsize=18, fontweight="bold", y=0.98)
t = [rel(e["ts"]) for e in uci]

axs[0].plot(t, [e["avgCqi"] for e in uci], color="#1565C0", lw=2, marker=".", ms=5, label="Avg CQI")
axs[0].set_ylabel("CQI (0-15)")
axs[0].set_ylim(bottom=0, top=16)
axs[0].legend(fontsize=10, loc="upper right")
axs[0].set_title("Channel Quality Indicator (CQI)")

axs[1].bar(t, [e["srDetected"] for e in uci], width=0.8, color="#E65100", alpha=0.8, label="SR Detected")
axs[1].set_ylabel("Count")
axs[1].legend(fontsize=10, loc="upper right")
axs[1].set_title("Scheduling Requests Detected")

axs[2].plot(t, [e["avgTa"] for e in uci], color="#6A1B9A", lw=2, label="Avg Timing Advance")
axs[2].set_ylabel("TA Offset")
axs[2].set_xlabel("Time (seconds)")
axs[2].legend(fontsize=10, loc="upper right")
axs[2].set_title("Timing Advance Offset")

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f"{OUT_DIR}/3_uci_stats.png", dpi=150)
plt.close()
print("  -> 3_uci_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. DL HARQ Stats
# ═══════════════════════════════════════════════════════════════════════════════
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("DL HARQ Stats (Downlink)", fontsize=18, fontweight="bold", y=0.98)
t = [rel(e["ts"]) for e in harq_dl]

axs[0].plot(t, [e["avgMcs"] for e in harq_dl], color="#1565C0", lw=2, label="Avg MCS")
axs[0].fill_between(t, [e["minMcs"] for e in harq_dl], [e["maxMcs"] for e in harq_dl],
                     alpha=0.2, color="#1565C0", label="MCS Range (min–max)")
axs[0].set_ylabel("MCS Index")
axs[0].legend(fontsize=10, loc="upper right")
axs[0].set_title("Modulation & Coding Scheme (MCS)")

tbs_kb = [e["tbsTotal"] / 1024 for e in harq_dl]
axs[1].fill_between(t, tbs_kb, alpha=0.3, color="#2E7D32")
axs[1].plot(t, tbs_kb, color="#2E7D32", lw=2, label="TBS Total (KB)")
axs[1].set_ylabel("KB")
axs[1].legend(fontsize=10, loc="upper right")
axs[1].set_title("Transport Block Size — Total Throughput")

axs[2].bar(t, [e["tbsCount"] for e in harq_dl], width=0.8, color="#E65100", alpha=0.8, label="HARQ Tx Count")
axs[2].set_ylabel("Count")
axs[2].set_xlabel("Time (seconds)")
axs[2].legend(fontsize=10, loc="upper right")
axs[2].set_title("Number of HARQ Transmissions")

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f"{OUT_DIR}/4_dl_harq_stats.png", dpi=150)
plt.close()
print("  -> 4_dl_harq_stats.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. UL HARQ Stats
# ═══════════════════════════════════════════════════════════════════════════════
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("UL HARQ Stats (Uplink)", fontsize=18, fontweight="bold", y=0.98)
t = [rel(e["ts"]) for e in harq_ul]

axs[0].plot(t, [e["avgMcs"] for e in harq_ul], color="#1565C0", lw=2, label="Avg MCS")
axs[0].fill_between(t, [e["minMcs"] for e in harq_ul], [e["maxMcs"] for e in harq_ul],
                     alpha=0.2, color="#1565C0", label="MCS Range (min–max)")
axs[0].set_ylabel("MCS Index")
axs[0].legend(fontsize=10, loc="upper right")
axs[0].set_title("Modulation & Coding Scheme (MCS)")

tbs_kb = [e["tbsTotal"] / 1024 for e in harq_ul]
axs[1].fill_between(t, tbs_kb, alpha=0.3, color="#C62828")
axs[1].plot(t, tbs_kb, color="#C62828", lw=2, label="TBS Total (KB)")
axs[1].set_ylabel("KB")
axs[1].legend(fontsize=10, loc="upper right")
axs[1].set_title("Transport Block Size — Total Throughput")

axs[2].bar(t, [e["tbsCount"] for e in harq_ul], width=0.8, color="#6A1B9A", alpha=0.8, label="HARQ Tx Count")
axs[2].set_ylabel("Count")
axs[2].set_xlabel("Time (seconds)")
axs[2].legend(fontsize=10, loc="upper right")
axs[2].set_title("Number of HARQ Transmissions")

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f"{OUT_DIR}/5_ul_harq_stats.png", dpi=150)
plt.close()
print("  -> 5_ul_harq_stats.png")

print(f"\nAll 5 plots saved to {OUT_DIR}/")
print(f"Time range: {rel(max(all_ts)):.0f}s")
