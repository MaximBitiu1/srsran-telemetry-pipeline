#!/usr/bin/env python3
"""Export stress-anomaly and channel datasets from log files to CSV.

Handles both ASCII and binary log files (null bytes, mixed binary content).
Outputs one CSV per schema per dataset.
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRESS_DIR = Path.home() / "Desktop" / "dataset" / "stress_20260325_204950"
CHANNEL_DIR = Path.home() / "Desktop" / "channel_dataset" / "20260401_180521"

GHOST_UE = 513  # duUeIndex to filter out

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_log_lines(filepath: Path):
    """Yield (timestamp_str, json_obj) for every REC line in a log file."""
    with open(filepath, "rb") as fh:
        for raw_line in fh:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if 'msg="REC: ' not in line:
                continue
            # Extract timestamp
            ts_match = re.match(r'time="([^"]+)"', line)
            if not ts_match:
                continue
            ts_str = ts_match.group(1)

            # Extract JSON payload
            idx = line.index('msg="REC: ') + len('msg="REC: ')
            payload = line[idx:]
            if payload.endswith('"'):
                payload = payload[:-1]
            payload = payload.replace('\\"', '"')

            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            yield ts_str, obj


def ts_to_unix(ts_str: str) -> float:
    """Parse logrus timestamp to unix seconds."""
    # Format: 2026-03-25T20:50:03+01:00
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.timestamp()
    except Exception:
        return 0.0


def ts_to_utc(ts_str: str) -> str:
    """Parse logrus timestamp to UTC ISO string."""
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except Exception:
        return ts_str


# ---------------------------------------------------------------------------
# Schema-specific row extractors
# Each returns a list of dicts (one per UE/hook/bearer in the message).
# ---------------------------------------------------------------------------

def extract_crc_stats(obj):
    """Extract crc_stats rows. Skip FAPI package and ghost UE."""
    pkg = obj.get("_schema_proto_package", "")
    if "fapi" in pkg.lower():
        return []
    rows = []
    for st in obj.get("stats", []):
        ue = st.get("duUeIndex", 0)
        if ue == GHOST_UE:
            continue
        cnt_sinr = st.get("cntSinr", 0)
        sum_sinr = st.get("sumSinr", 0)
        avg_sinr = sum_sinr / cnt_sinr if cnt_sinr else 0.0
        rows.append({
            "duUeIndex": ue,
            "avg_sinr": round(avg_sinr, 2),
            "min_sinr": st.get("minSinr", 0),
            "max_sinr": st.get("maxSinr", 0),
            "cnt_sinr": cnt_sinr,
            "harq_failure": st.get("harqFailure", 0),
            "succ_tx": st.get("succTx", 0),
            "cnt_tx": st.get("cntTx", 0),
            "cons_max": st.get("consMax", 0),
        })
    return rows


def extract_bsr_stats(obj):
    rows = []
    for st in obj.get("stats", []):
        ue = st.get("duUeIndex", 0)
        if ue == GHOST_UE:
            continue
        rows.append({
            "duUeIndex": ue,
            "bytes": int(st.get("bytes", 0)),
            "cnt": st.get("cnt", 0),
        })
    return rows


def extract_harq_stats(obj):
    """Extract harq_stats, determine direction from stream_id heuristic."""
    sid = obj.get("_stream_id", "")
    rows = []
    for st in obj.get("stats", []):
        ue = st.get("duUeIndex", 0)
        if ue == GHOST_UE:
            continue
        mcs = st.get("mcs", {})
        mcs_count = mcs.get("count", 0)
        mcs_total = int(mcs.get("total", 0))
        avg_mcs = mcs_total / mcs_count if mcs_count else 0.0
        consRetx = st.get("consRetx", {})
        rows.append({
            "duUeIndex": ue,
            "stream_id": sid,
            "avg_mcs": round(avg_mcs, 2),
            "mcs_min": mcs.get("min", 0),
            "mcs_max": mcs.get("max", 0),
            "mcs_count": mcs_count,
            "max_nof_harq_retxs": st.get("maxNofHarqRetxs", 0),
            "cons_retx_max": consRetx.get("max", 0),
            "cell_id": st.get("cellId", 0),
        })
    return rows


def extract_jbpf_out_perf_list(obj):
    """One row per hook."""
    rows = []
    for hp in obj.get("hookPerf", []):
        name = hp.get("hookName", "unknown")
        rows.append({
            "hook_name": name,
            "p50_us": round(int(hp.get("p50", 0)) / 1000, 3),
            "p90_us": round(int(hp.get("p90", 0)) / 1000, 3),
            "p99_us": round(int(hp.get("p99", 0)) / 1000, 3),
            "max_us": round(int(hp.get("max", 0)) / 1000, 3),
            "num": int(hp.get("num", 0)),
        })
    return rows


def extract_rlc_ul_stats(obj):
    rows = []
    for st in obj.get("stats", []):
        ue = st.get("duUeIndex", 0)
        if ue == GHOST_UE:
            continue
        lat = st.get("sduDeliveredLatency", {})
        lat_count = lat.get("count", 0)
        lat_total = int(lat.get("total", 0))
        lat_max = int(lat.get("max", 0))
        avg_lat_us = (lat_total / lat_count / 1000) if lat_count else 0.0
        rows.append({
            "duUeIndex": ue,
            "rb_id": st.get("rbId", 0),
            "is_srb": st.get("isSrb", 0),
            "sdu_delivered_lat_avg_us": round(avg_lat_us, 3),
            "sdu_delivered_lat_max_us": round(lat_max / 1000, 3),
            "sdu_delivered_lat_count": lat_count,
            "pdu_bytes_total": int(st.get("pduBytes", {}).get("total", 0)),
            "sdu_delivered_bytes_total": int(st.get("sduDeliveredBytes", {}).get("total", 0)),
        })
    return rows


def extract_uci_stats(obj):
    rows = []
    for st in obj.get("stats", []):
        ue = st.get("duUeIndex", 0)
        if ue == GHOST_UE:
            continue
        csi = st.get("csi", {})
        cqi = csi.get("cqi", {})
        ri = csi.get("ri", {})
        cqi_count = cqi.get("count", 0)
        cqi_total = int(cqi.get("total", 0))
        avg_cqi = cqi_total / cqi_count if cqi_count else 0.0
        rows.append({
            "duUeIndex": ue,
            "avg_cqi": round(avg_cqi, 2),
            "cqi_min": cqi.get("min", 0),
            "cqi_max": cqi.get("max", 0),
            "cqi_count": cqi_count,
            "ri_max": ri.get("max", 0),
            "sr_detected": st.get("srDetected", 0),
        })
    return rows


EXTRACTORS = {
    "crc_stats": extract_crc_stats,
    "bsr_stats": extract_bsr_stats,
    "harq_stats": extract_harq_stats,
    "jbpf_out_perf_list": extract_jbpf_out_perf_list,
    "rlc_ul_stats": extract_rlc_ul_stats,
    "uci_stats": extract_uci_stats,
}


# ---------------------------------------------------------------------------
# Main export logic
# ---------------------------------------------------------------------------

def build_scenario_list_stress(base_dir: Path):
    """Return list of (scenario_id, label, category, logpath) from stress manifest."""
    manifest = base_dir / "manifest.csv"
    scenarios = []
    with open(manifest, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["id"].strip()
            label = row["label"].strip()
            cat = row["category"].strip()
            logfile = Path(row["logfile"].strip())
            if logfile.exists():
                scenarios.append((sid, label, cat, logfile))
    return scenarios


def build_scenario_list_channel(base_dir: Path):
    """Return list of (scenario_id, label, category, logpath) from channel manifest + extra logs."""
    # Parse manifest
    manifest = base_dir / "manifest.csv"
    manifest_ids = {}
    if manifest.exists():
        with open(manifest, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = row["id"].strip()
                label = row["label"].strip()
                cat = row["category"].strip()
                logfile = Path(row["logfile"].strip())
                manifest_ids[sid] = (sid, label, cat, logfile)

    # Also scan for log files not in manifest
    scenarios = []
    for logfile in sorted(base_dir.glob("*.log")):
        fname = logfile.stem  # e.g. B1_baseline_indoor_los
        parts = fname.split("_", 1)
        sid = parts[0]
        label = parts[1] if len(parts) > 1 else fname
        if sid in manifest_ids:
            scenarios.append(manifest_ids[sid])
        else:
            # Infer category from prefix
            if sid.startswith("B"):
                cat = "baseline"
            elif sid.startswith("T"):
                cat = "time_varying"
            elif sid.startswith("S"):
                cat = "steady_impairment"
            elif sid.startswith("L"):
                cat = "rlf_cycle"
            else:
                cat = "unknown"
            scenarios.append((sid, label, cat, logfile))
    return scenarios


def export_dataset(scenarios, out_dir: Path, dataset_name: str):
    """Export all scenarios to CSV files in out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Accumulate rows: schema -> list of row dicts
    all_rows = {schema: [] for schema in EXTRACTORS}
    # Also collect any unknown schemas
    unknown_schemas = {}

    for scenario_id, label, category, logpath in scenarios:
        print(f"  [{dataset_name}] Parsing {scenario_id} ({label}) from {logpath.name} ...")
        first_unix = None
        msg_count = 0

        for ts_str, obj in parse_log_lines(logpath):
            schema = obj.get("_schema_proto_msg", "")
            if schema not in EXTRACTORS:
                unknown_schemas[schema] = unknown_schemas.get(schema, 0) + 1
                continue

            ts_unix = ts_to_unix(ts_str)
            ts_utc = ts_to_utc(ts_str)
            if first_unix is None:
                first_unix = ts_unix

            rel_s = round(ts_unix - first_unix, 3)

            extractor = EXTRACTORS[schema]
            extracted = extractor(obj)

            for row in extracted:
                row["scenario_id"] = scenario_id
                row["label"] = label
                row["category"] = category
                row["timestamp_utc"] = ts_utc
                row["timestamp_unix"] = ts_unix
                row["relative_s"] = rel_s
                all_rows[schema].append(row)

            msg_count += 1

        print(f"    -> {msg_count} REC messages parsed")

    # Write CSV files
    row_counts = {}
    for schema, rows in all_rows.items():
        if not rows:
            print(f"  [{dataset_name}] {schema}: 0 rows (skipping)")
            row_counts[schema] = 0
            continue

        csv_path = out_dir / f"{schema}.csv"
        # Determine column order: common columns first, then schema-specific
        common_cols = ["scenario_id", "label", "category", "timestamp_utc", "timestamp_unix", "relative_s"]
        all_keys = set()
        for r in rows:
            all_keys.update(r.keys())
        extra_cols = sorted(all_keys - set(common_cols))
        fieldnames = common_cols + extra_cols

        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        row_counts[schema] = len(rows)
        print(f"  [{dataset_name}] {schema}: {len(rows)} rows -> {csv_path}")

    if unknown_schemas:
        print(f"  [{dataset_name}] Skipped schemas: {dict(sorted(unknown_schemas.items()))}")

    return row_counts


def main():
    print("=" * 60)
    print("EXPORT ALL DATASETS TO CSV")
    print("=" * 60)

    # --- Stress dataset ---
    print(f"\n--- Stress anomaly dataset ({STRESS_DIR}) ---")
    stress_scenarios = build_scenario_list_stress(STRESS_DIR)
    print(f"Found {len(stress_scenarios)} scenarios")
    stress_csv_dir = STRESS_DIR / "csv"
    stress_counts = export_dataset(stress_scenarios, stress_csv_dir, "stress")

    # --- Channel dataset ---
    print(f"\n--- Channel dataset ({CHANNEL_DIR}) ---")
    channel_scenarios = build_scenario_list_channel(CHANNEL_DIR)
    print(f"Found {len(channel_scenarios)} scenarios")
    channel_csv_dir = CHANNEL_DIR / "csv"
    channel_counts = export_dataset(channel_scenarios, channel_csv_dir, "channel")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("EXPORT SUMMARY")
    print("=" * 60)
    print(f"\nStress dataset ({len(stress_scenarios)} scenarios):")
    for schema, count in sorted(stress_counts.items()):
        print(f"  {schema}: {count} rows")
    print(f"\nChannel dataset ({len(channel_scenarios)} scenarios):")
    for schema, count in sorted(channel_counts.items()):
        print(f"  {schema}: {count} rows")


if __name__ == "__main__":
    main()
