# srsRAN jbpf MAC Scheduler Telemetry — Project Summary & Launch Guide

## Project Context

You are working on a **5G NR telemetry collection system** built on top of:

- **srsRAN Project (jbpf fork)** — an open-source 5G gNB (base station) with eBPF/jbpf hooks in the MAC scheduler
- **jrt-controller** — a runtime controller that manages jbpf codelet lifecycle and data routing
- **jrtc-apps** — a repository of eBPF codelets that attach to MAC scheduler hooks and collect stats
- **srsUE** — a software UE (from srsRAN 4G) that connects to the gNB over a ZMQ virtual radio

The system runs entirely on one Linux machine using ZMQ (no real radio hardware).

---

## 1. What Was Done

### 1.1 Fixed All 10 eBPF Codelets (Verifier Failures)

All 10 MAC scheduler codelets had eBPF verifier failures that prevented loading. The fixes included:

- **Hash map relocation issues** — Map types in codelet `.o` files didn't match what the jbpf runtime expected. Fixed by correcting the map definitions and relocation entries.
- **`forward_destination` settings** — All output channels in `mac_stats.yaml` needed `forward_destination: DestinationUDP` to route telemetry data out via UDP to the decoder.
- **HARQ map type mismatches** — DL and UL HARQ codelets had incorrect map type definitions that needed correction.
- **Complex loop rejection** — `JBPF_HASHMAP_CLEAR` calls in flush codelets were rejected by the eBPF verifier for large maps. These were removed, making stats **cumulative** (never reset).

### 1.2 Fixed Two Bugs in `jrtc-ctl` (the Go CLI Tool)

**Bug 1: DL/UL HARQ Schema Registration Collision**

Both DL HARQ and UL HARQ codelets share the same protobuf schema (`mac_sched_harq_stats.proto`) with the same `msg_name: harq_stats`. The decoder's `LoadRequest.Streams` map was `map[string][]byte`, meaning the second HARQ stream (UL) would **overwrite** the first (DL) since they share the same key.

**Fix** (in `services/decoder/client.go`):
```go
// BEFORE:
Streams map[string][]byte

// AFTER:
Streams map[string][][]byte
```

And in the `Load()` function, nested loop over `streamIDs` slice for each proto message.

**Fix** (in `cmd/jbpf/load/load.go`):
```go
// BEFORE (assignment overwrites):
schemas[protoName].Streams[io.Serde.Protobuf.MessageName] = streamIDB

// AFTER (append preserves both):
schemas[protoName].Streams[io.Serde.Protobuf.MessageName] = append(
    schemas[protoName].Streams[io.Serde.Protobuf.MessageName], streamIDB,
)
```

**Bug 2: Context Cancellation Killing Phase 2**

The load command used a single `errgroup.WithContext()`. When the decoder (phase 1) goroutine finished and `g.Wait()` returned, the derived context was cancelled — which killed the jbpf load (phase 2) that was running concurrently.

**Fix** (in `cmd/jbpf/load/load.go`): Split into two sequential phases with separate errgroups:
```go
// Phase 1: Load schemas to decoder
g1, decoderCtx := errgroup.WithContext(cmd.Context())
g1.Go(func() error { /* decoder work */ })
if err := g1.Wait(); err != nil { return err }

// Phase 2: Load codelets via reverse proxy (fresh context)
g2, jbpfCtx := errgroup.WithContext(cmd.Context())
g2.Go(func() error { /* jbpf load work */ })
return g2.Wait()
```

### 1.3 Verified All 5 Telemetry Streams

After fixes, all 5 data streams flow correctly with zero "missing schema" errors:

| Stream | Proto Message | Description | Rate |
|--------|--------------|-------------|------|
| UCI | `uci_stats` | Uplink Control Information (CQI, RI, TA) | ~1 msg/sec |
| CRC | `crc_stats` | Uplink CRC decode results (success rate, SINR, RSRP) | ~1 msg/sec |
| BSR | `bsr_stats` | Buffer Status Reports (UE buffer sizes) | ~1 msg/sec |
| DL HARQ | `harq_stats` | Downlink HARQ (MCS, retransmissions, TBS) | ~1 msg/sec |
| UL HARQ | `harq_stats` | Uplink HARQ (MCS, retransmissions, TBS) | ~1 msg/sec |

**PHR (Power Headroom)**: The PHR codelet is loaded but produces 0 messages because srsUE's NR MAC layer does not implement PHR reporting. This is a known srsUE limitation, not a bug.

### 1.4 Key Design Notes

- **Stats are cumulative**: The flush codelets cannot clear the eBPF hash maps (verifier rejects the loop). So each telemetry message contains **running totals** since codelet load time. To get per-window values, consumers must diff consecutive messages.
- **Sentinel values**: When a stat has never been updated, `min` = `4294967295` (UINT32_MAX) and `max` = `0`. This indicates "no data collected yet."
- **duUeIndex 513**: A harmless ghost entry that appears in DL HARQ data. It's a one-time scheduler init event for internal UE index 0x201 that persists in the hash map because the map is never cleared. It has count=1, MCS=0, tbsBytes=0 and never grows. Filter it out by ignoring entries where `duUeIndex >= 32` or all stat counts are zero.

---

## 2. System Architecture

```
┌─────────┐    ZMQ     ┌──────────────────────────────┐
│  srsUE  │◄──────────►│  srsRAN gNB (jbpf-enabled)   │
│         │            │                              │
└─────────┘            │  MAC Scheduler Hooks:        │
                       │  ├─ mac_sched_crc_indication  │
                       │  ├─ mac_sched_ul_bsr_indication│
                       │  ├─ mac_sched_ul_phr_indication│
                       │  ├─ mac_sched_uci_indication  │
                       │  ├─ mac_sched_harq_dl         │
                       │  ├─ mac_sched_harq_ul         │
                       │  ├─ mac_sched_ue_deletion     │
                       │  └─ report_stats (periodic)   │
                       │                              │
                       │  jbpf IPC ──► /tmp/jbpf/     │
                       └──────────┬───────────────────┘
                                  │ IPC socket
                       ┌──────────┴───────────────────┐
                       │  srsran_reverse_proxy        │
                       │  (IPC ↔ TCP on port 30450)   │
                       └──────────┬───────────────────┘
                                  │ TCP
                       ┌──────────┴───────────────────┐
                       │  jrtc (jrt-controller)       │
                       │  Routes data streams         │
                       └──────────┬───────────────────┘
                                  │ UDP port 20788
                       ┌──────────┴───────────────────┐
                       │  jrtc-ctl decoder            │
                       │  (gRPC on TCP 20789 for      │
                       │   schema registration,       │
                       │   UDP 20788 for data)        │
                       │                              │
                       │  Output: decoded protobuf    │
                       │  JSON to stdout/log          │
                       └──────────────────────────────┘
```

The **10 eBPF codelets** are organized as:

1. **Event codelets** (6): Attach to MAC scheduler hooks, write stats into shared hash maps
   - `mac_sched_crc_stats` → CRC events
   - `mac_sched_bsr_stats` → BSR events
   - `mac_sched_phr_stats` → PHR events
   - `mac_sched_uci_pdu_stats` → UCI events
   - `mac_sched_dl_harq_stats` → DL HARQ events
   - `mac_sched_ul_harq_stats` → UL HARQ events

2. **Flush codelets** (3): Attach to `report_stats` (periodic timer), read shared maps and output via ring buffer
   - `mac_stats_collect` → flushes CRC, BSR, PHR, UCI
   - `mac_stats_collect_dl_harq` → flushes DL HARQ
   - `mac_stats_collect_ul_harq` → flushes UL HARQ

3. **Cleanup codelet** (1): Handles UE deletion events
   - `mac_sched_ue_deletion` → clears per-UE entries from all hash maps

---

## 3. Directory Layout

```
~/Desktop/
├── srsRAN_Project_jbpf/           # gNB source + build
│   ├── build/apps/gnb/gnb         # gNB binary
│   ├── configs/gnb_zmq_jbpf.yml   # gNB config (ZMQ + jbpf)
│   └── out/bin/
│       └── srsran_reverse_proxy   # IPC-to-TCP proxy binary
│
├── jrt-controller/                # jrt-controller source + build
│   └── out/bin/
│       ├── jrtc                   # jrt-controller daemon
│       └── jrtc-ctl               # CLI tool (with our bug fixes)
│
├── jrtc-apps/                     # Codelet source + compiled objects
│   ├── set_vars.sh                # Environment setup script
│   ├── .env                       # Base env (SRS_JBPF_DOCKER=1, USE_JRTC=1)
│   ├── .env.local                 # Local overrides (SRS_JBPF_DOCKER=0, paths)
│   └── codelets/mac/
│       ├── mac_stats.yaml         # Codelet set descriptor (all 10 codelets)
│       ├── *.o                    # Compiled eBPF codelet objects
│       ├── *.proto                # Protobuf schema source files
│       ├── *.pb                   # Compiled protobuf descriptors
│       └── *_serializer.so        # Serde shared libraries
│
├── srsRAN_4G/                     # srsUE source (v22.10)
├── ue_zmq.conf                    # UE config file
└── JBPF_MAC_TELEMETRY_PROMPT.md   # This file
```

---

## 4. Step-by-Step Launch Instructions

**Prerequisites**: All components are already built. The sudo password is `2003`.

You need **5 terminal windows**. Run each step in order, waiting for the previous one to succeed before moving on.

### Terminal 1: jrt-controller

```bash
# Clean stale IPC sockets from any previous run
rm -f /tmp/jbpf/* 2>/dev/null

# Start jrt-controller
source ~/Desktop/jrtc-apps/set_vars.sh
~/Desktop/jrt-controller/out/bin/jrtc 2>/tmp/jrtc.log &

# Verify it's running
sleep 3 && pgrep -af "jrtc$" && echo "jrtc OK"
```

### Terminal 2: gNB (5G Base Station)

```bash
source ~/Desktop/jrtc-apps/set_vars.sh
echo "2003" | sudo -S -E ~/Desktop/srsRAN_Project_jbpf/build/apps/gnb/gnb \
  -c ~/Desktop/srsRAN_Project_jbpf/configs/gnb_zmq_jbpf.yml \
  2>/tmp/gnb_stderr.log &

# Wait for gNB to start and create the IPC socket
sleep 10

# CRITICAL: Fix IPC socket permissions so the reverse proxy can connect
echo "2003" | sudo -S chmod 777 /tmp/jbpf/jbpf_lcm_ipc

# Verify gNB is running
tail -5 /tmp/gnb_stderr.log
# Should show "==== gNB started ===" and "N2: Connection to AMF ... completed"
```

### Terminal 3: Reverse Proxy

```bash
source ~/Desktop/jrtc-apps/set_vars.sh
~/Desktop/srsRAN_Project_jbpf/out/bin/srsran_reverse_proxy \
  --host-port 30450 \
  --address "/tmp/jbpf/jbpf_lcm_ipc" \
  2>&1 | tee /tmp/reverse_proxy.log
```

This bridges the gNB's IPC socket to TCP port 30450 so `jrtc-ctl` can talk to it.

### Terminal 4: Decoder

```bash
source ~/Desktop/jrtc-apps/set_vars.sh
export PATH=$PATH:~/Desktop/jrt-controller/out/bin

jrtc-ctl decoder run --decoder-data-enabled 2>&1 | tee /tmp/decoder.log
```

This starts the decoder which:
- Listens on **TCP 20789** for gRPC schema registration requests
- Listens on **UDP 20788** for incoming telemetry data
- Decodes protobuf messages and prints them as JSON to stdout

### Terminal 5: Load Codelets, Start UE, Generate Traffic

```bash
# Set up environment
source ~/Desktop/jrtc-apps/set_vars.sh
export PATH=$PATH:~/Desktop/jrt-controller/out/bin

# Load all 10 MAC codelets + register schemas with decoder
jrtc-ctl jbpf load \
  --config ${JBPF_CODELETS}/mac/mac_stats.yaml \
  --device-id 1 \
  --decoder-enable \
  --decoder-port 20789 \
  --jbpf-port 30450 \
  2>&1
echo "Load Exit: $?"
# Should print "Load Exit: 0"

# Start the UE (creates network namespace ue1)
echo "2003" | sudo -S ip netns add ue1 2>/dev/null
echo "2003" | sudo -S /usr/local/bin/srsue ~/Desktop/ue_zmq.conf 2>&1 | tee /tmp/ue.log &

# Wait for UE to attach (watch for "RRC Connected" and "PDU Session" in output)
sleep 20

# Verify UE got an IP address
echo "2003" | sudo -S ip netns exec ue1 ip addr show tun_srsue 2>/dev/null | head -3
# Should show an IP like 10.45.0.x

# Generate traffic (ping at 10 pps for 30 seconds)
echo "2003" | sudo -S ip netns exec ue1 ping 10.45.0.1 -i 0.1 -c 300 &
```

### Viewing Telemetry

After codelets are loaded and traffic is flowing, **Terminal 4** (decoder) will show decoded JSON messages. You can also check:

```bash
# Count messages per stream type
grep -o '"_schema_proto_msg":"[^"]*"' /tmp/decoder.log | sort | uniq -c | sort -rn

# Check for errors
grep -c "missing schema" /tmp/decoder.log

# View latest messages
tail -20 /tmp/decoder.log
```

### Unloading Codelets

```bash
source ~/Desktop/jrtc-apps/set_vars.sh
export PATH=$PATH:~/Desktop/jrt-controller/out/bin

jrtc-ctl jbpf unload \
  --config ${JBPF_CODELETS}/mac/mac_stats.yaml \
  --device-id 1 \
  --jbpf-port 30450 \
  2>&1
echo "Unload Exit: $?"
```

### Shutting Down (Reverse Order)

```bash
# Kill UE
echo "2003" | sudo -S pkill -9 srsue

# Kill decoder (Ctrl+C in Terminal 4, or)
pkill -f "decoder run"

# Kill reverse proxy (Ctrl+C in Terminal 3, or)
pkill -9 srsran_reverse

# Kill gNB
echo "2003" | sudo -S pkill -9 gnb

# Kill jrt-controller
pkill -9 jrtc

# Clean up IPC sockets
rm -f /tmp/jbpf/*
```

---

## 5. Telemetry Data Format

All messages are JSON with metadata fields:
- `_schema_proto_msg`: Message type (e.g., `"uci_stats"`)
- `_schema_proto_package`: Proto package name
- `_stream_id`: UUID identifying the stream source
- `timestamp`: gNB nanosecond timestamp
- `stats`: Array of per-UE stat objects

### 5.1 UCI Stats (`uci_stats`)

```json
{
  "duUeIndex": 0,
  "srDetected": 0,
  "csi": {
    "cqi": { "count": 49, "min": 15, "max": 15, "total": 735 },
    "ri":  { "count": 49, "min": 1,  "max": 1,  "total": 49  }
  },
  "timeAdvanceOffset": { "count": 49, "min": "1026", "max": "1026", "total": "50274" }
}
```

- **CQI** (Channel Quality Indicator): 0–15 scale, 15 = best. Average = total/count.
- **RI** (Rank Indicator): Number of spatial layers (1 = single antenna).
- **Time Advance Offset**: Propagation delay in samples.
- **srDetected**: Whether the UE sent a Scheduling Request.

### 5.2 CRC Stats (`crc_stats`)

```json
{
  "duUeIndex": 0,
  "succTx": 36, "cntTx": 36,
  "harqFailure": 0, "consMax": 0,
  "retxHist": [36, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  "cntSinr": 36, "minSinr": 42, "maxSinr": 42, "sumSinr": 1512,
  "cntRsrp": 36, "minRsrp": -1, "maxRsrp": 0, "sumRsrp": 0
}
```

- **succTx / cntTx**: Successful decodes / total transmissions. Success rate = succTx/cntTx.
- **retxHist[16]**: Histogram — retxHist[i] = number of transmissions that succeeded after i retransmissions. retxHist[0] = first-attempt success.
- **SINR**: Signal-to-Interference-plus-Noise Ratio in dB. Average = sumSinr/cntSinr.
- **RSRP**: Reference Signal Received Power in dB.
- **harqFailure / consMax**: Total HARQ failures / max consecutive failures.

### 5.3 BSR Stats (`bsr_stats`)

```json
{
  "duUeIndex": 0,
  "cnt": 36,
  "bytes": "1008"
}
```

- **cnt**: Number of BSR reports received.
- **bytes**: Total buffer size reported by the UE across all BSRs.

### 5.4 HARQ Stats (`harq_stats`) — Used by Both DL and UL

```json
{
  "duUeIndex": 0, "cellId": 0, "rnti": 0,
  "mcsTable": 0, "maxNofHarqRetxs": 4,
  "mcs":      { "count": 342, "min": 21, "max": 28, "total": "9234" },
  "consRetx": { "count": 342, "min": 0,  "max": 0,  "total": "0"    },
  "perHarqTypeStats": [
    {
      "count": 342,
      "tbsBytes": { "count": 342, "total": "167832" },
      "cqi":      { "count": 342, "min": 15, "max": 15, "total": "5130" }
    },
    { "count": 0, "tbsBytes": { "count": 0, "total": "0" }, "cqi": { "count": 0, "min": 4294967295, "max": 0, "total": "0" } },
    { "count": 0, "tbsBytes": { "count": 0, "total": "0" }, "cqi": { "count": 0, "min": 4294967295, "max": 0, "total": "0" } }
  ]
}
```

- **mcs**: Modulation & Coding Scheme index. Higher = faster. Average = total/count.
- **consRetx**: Consecutive retransmissions per HARQ event.
- **perHarqTypeStats[0]**: NEW_TX (first transmission) — count, total TBS bytes, CQI at time of TX.
- **perHarqTypeStats[1]**: RETX (retransmission).
- **perHarqTypeStats[2]**: FAILURE (max retries exhausted).
- **Sentinel values**: `min: 4294967295` (UINT32_MAX) and `max: 0` mean "no data collected."
- **Two streams share this schema**: DL HARQ and UL HARQ have different `_stream_id` values.

### 5.5 PHR Stats (`phr_stats`) — NOT ACTIVE

PHR (Power Headroom Report) telemetry is loaded but produces 0 messages because srsUE does not implement NR MAC PHR. This is expected and not a bug.

---

## 6. Rebuilding jrtc-ctl (If Code Changes Are Made)

If you modify Go source files in `~/Desktop/jrt-controller/tools/jrtc-ctl/`:

```bash
cd ~/Desktop/jrt-controller/tools/jrtc-ctl
CGO_CFLAGS="-I/home/maxim/Desktop/jrt-controller/out/inc" \
CGO_LDFLAGS="-L/home/maxim/Desktop/jrt-controller/out/lib -ljrtc_router_stream_id_static" \
go build --trimpath -o /home/maxim/Desktop/jrt-controller/out/bin/jrtc-ctl main.go
echo "Build exit: $?"
```

---

## 7. Modified Files Summary

| File | What Changed |
|------|-------------|
| `jrt-controller/tools/jrtc-ctl/services/decoder/client.go` | `LoadRequest.Streams`: `map[string][]byte` → `map[string][][]byte`; `Load()` function: nested loop over stream ID slices |
| `jrt-controller/tools/jrtc-ctl/cmd/jbpf/load/load.go` | Split single errgroup into g1 (decoder) + g2 (jbpf) for proper context management; Changed stream ID assignment to `append()` |
| `jrtc-apps/codelets/mac/mac_stats.yaml` | All `forward_destination` fields set to `DestinationUDP` |
| Various `codelets/mac/*.cpp` files | eBPF verifier fixes (map types, relocations, removed HASHMAP_CLEAR) |

---

## 8. Troubleshooting

| Problem | Solution |
|---------|----------|
| `Load Exit: 1` or codelet load fails | Check reverse proxy is running (`pgrep -f srsran_reverse`), check IPC socket permissions (`ls -la /tmp/jbpf/jbpf_lcm_ipc`), restart with `chmod 777` |
| "missing schema" in decoder log | Codelets were loaded without `--decoder-enable --decoder-port 20789`. Unload and reload with those flags. |
| No telemetry data in decoder | Check gNB is running, UE is attached, traffic is flowing. Check `tail /tmp/gnb_stderr.log` for errors. |
| Decoder shows only hex blobs | Schema registration failed. Check decoder is listening on TCP 20789 (`ss -tlnp \| grep 20789`). |
| HARQ data all zeros / sentinel values | No active traffic. Start pinging: `sudo ip netns exec ue1 ping 10.45.0.1 -i 0.1` |
| gNB won't start | Clean stale sockets: `rm -f /tmp/jbpf/*`, kill old processes, try again |
| UE won't attach | Make sure gNB shows "gNB started" and AMF connection is up. Check `tail /tmp/ue.log`. |
| `duUeIndex: 513` in HARQ data | Harmless ghost entry. See Section 1.4. Filter out entries where `duUeIndex >= 32`. |
