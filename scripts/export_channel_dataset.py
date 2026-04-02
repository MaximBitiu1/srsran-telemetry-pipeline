#!/usr/bin/env python3
"""
export_channel_dataset.py
=========================
Converts raw decoder logs from a channel dataset collection run into
structured CSV and HDF5 files with timestamps.

For each decoder log (one per scenario) the script extracts every known
telemetry schema into a flat tabular form and writes:

  <dataset_dir>/csv/
      crc_stats.csv          — MAC CRC: HARQ failures, SINR, Tx counts
      bsr_stats.csv          — MAC BSR: buffer bytes, count
      harq_stats.csv         — HARQ MCS, retx counts (DL + UL)
      uci_stats.csv          — UCI: CQI, SR, timing advance
      rlc_ul_stats.csv       — RLC UL: SDU delay, PDU bytes
      rlc_dl_stats.csv       — RLC DL: SDU delay, PDU bytes
      pdcp_ul_stats.csv      — PDCP UL: bytes
      pdcp_dl_stats.csv      — PDCP DL: bytes

  <dataset_dir>/channel_dataset.h5
      /scenarios/<id>/crc_stats   — dataset, attrs: label, category, flags
      /scenarios/<id>/bsr_stats
      ...

All CSV and HDF5 records include:
  - timestamp_utc   (ISO-8601 string in CSV; Unix float64 in HDF5)
  - relative_s      (seconds from start of this scenario's log)
  - scenario_id     (B1, R1, E2, ...)
  - label           (full scenario filename stem)
  - category        (baseline / high_prob / edge_case)

Usage:
    python3 export_channel_dataset.py <dataset_dir>
    python3 export_channel_dataset.py <dataset_dir> --format csv      # CSV only
    python3 export_channel_dataset.py <dataset_dir> --format hdf5     # HDF5 only
    python3 export_channel_dataset.py <dataset_dir> --format both     # default
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    HDF5_AVAILABLE = False
    print("[WARN] h5py not installed — HDF5 output disabled (pip install h5py)")


# ── Schema extraction functions ───────────────────────────────────────────────
# Each returns a list of flat dicts (one per stats entry in the message).
# All receive the parsed JSON data dict and the wall-clock datetime.

DL_STREAM = "4e1ae9d5f08e"
UL_STREAM  = "2a440fdb"

def _safe_div(a, b):
    try:
        return float(a) / float(b) if float(b) != 0 else 0.0
    except (TypeError, ValueError):
        return 0.0

def extract_crc_stats(data, ts):
    rows = []
    for s in data.get("stats", []):
        if s.get("duUeIndex", 0) == 513:
            continue
        rows.append({
            "harq_failure":    int(s.get("harqFailure", 0)),
            "succ_tx":         int(s.get("succTx", 0)),
            "cnt_tx":          int(s.get("cntTx", 0)),
            "sum_sinr":        float(s.get("sumSinr", 0)),
            "cnt_sinr":        int(s.get("cntSinr", 0)),
            "avg_sinr":        _safe_div(s.get("sumSinr", 0), s.get("cntSinr", 0)),
            "du_ue_index":     int(s.get("duUeIndex", 0)),
        })
    return rows

def extract_bsr_stats(data, ts):
    rows = []
    for s in data.get("stats", []):
        rows.append({
            "bytes":       int(s.get("bytes", 0)),
            "cnt":         int(s.get("cnt", 0)),
            "du_ue_index": int(s.get("duUeIndex", 0)),
        })
    return rows

def extract_harq_stats(data, ts):
    rows = []
    stream_id = data.get("_stream_id", "")
    direction = "dl" if DL_STREAM in stream_id else ("ul" if UL_STREAM in stream_id else "unknown")
    for s in data.get("stats", []):
        if s.get("duUeIndex", 0) == 513:
            continue
        mcs = s.get("mcs", {})
        cr  = s.get("consRetx", {})
        phs = s.get("perHarqTypeStats", [{}])
        tbs = phs[0].get("tbsBytes", {}) if phs else {}
        rows.append({
            "direction":       direction,
            "mcs_avg":         _safe_div(int(mcs.get("total", 0)), int(mcs.get("count", 1))),
            "mcs_min":         int(mcs.get("min", 0)),
            "mcs_max":         int(mcs.get("max", 0)),
            "mcs_count":       int(mcs.get("count", 0)),
            "retx_count":      int(cr.get("count", 0)),
            "retx_max":        int(cr.get("max", 0)),
            "tbs_bytes_total": int(tbs.get("total", 0)),
            "tbs_count":       int(tbs.get("count", 0)) if phs else 0,
            "du_ue_index":     int(s.get("duUeIndex", 0)),
        })
    return rows

def extract_uci_stats(data, ts):
    rows = []
    for s in data.get("stats", []):
        csi = s.get("csi", {})
        cqi = csi.get("cqi", {})
        ri  = csi.get("ri", {})
        ta  = s.get("timeAdvanceOffset", {})
        ta_total = int(ta.get("total", 0))
        ta_count = int(ta.get("count", 0))
        ta_avg   = _safe_div(ta_total, ta_count)
        # Sentinel filter: TA values > 1e12 ns (1000s) are uninitialised memory
        if ta_avg > 1e12:
            ta_total = 0
            ta_count = 0
            ta_avg   = 0.0
        rows.append({
            "sr_detected":     int(s.get("srDetected", 0)),
            "cqi_total":       float(cqi.get("total", 0)),
            "cqi_count":       int(cqi.get("count", 0)),
            "cqi_avg":         _safe_div(cqi.get("total", 0), cqi.get("count", 0)),
            "ri_total":        float(ri.get("total", 0)),
            "ri_count":        int(ri.get("count", 0)),
            "ri_avg":          _safe_div(ri.get("total", 0), ri.get("count", 0)),
            "ta_total":        ta_total,
            "ta_count":        ta_count,
            "ta_avg":          ta_avg,
            "du_ue_index":     int(s.get("duUeIndex", 0)),
        })
    return rows

def _int_field(d, key):
    """Extract integer from a plain int or a {count, total} dict field."""
    v = d.get(key, 0)
    if isinstance(v, dict):
        return int(v.get("total", 0))
    return int(v) if v is not None else 0

def _count_field(d, key):
    v = d.get(key, {})
    if isinstance(v, dict):
        return int(v.get("count", 0))
    return 0

def _max_field(d, key):
    v = d.get(key, {})
    if isinstance(v, dict):
        return int(v.get("max", 0))
    return 0

def extract_rlc_ul_stats(data, ts):
    # Fields: pduBytes{count,total}, sduDeliveredBytes{count,total},
    #         sduDeliveredLatency{count,max,min,total}
    rows = []
    for s in data.get("stats", []):
        if s.get("duUeIndex", 0) == 513:
            continue
        lat = s.get("sduDeliveredLatency", {})
        lat_count = int(lat.get("count", 0)) if isinstance(lat, dict) else 0
        lat_total = int(lat.get("total", 0)) if isinstance(lat, dict) else 0
        lat_max   = int(lat.get("max", 0))   if isinstance(lat, dict) else 0
        rows.append({
            "pdu_bytes_total":    _int_field(s, "pduBytes"),
            "pdu_count":          _count_field(s, "pduBytes"),
            "sdu_delivered_bytes": _int_field(s, "sduDeliveredBytes"),
            "sdu_delay_count":    lat_count,
            "sdu_delay_sum_ns":   lat_total,
            "sdu_delay_avg_ns":   _safe_div(lat_total, lat_count),
            "sdu_delay_max_ns":   lat_max,
            "du_ue_index":        int(s.get("duUeIndex", 0)),
        })
    return rows

def extract_rlc_dl_stats(data, ts):
    # Fields: pduTxBytes{count,total}, sduQueueBytes{count,max,total},
    #         sduTxCompleted{count,max,total}
    rows = []
    for s in data.get("stats", []):
        if s.get("duUeIndex", 0) == 513:
            continue
        queue = s.get("sduQueueBytes", {})
        rows.append({
            "pdu_tx_bytes":      _int_field(s, "pduTxBytes"),
            "sdu_new_bytes":     _int_field(s, "sduNewBytes"),
            "sdu_queue_bytes_avg": _safe_div(
                int(queue.get("total", 0)) if isinstance(queue, dict) else 0,
                int(queue.get("count", 1)) if isinstance(queue, dict) else 1,
            ),
            "sdu_queue_bytes_max": _max_field(s, "sduQueueBytes"),
            "du_ue_index":       int(s.get("duUeIndex", 0)),
        })
    return rows

def extract_dl_stats(data, ts):
    # PDCP DL (CU-level): dataPduTxBytes, sduTxLatency{count,max,total}
    rows = []
    for s in data.get("stats", []):
        lat = s.get("sduTxLatency", {})
        lat_count = int(lat.get("count", 0)) if isinstance(lat, dict) else 0
        lat_total = int(lat.get("total", 0)) if isinstance(lat, dict) else 0
        lat_max   = int(lat.get("max", 0))   if isinstance(lat, dict) else 0
        rows.append({
            "data_pdu_tx_bytes":  _int_field(s, "dataPduTxBytes"),
            "data_pdu_retx_bytes": _int_field(s, "dataPduRetxBytes"),
            "sdu_tx_latency_count": lat_count,
            "sdu_tx_latency_avg_ns": _safe_div(lat_total, lat_count),
            "sdu_tx_latency_max_ns": lat_max,
            "cu_ue_index":        int(s.get("cuUeIndex", 0)),
        })
    return rows

def extract_ul_stats(data, ts):
    # PDCP UL (CU-level): rxDataPduBytes, sduDeliveredBytes
    rows = []
    for s in data.get("stats", []):
        rows.append({
            "rx_data_pdu_bytes":   _int_field(s, "rxDataPduBytes"),
            "sdu_delivered_bytes": _int_field(s, "sduDeliveredBytes"),
            "cu_ue_index":         int(s.get("cuUeIndex", 0)),
        })
    return rows


def extract_jbpf_out_perf_list(data, ts):
    """Extract jBPF hook latency percentiles — unique thesis contribution (no E2SM-KPM equivalent)."""
    rows = []
    for h in data.get("hookPerf", []):
        name = h.get("hookName", "")
        num = int(h.get("num", 0))
        if num == 0:
            continue  # skip hooks with no calls this window
        rows.append({
            "hook_name":  name,
            "call_count": num,
            "min_ns":     int(h.get("min", 0)),
            "max_ns":     int(h.get("max", 0)),
            "p50_ns":     int(h.get("p50", 0)),
            "p90_ns":     int(h.get("p90", 0)),
            "p95_ns":     int(h.get("p95", 0)),
            "p99_ns":     int(h.get("p99", 0)),
        })
    return rows

def extract_dl_config_stats(data, ts):
    """Extract FAPI DL TTI scheduling stats per RNTI."""
    rows = []
    for s in data.get("stats", []):
        rnti = int(s.get("rnti", 0))
        if rnti == 0:
            continue
        rows.append({
            "rnti":       rnti,
            "cell_id":    int(s.get("cellId", 0)),
            "mcs_avg":    int(s.get("l1McsAvg", 0)),
            "mcs_min":    int(s.get("l1McsMin", 0)),
            "mcs_max":    int(s.get("l1McsMax", 0)),
            "prb_avg":    int(s.get("l1PrbAvg", 0)),
            "prb_min":    int(s.get("l1PrbMin", 0)),
            "prb_max":    int(s.get("l1PrbMax", 0)),
            "tbs_avg":    int(s.get("l1TbsAvg", 0)),
            "tbs_min":    int(s.get("l1TbsMin", 0)),
            "tbs_max":    int(s.get("l1TbsMax", 0)),
            "dl_tx":      int(s.get("l1DlcTx", 0)),
            "l1_cnt":     int(s.get("l1Cnt", 0)),
        })
    return rows

def extract_ul_config_stats(data, ts):
    """Extract FAPI UL TTI scheduling stats per RNTI."""
    rows = []
    for s in data.get("stats", []):
        rnti = int(s.get("rnti", 0))
        if rnti == 0:
            continue
        rows.append({
            "rnti":       rnti,
            "cell_id":    int(s.get("cellId", 0)),
            "mcs_avg":    int(s.get("l1McsAvg", 0)),
            "mcs_min":    int(s.get("l1McsMin", 0)),
            "mcs_max":    int(s.get("l1McsMax", 0)),
            "prb_avg":    int(s.get("l1PrbAvg", 0)),
            "prb_min":    int(s.get("l1PrbMin", 0)),
            "prb_max":    int(s.get("l1PrbMax", 0)),
            "tbs_avg":    int(s.get("l1TbsAvg", 0)),
            "tbs_min":    int(s.get("l1TbsMin", 0)),
            "tbs_max":    int(s.get("l1TbsMax", 0)),
            "l1_cnt":     int(s.get("l1Cnt", 0)),
        })
    return rows


def extract_rach_stats(data, ts):
    # One record per RACH attempt — marks a re-attachment or initial attach event
    return [{"event": 1, "preamble_index": int(data.get("preambleIndex", 0))}]

def extract_rrc_ue_add(data, ts):
    return [{
        "event":   1,
        "c_rnti":  int(data.get("cRnti", 0)),
        "pci":     int(data.get("pci", 0)),
    }]

RRC_PROC_NAMES = {1: "RRCSetup", 2: "RRCReconfig", 3: "RRCReestab", 4: "SecurityMode"}

def extract_rrc_ue_procedure(data, ts):
    proc_id = int(data.get("procedure", 0))
    return [{
        "event":        1,
        "procedure_id": proc_id,
        "procedure":    RRC_PROC_NAMES.get(proc_id, f"proc_{proc_id}"),
        "success":      1 if data.get("success") else 0,
    }]

def extract_rrc_ue_remove(data, ts):
    return [{"event": 1}]

NGAP_PROC_NAMES = {
    1: "InitialUEMessage", 2: "UEContextRelease",
    3: "InitialContextSetup", 4: "PDUSessionSetup", 5: "HandoverPrep",
}

def extract_ngap_procedure_started(data, ts):
    proc_id = int(data.get("procedure", 0))
    return [{
        "event":        1,
        "procedure_id": proc_id,
        "procedure":    NGAP_PROC_NAMES.get(proc_id, f"proc_{proc_id}"),
        "phase":        "started",
    }]

def extract_ngap_procedure_completed(data, ts):
    proc_id = int(data.get("procedure", 0))
    return [{
        "event":        1,
        "procedure_id": proc_id,
        "procedure":    NGAP_PROC_NAMES.get(proc_id, f"proc_{proc_id}"),
        "phase":        "completed",
        "success":      1 if data.get("success") else 0,
    }]


# Schema → extractor mapping
EXTRACTORS = {
    "crc_stats":                  extract_crc_stats,
    "bsr_stats":                  extract_bsr_stats,
    "harq_stats":                 extract_harq_stats,
    "uci_stats":                  extract_uci_stats,
    "rlc_ul_stats":               extract_rlc_ul_stats,
    "rlc_dl_stats":               extract_rlc_dl_stats,
    "dl_stats":                   extract_dl_stats,
    "ul_stats":                   extract_ul_stats,
    # FAPI scheduling + jBPF hook latency
    "jbpf_out_perf_list":         extract_jbpf_out_perf_list,
    "dl_config_stats":            extract_dl_config_stats,
    "ul_config_stats":            extract_ul_config_stats,
    # Event-driven schemas — critical for RLF cycle scenarios
    "rach_stats":                 extract_rach_stats,
    "rrc_ue_add":                 extract_rrc_ue_add,
    "rrc_ue_procedure":           extract_rrc_ue_procedure,
    "rrc_ue_remove":              extract_rrc_ue_remove,
    "ngap_procedure_started":     extract_ngap_procedure_started,
    "ngap_procedure_completed":   extract_ngap_procedure_completed,
}

# ── Log parser ────────────────────────────────────────────────────────────────
def parse_log(path, scenario_id, label, category):
    """
    Parse a decoder log file.
    Returns dict: schema_name → list of row dicts (with timestamp fields injected).
    """
    result = defaultdict(list)
    t0 = None

    # Read as binary to handle logs with null-byte sparse holes (from tee
    # truncation race).  Split on newlines, decode only lines that start with
    # b'time=' — this avoids creating giant strings from null-padded regions.
    with open(path, "rb") as f:
        raw_data = f.read()
    lines = raw_data.split(b"\n")
    del raw_data  # free memory

    for raw_line in lines:
        # Fast pre-filter: skip lines that cannot match (null padding, recv, etc.)
        if not raw_line.startswith(b"time="):
            continue
        line = raw_line.decode("utf-8", errors="replace")
        m = re.match(r'^time="([^"]+)".*msg="REC: (.+)"$', line.strip())
        if not m:
            continue
        ts_str, raw = m.group(1), m.group(2)
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        raw = raw.replace('\\"', '"')
        if raw.startswith('"'): raw = raw[1:]
        if raw.endswith('"'):   raw = raw[:-1]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        schema = data.get("_schema_proto_msg", "")
        pkg    = data.get("_schema_proto_package", "")
        # Disambiguate FAPI vs MAC crc_stats by package name
        if schema == "crc_stats" and "fapi" in pkg:
            schema = "fapi_crc_stats"  # we skip FAPI CRC for now (cumulative sums)
            continue

        extractor = EXTRACTORS.get(schema)
        if extractor is None:
            continue

        if t0 is None:
            t0 = ts

        rows = extractor(data, ts)
        rel_s = (ts - t0).total_seconds()
        ts_unix = ts.timestamp()

        for row in rows:
            row["timestamp_utc"] = ts.isoformat()
            row["timestamp_unix"] = ts_unix
            row["relative_s"]    = round(rel_s, 3)
            row["scenario_id"]   = scenario_id
            row["label"]         = label
            row["category"]      = category
            result[schema].append(row)

    return result


# ── CSV writer ────────────────────────────────────────────────────────────────
# Columns are written in a defined order: metadata first, then schema fields.
META_COLS = ["scenario_id", "label", "category", "timestamp_utc", "timestamp_unix", "relative_s"]

def write_csv(all_schema_rows, out_dir):
    """
    all_schema_rows: dict schema → list of row dicts (accumulated across all scenarios)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for schema, rows in sorted(all_schema_rows.items()):
        if not rows:
            continue
        # Collect all field names (preserve insertion order, meta first)
        all_keys = list(META_COLS)
        for row in rows:
            for k in row:
                if k not in all_keys:
                    all_keys.append(k)

        out_path = out_dir / f"{schema}.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        written[schema] = (out_path, len(rows))
        print(f"  CSV  {schema}.csv  ({len(rows)} rows)")
    return written


# ── HDF5 writer ───────────────────────────────────────────────────────────────
def write_hdf5(per_scenario_data, out_path):
    """
    per_scenario_data: dict scenario_id → {schema → list of row dicts, 'meta': {...}}
    """
    with h5py.File(out_path, "w") as hf:
        for sid, scenario in sorted(per_scenario_data.items()):
            meta  = scenario.get("meta", {})
            grp   = hf.require_group(f"scenarios/{sid}")
            grp.attrs["label"]    = meta.get("label", sid)
            grp.attrs["category"] = meta.get("category", "")
            grp.attrs["flags"]    = meta.get("flags", "")

            for schema, rows in scenario.items():
                if schema == "meta" or not rows:
                    continue

                # Gather numeric + string columns separately
                all_keys = [k for k in rows[0] if k not in ("timestamp_utc", "scenario_id", "label", "category")]
                str_keys  = ["timestamp_utc"]
                num_keys  = [k for k in all_keys if k not in str_keys]

                ds_grp = grp.require_group(schema)

                # Timestamps as fixed-length strings
                ts_arr = np.array([r["timestamp_utc"].encode("ascii") for r in rows],
                                  dtype="S32")
                ds_grp.create_dataset("timestamp_utc", data=ts_arr, compression="gzip")

                # Numeric columns as float64 arrays
                for col in num_keys:
                    try:
                        arr = np.array([float(r.get(col, 0)) for r in rows], dtype=np.float64)
                        ds_grp.create_dataset(col, data=arr, compression="gzip")
                    except (TypeError, ValueError):
                        pass  # skip non-numeric

                ds_grp.attrs["n_rows"] = len(rows)
                ds_grp.attrs["schema"] = schema

    print(f"  HDF5 {out_path.name}")


# ── Manifest loader ───────────────────────────────────────────────────────────
def load_manifest(dataset_dir):
    """
    Returns list of dicts: id, label, category, flags, logfile.
    Falls back to scanning *.log files if manifest.csv absent.
    """
    manifest_path = dataset_dir / "manifest.csv"
    entries = []

    if manifest_path.exists():
        with open(manifest_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row.get("status", "complete")
                if status in ("dry_run", "failed_start", "ue_no_attach", "no_data"):
                    continue
                logfile = Path(row.get("logfile", ""))
                if not logfile.exists():
                    # Try relative to dataset_dir
                    logfile = dataset_dir / logfile.name
                if not logfile.exists():
                    continue
                entries.append({
                    "id":       row["id"].strip(),
                    "label":    row["label"].strip(),
                    "category": row["category"].strip(),
                    "flags":    row.get("flags", "").strip('"'),
                    "logfile":  logfile,
                })

    # Fallback: if manifest is missing or empty (header-only), scan *.log files
    if not entries:
        # Fallback: scan for *.log files, infer id from filename
        for lf in sorted(dataset_dir.glob("*.log")):
            parts = lf.stem.split("_", 1)
            sid   = parts[0] if parts else lf.stem
            label = lf.stem
            entries.append({
                "id": sid, "label": label, "category": "unknown",
                "flags": "", "logfile": lf,
            })

    return entries


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Export channel dataset logs → CSV + HDF5")
    parser.add_argument("dataset_dir", help="Path to channel_dataset/<timestamp>/ directory")
    parser.add_argument("--format", choices=["csv", "hdf5", "both"], default="both",
                        help="Output format (default: both)")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).expanduser().resolve()
    if not dataset_dir.is_dir():
        print(f"ERROR: {dataset_dir} is not a directory")
        sys.exit(1)

    print(f"Dataset : {dataset_dir}")

    entries = load_manifest(dataset_dir)
    if not entries:
        print("ERROR: No valid scenario logs found (check manifest.csv or *.log files)")
        sys.exit(1)

    print(f"Scenarios to export: {len(entries)}")
    print()

    # Accumulate rows per schema across all scenarios (for CSV)
    all_schema_rows = defaultdict(list)
    # Per-scenario data (for HDF5)
    per_scenario_data = {}

    for entry in entries:
        sid      = entry["id"]
        label    = entry["label"]
        category = entry["category"]
        logfile  = entry["logfile"]
        flags    = entry["flags"]

        print(f"  Parsing [{sid}] {logfile.name} ...", end=" ", flush=True)
        schema_rows = parse_log(logfile, sid, label, category)
        total = sum(len(v) for v in schema_rows.values())
        print(f"{total} records across {len(schema_rows)} schemas")

        for schema, rows in schema_rows.items():
            all_schema_rows[schema].extend(rows)

        per_scenario_data[sid] = dict(schema_rows)
        per_scenario_data[sid]["meta"] = {
            "label": label, "category": category, "flags": flags,
        }

    print()

    do_csv  = args.format in ("csv", "both")
    do_hdf5 = args.format in ("hdf5", "both") and HDF5_AVAILABLE

    if do_csv:
        csv_dir = dataset_dir / "csv"
        print(f"Writing CSV → {csv_dir}/")
        write_csv(all_schema_rows, csv_dir)

    if do_hdf5:
        hdf5_path = dataset_dir / "channel_dataset.h5"
        print(f"\nWriting HDF5 → {hdf5_path}")
        write_hdf5(per_scenario_data, hdf5_path)
    elif args.format in ("hdf5", "both") and not HDF5_AVAILABLE:
        print("[WARN] Skipping HDF5 — h5py not available. Install with: pip install h5py")

    print()
    print("Export complete.")
    print(f"  CSV files : {dataset_dir / 'csv'}/")
    if do_hdf5:
        print(f"  HDF5 file : {dataset_dir / 'channel_dataset.h5'}")
    print()
    print("Schema summary:")
    for schema, rows in sorted(all_schema_rows.items()):
        scenarios_present = sorted({r["scenario_id"] for r in rows})
        print(f"  {schema:<20} {len(rows):>6} rows  scenarios: {', '.join(scenarios_present)}")


if __name__ == "__main__":
    main()
