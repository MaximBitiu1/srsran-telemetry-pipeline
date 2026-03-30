#!/usr/bin/env python3
"""
UE Traffic Ingestor — tails iperf3 UL/DL and ping logs, writes to InfluxDB.

Measurements written:
  ue_ul_throughput  — bitrate_mbps, bytes, datagrams
  ue_dl_throughput  — bitrate_mbps, bytes, jitter_ms, lost_pkts, total_pkts, loss_pct
  ue_rtt            — rtt_ms, seq

Usage:
  python3 ue_traffic_ingestor.py [--ul FILE] [--dl FILE] [--ping FILE]
                                  [--host HOST] [--port PORT] [--db DB]
"""

import argparse
import re
import time
import threading
from datetime import datetime, timezone
from influxdb import InfluxDBClient

# ── Regexes ──────────────────────────────────────────────────────────────────
# [ 5] 387.00-388.00 sec  1.19 MBytes  10.0 Mbits/sec  893
RE_IPERF_UL = re.compile(
    r'\[\s*\d+\]\s+[\d.]+-(?P<t_end>[\d.]+)\s+sec'
    r'\s+(?P<bytes>[\d.]+)\s+(?P<bytes_unit>\S+)'
    r'\s+(?P<bitrate>[\d.]+)\s+(?P<bitrate_unit>\S+)'
    r'\s+(?P<datagrams>\d+)'
)
# [ 5] 362.00-363.00 sec  0.00 Bytes  0.00 bits/sec  77.833 ms  0/0 (0%)
RE_IPERF_DL = re.compile(
    r'\[\s*\d+\]\s+[\d.]+-(?P<t_end>[\d.]+)\s+sec'
    r'\s+(?P<bytes>[\d.]+)\s+(?P<bytes_unit>\S+)'
    r'\s+(?P<bitrate>[\d.]+)\s+(?P<bitrate_unit>\S+)'
    r'\s+(?P<jitter>[\d.]+)\s+ms'
    r'\s+(?P<lost>\d+)/(?P<total>\d+)'
    r'\s+\((?P<loss_pct>[\d.]+)%\)'
)
# 64 bytes from 10.45.0.1: icmp_seq=5 ttl=64 time=18660 ms
RE_PING = re.compile(
    r'icmp_seq=(?P<seq>\d+).*time=(?P<rtt>[\d.]+)\s+ms'
)


def to_mbits(value, unit):
    """Normalise iperf3 bitrate to Mbits/sec."""
    v = float(value)
    unit = unit.lower()
    if 'kbits' in unit:
        return v / 1000.0
    if 'gbits' in unit:
        return v * 1000.0
    return v  # already Mbits/sec


def to_bytes(value, unit):
    """Normalise iperf3 transfer to bytes."""
    v = float(value)
    unit = unit.lower()
    if 'kbyte' in unit:
        return v * 1024
    if 'mbyte' in unit:
        return v * 1024 * 1024
    if 'gbyte' in unit:
        return v * 1024 * 1024 * 1024
    return v


def now_ns():
    return int(datetime.now(timezone.utc).timestamp() * 1e9)


def tail_file(path, callback, stop_event, poll=0.5):
    """Tail a file, calling callback(line) for each new line."""
    while not stop_event.is_set():
        try:
            with open(path, 'r') as f:
                f.seek(0, 2)  # seek to end
                while not stop_event.is_set():
                    line = f.readline()
                    if line:
                        callback(line.rstrip())
                    else:
                        time.sleep(poll)
        except FileNotFoundError:
            time.sleep(2)
        except Exception as e:
            print(f'[WARN] tail {path}: {e}')
            time.sleep(2)


class TrafficIngestor:
    def __init__(self, host, port, db):
        self.client = InfluxDBClient(host=host, port=port, database=db)
        self.lock = threading.Lock()
        self.written = 0
        self.errors = 0

    def write(self, measurement, fields, ts_ns=None):
        if ts_ns is None:
            ts_ns = now_ns()
        point = {
            'measurement': measurement,
            'time': ts_ns,
            'fields': fields,
        }
        try:
            self.client.write_points([point], time_precision='n')
            with self.lock:
                self.written += 1
        except Exception as e:
            with self.lock:
                self.errors += 1
            print(f'[ERROR] write {measurement}: {e}')

    def handle_ul(self, line):
        m = RE_IPERF_UL.search(line)
        if not m:
            return
        bitrate = to_mbits(m.group('bitrate'), m.group('bitrate_unit'))
        self.write('ue_ul_throughput', {
            'bitrate_mbps': bitrate,
            'bytes':        to_bytes(m.group('bytes'), m.group('bytes_unit')),
            'datagrams':    int(m.group('datagrams')),
        })

    def handle_dl(self, line):
        m = RE_IPERF_DL.search(line)
        if not m:
            return
        bitrate = to_mbits(m.group('bitrate'), m.group('bitrate_unit'))
        total = int(m.group('total'))
        self.write('ue_dl_throughput', {
            'bitrate_mbps': bitrate,
            'bytes':        to_bytes(m.group('bytes'), m.group('bytes_unit')),
            'jitter_ms':    float(m.group('jitter')),
            'lost_pkts':    int(m.group('lost')),
            'total_pkts':   total,
            'loss_pct':     float(m.group('loss_pct')),
        })

    def handle_ping(self, line):
        m = RE_PING.search(line)
        if not m:
            return
        self.write('ue_rtt', {
            'rtt_ms': float(m.group('rtt')),
            'seq':    int(m.group('seq')),
        })

    def status(self):
        with self.lock:
            return self.written, self.errors


def main():
    parser = argparse.ArgumentParser(description='UE Traffic → InfluxDB')
    parser.add_argument('--ul',   default='/tmp/iperf3.log',    help='iperf3 UL log')
    parser.add_argument('--dl',   default='/tmp/iperf3_dl.log', help='iperf3 DL log')
    parser.add_argument('--ping', default='/tmp/ping_ue.log',   help='ping RTT log')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', default=8086, type=int)
    parser.add_argument('--db',   default='srsran_telemetry')
    args = parser.parse_args()

    ingestor = TrafficIngestor(args.host, args.port, args.db)
    stop = threading.Event()

    threads = [
        threading.Thread(target=tail_file, args=(args.ul,   ingestor.handle_ul,   stop), daemon=True),
        threading.Thread(target=tail_file, args=(args.dl,   ingestor.handle_dl,   stop), daemon=True),
        threading.Thread(target=tail_file, args=(args.ping, ingestor.handle_ping, stop), daemon=True),
    ]

    print(f'[INFO] Tailing UL={args.ul}  DL={args.dl}  ping={args.ping}')
    print(f'[INFO] Writing to InfluxDB {args.host}:{args.port}/{args.db}')

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(10)
            w, e = ingestor.status()
            print(f'[STATUS] written={w} errors={e}')
    except KeyboardInterrupt:
        stop.set()
        print(f'\n[DONE] written={ingestor.status()[0]} errors={ingestor.status()[1]}')


if __name__ == '__main__':
    main()
