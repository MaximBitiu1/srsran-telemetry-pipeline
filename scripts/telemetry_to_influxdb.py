#!/usr/bin/env python3
"""
Real-time InfluxDB Ingestor for srsRAN 5G NR jBPF Telemetry.

Tails the decoder log file and writes parsed telemetry data
to InfluxDB in real-time for Grafana visualization.

Usage:
    python3 telemetry_to_influxdb.py [--log /tmp/decoder.log] [--db srsran_telemetry] [--host localhost]
    python3 telemetry_to_influxdb.py --replay /tmp/decoder_snr30_fading_allcodelets.log

Modes:
    Live (default): tail -f on decoder log, writes new records as they arrive
    Replay: ingest an existing log file (e.g., from a previous collection run)
"""
import argparse
import json
import os
import re
import signal
import sys
import time
from datetime import datetime
from influxdb import InfluxDBClient

# ── Configuration ────────────────────────────────────────────────────────────
DEFAULT_LOG = "/tmp/decoder.log"
DEFAULT_DB = "srsran_telemetry"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8086
BATCH_SIZE = 50          # Write every N points
FLUSH_INTERVAL = 2.0     # Or flush every N seconds
TAIL_POLL_INTERVAL = 0.1 # seconds between tail polls

# ── Global state ─────────────────────────────────────────────────────────────
running = True
stats = {"parsed": 0, "written": 0, "errors": 0, "skipped": 0}

def signal_handler(sig, frame):
    global running
    print(f"\n[INFO] Caught signal {sig}, flushing and exiting...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ── Log line parser ──────────────────────────────────────────────────────────
LINE_RE = re.compile(r'^time="([^"]+)".*msg="REC: (.+)"$')

def parse_line(line):
    """Parse a decoder log line → (timestamp, schema, package, data_dict) or None."""
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    ts_str, raw = m.group(1), m.group(2)
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        return None
    raw = raw.replace('\\"', '"')
    if raw.startswith('"'):
        raw = raw[1:]
    if raw.endswith('"'):
        raw = raw[:-1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    schema = data.get("_schema_proto_msg", "unknown")
    pkg = data.get("_schema_proto_package", "")
    # Disambiguate crc_stats (MAC vs FAPI)
    if schema == "crc_stats" and pkg == "fapi_gnb_crc_stats":
        schema = "fapi_crc_stats"
    return ts, schema, pkg, data

# ── Schema → InfluxDB points ────────────────────────────────────────────────
def safe_div(a, b, default=0.0):
    return float(a) / float(b) if b else default

def safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

UINT32_MAX = 4294967295

def make_points(ts, schema, pkg, data):
    """Convert a parsed telemetry record into a list of InfluxDB point dicts."""
    iso_ts = ts.isoformat()
    points = []

    if schema == "crc_stats":
        # MAC CRC Stats
        for s in data.get("stats", []):
            ue = s.get("duUeIndex", 0)
            if ue == 513 or ue >= 32:
                continue
            cnt_sinr = safe_int(s.get("cntSinr", 0))
            cnt_rsrp = safe_int(s.get("cntRsrp", 0))
            min_sinr = safe_int(s.get("minSinr", 0))
            max_sinr = safe_int(s.get("maxSinr", 0))
            if min_sinr == UINT32_MAX or min_sinr == 32767:
                min_sinr = 0
            if max_sinr == -32768:
                max_sinr = 0
            points.append({
                "measurement": "mac_crc_stats",
                "tags": {"ue": str(ue)},
                "time": iso_ts,
                "fields": {
                    "succ_tx": safe_int(s.get("succTx", 0)),
                    "cnt_tx": safe_int(s.get("cntTx", 0)),
                    "harq_failure": safe_int(s.get("harqFailure", 0)),
                    "avg_sinr": safe_div(s.get("sumSinr", 0), cnt_sinr),
                    "min_sinr": float(min_sinr),
                    "max_sinr": float(max_sinr),
                    "avg_rsrp": safe_div(s.get("sumRsrp", 0), cnt_rsrp),
                    "tx_success_rate": safe_div(s.get("succTx", 0), s.get("cntTx", 1)) * 100.0,
                }
            })

    elif schema == "bsr_stats":
        # MAC BSR Stats
        for s in data.get("stats", []):
            ue = s.get("duUeIndex", 0)
            if ue == 513 or ue >= 32:
                continue
            b = safe_int(s.get("bytes", 0))
            c = safe_int(s.get("cnt", 0))
            points.append({
                "measurement": "mac_bsr_stats",
                "tags": {"ue": str(ue)},
                "time": iso_ts,
                "fields": {
                    "total_bytes": b,
                    "count": c,
                    "avg_bytes_per_report": safe_div(b, c),
                }
            })

    elif schema == "uci_stats":
        # MAC UCI Stats
        for s in data.get("stats", []):
            ue = s.get("duUeIndex", 0)
            if ue == 513 or ue >= 32:
                continue
            csi = s.get("csi", {})
            cqi = csi.get("cqi", {})
            ri = csi.get("ri", {})
            ta = s.get("timeAdvanceOffset", {})
            points.append({
                "measurement": "mac_uci_stats",
                "tags": {"ue": str(ue)},
                "time": iso_ts,
                "fields": {
                    "avg_cqi": safe_div(cqi.get("total", 0), cqi.get("count", 0)),
                    "avg_ri": safe_div(ri.get("total", 0), ri.get("count", 0)),
                    "sr_detected": safe_int(s.get("srDetected", 0)),
                    "avg_timing_advance": safe_div(int(ta.get("total", 0)), ta.get("count", 0)),
                }
            })

    elif schema == "harq_stats":
        # MAC HARQ Stats (DL or UL determined by stream_id or alternation)
        stream_id = data.get("_stream_id", "")
        for s in data.get("stats", []):
            ue = s.get("duUeIndex", 0)
            if ue == 513 or ue >= 32:
                continue
            mcs = s.get("mcs", {})
            cr = s.get("consRetx", {})
            phs = s.get("perHarqTypeStats", [{}])
            tbs_total = safe_int(phs[0].get("tbsBytes", {}).get("total", 0)) if phs else 0
            tbs_count = safe_int(phs[0].get("count", 0)) if phs else 0
            mcs_min = safe_int(mcs.get("min", 0))
            mcs_max = safe_int(mcs.get("max", 0))
            if mcs_min == UINT32_MAX:
                mcs_min = 0
            points.append({
                "measurement": "mac_harq_stats",
                "tags": {"ue": str(ue), "stream_id": stream_id},
                "time": iso_ts,
                "fields": {
                    "avg_mcs": safe_div(int(mcs.get("total", 0)), int(mcs.get("count", 0))),
                    "min_mcs": float(mcs_min),
                    "max_mcs": float(mcs_max),
                    "retx_count": safe_int(cr.get("count", 0)),
                    "max_retx": safe_int(cr.get("max", 0)),
                    "tbs_bytes": tbs_total,
                    "tbs_count": tbs_count,
                }
            })

    elif schema == "rlc_dl_stats":
        total_pdu_tx = 0
        total_sdu_new = 0
        total_am_retx = 0
        total_sdu_queue = 0
        for s in data.get("stats", []):
            total_pdu_tx += safe_int(s.get("pduTxBytes", {}).get("total", 0))
            total_sdu_new += safe_int(s.get("sduNewBytes", {}).get("total", 0))
            am = s.get("am", {})
            if am:
                total_am_retx += safe_int(am.get("pduRetxCount", {}).get("total", 0))
            total_sdu_queue += safe_int(s.get("sduQueueBytes", {}).get("total", 0))
        points.append({
            "measurement": "rlc_dl_stats",
            "tags": {},
            "time": iso_ts,
            "fields": {
                "pdu_tx_bytes": total_pdu_tx,
                "sdu_new_bytes": total_sdu_new,
                "am_retx_count": total_am_retx,
                "sdu_queue_bytes": total_sdu_queue,
                "num_bearers": len(data.get("stats", [])),
            }
        })

    elif schema == "rlc_ul_stats":
        total_pdu_rx = 0
        total_sdu_deliv = 0
        total_lat_sum = 0
        total_lat_cnt = 0
        for s in data.get("stats", []):
            total_pdu_rx += safe_int(s.get("pduBytes", {}).get("total", 0))
            total_sdu_deliv += safe_int(s.get("sduDeliveredBytes", {}).get("total", 0))
            lat = s.get("sduDeliveredLatency", {})
            total_lat_sum += safe_int(lat.get("total", 0))
            total_lat_cnt += safe_int(lat.get("count", 0))
        points.append({
            "measurement": "rlc_ul_stats",
            "tags": {},
            "time": iso_ts,
            "fields": {
                "pdu_rx_bytes": total_pdu_rx,
                "sdu_delivered_bytes": total_sdu_deliv,
                "avg_sdu_latency": safe_div(total_lat_sum, total_lat_cnt),
            }
        })

    elif schema == "dl_stats":
        # PDCP DL
        total_data_tx = 0
        total_data_retx = 0
        total_ctrl_tx = 0
        total_lat_sum = 0
        total_lat_cnt = 0
        total_disc = 0
        for s in data.get("stats", []):
            total_data_tx += safe_int(s.get("dataPduTxBytes", {}).get("total", 0))
            total_data_retx += safe_int(s.get("dataPduRetxBytes", {}).get("total", 0))
            total_ctrl_tx += safe_int(s.get("controlPduTxBytes", {}).get("total", 0))
            lat = s.get("sduTxLatency", {})
            total_lat_sum += safe_int(lat.get("total", 0))
            total_lat_cnt += safe_int(lat.get("count", 0))
            total_disc += safe_int(s.get("sduDiscarded", 0))
        points.append({
            "measurement": "pdcp_dl_stats",
            "tags": {},
            "time": iso_ts,
            "fields": {
                "data_tx_bytes": total_data_tx,
                "data_retx_bytes": total_data_retx,
                "ctrl_tx_bytes": total_ctrl_tx,
                "avg_sdu_latency": safe_div(total_lat_sum, total_lat_cnt),
                "sdu_discarded": total_disc,
            }
        })

    elif schema == "ul_stats":
        # PDCP UL
        total_data_rx = 0
        total_sdu_deliv = 0
        total_ctrl_rx = 0
        for s in data.get("stats", []):
            total_data_rx += safe_int(s.get("rxDataPduBytes", {}).get("total", 0))
            total_sdu_deliv += safe_int(s.get("sduDeliveredBytes", {}).get("total", 0))
            total_ctrl_rx += safe_int(s.get("rxControlPduBytes", {}).get("total", 0))
        points.append({
            "measurement": "pdcp_ul_stats",
            "tags": {},
            "time": iso_ts,
            "fields": {
                "data_rx_bytes": total_data_rx,
                "sdu_delivered_bytes": total_sdu_deliv,
                "ctrl_rx_bytes": total_ctrl_rx,
            }
        })

    elif schema == "dl_config_stats":
        # FAPI DL Config
        for s in data.get("stats", []):
            rnti = safe_int(s.get("rnti", 0))
            if rnti <= 1000:
                continue  # Skip system/SIB RNTIs
            cnt = max(safe_int(s.get("l1Cnt", 1)), 1)
            points.append({
                "measurement": "fapi_dl_config",
                "tags": {"rnti": str(rnti)},
                "time": iso_ts,
                "fields": {
                    "avg_mcs": safe_float(s.get("l1McsAvg", 0)) / cnt,
                    "min_mcs": safe_float(s.get("l1McsMin", 0)),
                    "max_mcs": safe_float(s.get("l1McsMax", 0)),
                    "avg_prb": safe_float(s.get("l1PrbAvg", 0)) / cnt,
                    "min_prb": safe_float(s.get("l1PrbMin", 0)),
                    "max_prb": safe_float(s.get("l1PrbMax", 0)),
                    "avg_tbs": safe_float(s.get("l1TbsAvg", 0)) / cnt,
                    "total_tx": safe_int(s.get("l1DlcTx", 0)),
                    "l1_count": cnt,
                }
            })

    elif schema == "ul_config_stats":
        # FAPI UL Config
        for s in data.get("stats", []):
            cnt = max(safe_int(s.get("l1Cnt", 1)), 1)
            points.append({
                "measurement": "fapi_ul_config",
                "tags": {},
                "time": iso_ts,
                "fields": {
                    "avg_mcs": safe_float(s.get("l1McsAvg", 0)) / cnt,
                    "min_mcs": safe_float(s.get("l1McsMin", 0)),
                    "max_mcs": safe_float(s.get("l1McsMax", 0)),
                    "avg_prb": safe_float(s.get("l1PrbAvg", 0)) / cnt,
                    "min_prb": safe_float(s.get("l1PrbMin", 0)),
                    "max_prb": safe_float(s.get("l1PrbMax", 0)),
                    "avg_tbs": safe_float(s.get("l1TbsAvg", 0)) / cnt,
                    "l1_count": cnt,
                }
            })

    elif schema == "fapi_crc_stats":
        # FAPI CRC (PHY layer SNR + TA)
        for s in data.get("stats", []):
            snr_min = safe_int(s.get("l1SnrMin", 0))
            snr_max = safe_int(s.get("l1SnrMax", 0))
            ta_min = safe_int(s.get("l1TaMin", 0))
            ta_max = safe_int(s.get("l1TaMax", 0))
            if snr_min == UINT32_MAX:
                snr_min = 0
            if ta_min == UINT32_MAX:
                ta_min = 0
            points.append({
                "measurement": "fapi_crc_stats",
                "tags": {},
                "time": iso_ts,
                "fields": {
                    "snr_min": float(snr_min),
                    "snr_max": float(snr_max),
                    "ta_min": float(ta_min),
                    "ta_max": float(ta_max),
                }
            })

    elif schema == "rach_stats":
        # FAPI RACH (rare - one per attach)
        points.append({
            "measurement": "fapi_rach_stats",
            "tags": {},
            "time": iso_ts,
            "fields": {"event": 1}
        })

    elif schema == "rrc_ue_add":
        points.append({
            "measurement": "rrc_events",
            "tags": {"event_type": "ue_add"},
            "time": iso_ts,
            "fields": {
                "event": 1,
                "c_rnti": safe_int(data.get("cRnti", 0)),
                "pci": safe_int(data.get("pci", 0)),
            }
        })

    elif schema == "rrc_ue_procedure":
        proc_names = {1: "RRCSetup", 2: "RRCReconfig", 3: "RRCReestab", 4: "SecurityMode"}
        proc_id = safe_int(data.get("procedure", 0))
        points.append({
            "measurement": "rrc_events",
            "tags": {
                "event_type": "procedure",
                "procedure": proc_names.get(proc_id, f"proc_{proc_id}"),
            },
            "time": iso_ts,
            "fields": {
                "event": 1,
                "success": 1 if data.get("success") else 0,
                "procedure_id": proc_id,
            }
        })

    elif schema == "rrc_ue_remove":
        points.append({
            "measurement": "rrc_events",
            "tags": {"event_type": "ue_remove"},
            "time": iso_ts,
            "fields": {"event": 1}
        })

    elif schema == "ngap_procedure_started":
        ngap_names = {1: "InitialUEMessage", 2: "UEContextRelease",
                      3: "InitialContextSetup", 4: "PDUSessionSetup", 5: "HandoverPrep"}
        proc_id = safe_int(data.get("procedure", 0))
        points.append({
            "measurement": "ngap_events",
            "tags": {
                "event_type": "started",
                "procedure": ngap_names.get(proc_id, f"proc_{proc_id}"),
            },
            "time": iso_ts,
            "fields": {
                "event": 1,
                "procedure_id": proc_id,
            }
        })

    elif schema == "ngap_procedure_completed":
        ngap_names = {1: "InitialUEMessage", 2: "UEContextRelease",
                      3: "InitialContextSetup", 4: "PDUSessionSetup", 5: "HandoverPrep"}
        proc_id = safe_int(data.get("procedure", 0))
        points.append({
            "measurement": "ngap_events",
            "tags": {
                "event_type": "completed",
                "procedure": ngap_names.get(proc_id, f"proc_{proc_id}"),
            },
            "time": iso_ts,
            "fields": {
                "event": 1,
                "success": 1 if data.get("success") else 0,
                "procedure_id": proc_id,
            }
        })

    elif schema == "jbpf_out_perf_list":
        for hp in data.get("hookPerf", []):
            name = hp.get("hookName", "unknown")
            if not name or name == "unknown":
                continue
            points.append({
                "measurement": "jbpf_perf",
                "tags": {"hook": name},
                "time": iso_ts,
                "fields": {
                    "p50": safe_int(hp.get("p50", 0)),
                    "p90": safe_int(hp.get("p90", 0)),
                    "p95": safe_int(hp.get("p95", 0)),
                    "p99": safe_int(hp.get("p99", 0)),
                    "min_ns": safe_int(hp.get("min", 0)),
                    "max_ns": safe_int(hp.get("max", 0)),
                    "invocations": safe_int(hp.get("num", 0)),
                }
            })

    return points

# ── Tail file implementation ─────────────────────────────────────────────────
def tail_file(filepath, from_beginning=False):
    """Generator that yields new lines from a file, similar to tail -f.
    
    Args:
        filepath: Path to the file to tail.
        from_beginning: If True, read from the start of the file (useful with --drop
                        to capture events that fired before the ingestor started).
    """
    # If file doesn't exist yet, wait for it
    while running and not os.path.exists(filepath):
        print(f"[WAIT] Waiting for {filepath} to appear...")
        time.sleep(1)
    if not running:
        return

    with open(filepath, 'r', errors='replace') as f:
        if from_beginning:
            # Read from position 0 to capture all existing content first
            print(f"[INFO] Reading from beginning of {filepath}")
        else:
            # Seek to end for live mode (only new data)
            f.seek(0, 2)
        last_pos = f.tell()
        while running:
            # Detect file truncation (decoder restart / tee re-open)
            try:
                cur_size = os.path.getsize(filepath)
            except OSError:
                cur_size = last_pos
            if cur_size < last_pos:
                print(f"[INFO] File truncated ({last_pos} → {cur_size}), re-reading from start")
                f.seek(0)
                last_pos = 0

            line = f.readline()
            if line:
                last_pos = f.tell()
                yield line
            else:
                time.sleep(TAIL_POLL_INTERVAL)

def replay_file(filepath):
    """Generator that yields all lines from existing file."""
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            if not running:
                return
            yield line

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    global running

    parser = argparse.ArgumentParser(description="srsRAN Telemetry → InfluxDB Ingestor")
    parser.add_argument("--log", default=DEFAULT_LOG, help=f"Decoder log file to tail (default: {DEFAULT_LOG})")
    parser.add_argument("--replay", metavar="FILE", help="Replay an existing log file (ingest all records, then exit)")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"InfluxDB database name (default: {DEFAULT_DB})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"InfluxDB host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"InfluxDB port (default: {DEFAULT_PORT})")
    parser.add_argument("--drop", action="store_true", help="Drop and recreate the database before starting")
    parser.add_argument("--from-beginning", action="store_true", dest="from_beginning",
                        help="Read log from the beginning on startup (captures events before ingestor starts, e.g. NGAP/RRC attach)")
    args = parser.parse_args()

    # Connect to InfluxDB
    print(f"[INFO] Connecting to InfluxDB at {args.host}:{args.port}, database={args.db}")
    client = InfluxDBClient(host=args.host, port=args.port, database=args.db)

    # Create DB if not exists
    client.create_database(args.db)

    if args.drop:
        print(f"[WARN] Dropping database {args.db}...")
        client.drop_database(args.db)
        client.create_database(args.db)
        print(f"[INFO] Database {args.db} recreated")

    client.switch_database(args.db)

    # Set up retention policy (keep 30 days of data)
    try:
        client.create_retention_policy("telemetry_30d", "30d", 1, database=args.db, default=True)
    except Exception:
        pass  # Already exists

    # Determine mode
    if args.replay:
        filepath = args.replay
        mode = "replay"
        print(f"[INFO] Replay mode: ingesting {filepath}")
        line_gen = replay_file(filepath)
    else:
        filepath = args.log
        mode = "live"
        print(f"[INFO] Live mode: tailing {filepath}")
        print(f"[INFO] Press Ctrl+C to stop")
        # Read from beginning when --drop or --from-beginning: captures events
        # (NGAP, RRC attach, etc.) that fired before the ingestor started.
        line_gen = tail_file(filepath, from_beginning=(args.drop or args.from_beginning))

    # Process lines
    batch = []
    last_flush = time.time()

    for line in line_gen:
        result = parse_line(line)
        if result is None:
            stats["skipped"] += 1
            continue

        ts, schema, pkg, data = result
        stats["parsed"] += 1

        points = make_points(ts, schema, pkg, data)
        if points:
            batch.extend(points)

        # Flush batch
        now = time.time()
        if len(batch) >= BATCH_SIZE or (now - last_flush) >= FLUSH_INTERVAL:
            if batch:
                try:
                    client.write_points(batch, time_precision='s')
                    stats["written"] += len(batch)
                except Exception as e:
                    stats["errors"] += 1
                    print(f"[ERROR] InfluxDB write failed: {e}")
                batch = []
                last_flush = now

                # Status update every 100 records
                if stats["parsed"] % 100 == 0:
                    print(f"[STATUS] parsed={stats['parsed']} written={stats['written']} errors={stats['errors']} skipped={stats['skipped']}")

    # Final flush
    if batch:
        try:
            client.write_points(batch, time_precision='s')
            stats["written"] += len(batch)
        except Exception as e:
            stats["errors"] += 1
            print(f"[ERROR] Final flush failed: {e}")

    print(f"\n[DONE] {mode.upper()} complete:")
    print(f"  Parsed:  {stats['parsed']}")
    print(f"  Written: {stats['written']} points")
    print(f"  Errors:  {stats['errors']}")
    print(f"  Skipped: {stats['skipped']} (non-telemetry lines)")

    client.close()

if __name__ == "__main__":
    main()
