# Custom SINR Codelet: Variance and Sliding Window Average

## Overview

This document describes a **custom jBPF codelet** built on top of the existing
`mac_sched_crc_stats` codelet.  The custom codelet adds two analytical
operations that run **inside the gNB process** (in-line, at the MAC layer):

| Operation | Description |
|-----------|-------------|
| **SINR Variance** | Online computation of $\text{Var}(X) = E[X^2] - (E[X])^2$ over the current reporting window (~1 s) |
| **Sliding Window Average** | Ring-buffer average of the last 16 SINR samples, persisting across reporting windows |

Both computations execute on every `mac_sched_crc_indication` hook invocation —
the same hook that fires once per UL CRC PDU — so there is **zero additional
hook overhead**.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  srsRAN gNB  (mac_sched_crc_indication hook)                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  mac_sched_crc_stats_custom.o  (hook codelet)            │    │
│  │                                                          │    │
│  │  On each UL CRC PDU:                                     │    │
│  │   1. Extract SINR from ul_crc_pdu_indication             │    │
│  │   2. Update min / max / sum / count   (basic stats)      │    │
│  │   3. Accumulate sum_sq_sinr           (for variance)     │    │
│  │   4. Update ring buffer[16]           (sliding window)   │    │
│  │   5. Compute variance = E[X²] − E[X]²                   │    │
│  │   6. Compute sliding_avg = window_sum / window_count     │    │
│  │                                                          │    │
│  │        ┌────────────────────┐  ┌─────────────────────┐   │    │
│  │        │ stats_map_crc_custom│  │  sinr_window_map    │   │    │
│  │        │ (cleared each ~1s) │  │  (persists always)  │   │    │
│  │        └────────┬───────────┘  └─────────────────────┘   │    │
│  └─────────────────┼────────────────────────────────────────┘    │
│                    │ shared via linked_maps                       │
│  ┌─────────────────▼────────────────────────────────────────┐    │
│  │  mac_stats_collect_custom.o  (collector codelet)          │    │
│  │                                                          │    │
│  │  Runs on report_stats hook (~1 s tick):                   │    │
│  │   • Reads stats_map_crc_custom                            │    │
│  │   • Sets timestamp                                        │    │
│  │   • Sends via ringbuf → protobuf serializer → UDP         │    │
│  │   • Clears stats_map (but NOT sinr_window_map)            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                    │                                             │
└────────────────────┼─────────────────────────────────────────────┘
                     │ UDP / protobuf
                     ▼
            InfluxDB / Grafana
```

---

## What Changed vs the Original Codelet

### Base codelet: `mac_sched_crc_stats.cpp`

The original codelet tracks per-UE, per-window:
- `min_sinr`, `max_sinr`, `sum_sinr`, `cnt_sinr`
- `min_rsrp`, `max_rsrp`, `sum_rsrp`, `cnt_rsrp`
- CRC success/failure counts, retransmission histogram, HARQ failure count

### Custom codelet: `mac_sched_crc_stats_custom.cpp`

Streamlined to focus on SINR analytics.  Added fields:

| New field | Type | Purpose |
|-----------|------|---------|
| `sum_sq_sinr` | `int32` | $\sum x_i^2$ for variance calculation |
| `sinr_variance` | `int32` | $E[X^2] - (E[X])^2$, computed on each sample |
| `sinr_sliding_avg` | `int32` | Average of last 16 SINR readings |
| `sinr_sliding_cnt` | `uint32` | Number of samples in the sliding window (up to 16) |

Removed fields (to keep the codelet focused):
- RSRP statistics (not needed for this analysis)
- Retransmission histogram (kept in the original codelet)
- HARQ failure counter (kept in the original codelet)

---

## Implementation Details

### 1. Variance: Welford-style Online Computation

Computing variance in a single pass without storing all samples:

$$\text{Var}(X) = \frac{\sum x_i^2}{n} - \left(\frac{\sum x_i}{n}\right)^2$$

On each SINR sample the codelet updates:
```
sum_sinr     += sinr_dB
sum_sq_sinr  += sinr_dB * sinr_dB
cnt_sinr++
```

Then computes:
```
mean     = signed_div(sum_sinr, cnt_sinr)
variance = (sum_sq_sinr / cnt_sinr) - mean²
```

**BPF constraint**: The eBPF instruction set does **not** support signed
integer division.  We use a `signed_div()` helper that tracks the sign
separately and performs unsigned division:

```cpp
static __attribute__((always_inline))
int32_t signed_div(int32_t num, uint32_t den)
{
    if (den == 0) return 0;
    if (num >= 0)
        return (int32_t)((uint32_t)num / den);
    else
        return -(int32_t)((uint32_t)(-num) / den);
}
```

### 2. Sliding Window Average (Ring Buffer)

A 16-entry ring buffer stores the most recent SINR samples.  The window
persists across reporting windows (its BPF map is never cleared by the
collector).

```
┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
│ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │ 8 │ 9 │10 │11 │12 │13 │14 │15 │
└───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘
      ▲ write_idx (wraps around)

window_sum tracks the running sum — no loop needed for average.
```

On each new SINR sample:
1. If window full (count ≥ 16): subtract oldest sample from `window_sum`
2. Write new sample at `write_idx & 0xF`
3. Add new sample to `window_sum`
4. `sliding_avg = signed_div(window_sum, min(count, 16))`

**BPF constraint**: Variable-indexed array access inside map values can fail
the BPF verifier.  The codelet uses `switch/case` with 16 explicit cases for
both read and write operations, following the same pattern used by the original
`retx_hist` update logic.

### 3. Collector Simplicity

The collector (`mac_stats_collect_custom.cpp`) is intentionally minimal:
- Reads the shared `stats_map_crc_custom`
- Sets the timestamp
- Sends via ring buffer output
- Clears the stats map (but **not** `sinr_window_map`)

All mathematical computations happen in the hook codelet, keeping the
collector under 203 BPF instructions.

---

## File Inventory

All files are in `/codelets/mac/` within the `jrtc-apps` repository:

| File | Purpose |
|------|---------|
| `mac_sched_crc_stats_custom.cpp` | Hook codelet — SINR extraction + variance + sliding window |
| `mac_stats_collect_custom.cpp` | Collector codelet — periodic output via protobuf/UDP |
| `mac_sched_crc_stats_custom.proto` | Protobuf schema for the custom output message |
| `mac_sched_crc_stats_custom.options` | nanopb options (max 32 UE entries) |
| `mac_stats_custom.yaml` | Deployment descriptor for `jrtc-ctl` |

Build artifacts (generated):

| File | Purpose |
|------|---------|
| `mac_sched_crc_stats_custom.o` | Compiled hook codelet (698 BPF instructions) |
| `mac_stats_collect_custom.o` | Compiled collector codelet (203 BPF instructions) |
| `mac_sched_crc_stats_custom.pb.h` | nanopb-generated C header |
| `mac_sched_crc_stats_custom.pb` | Compiled protobuf descriptor |
| `mac_sched_crc_stats_custom:crc_stats_custom_serializer.so` | Protobuf serializer shared library |

---

## Protobuf Schema

```protobuf
message t_crc_stats_custom {
   required uint32 du_ue_index     = 1;   // UE identifier
   required uint32 succ_tx         = 2;   // successful CRC count
   required uint32 cnt_tx          = 3;   // total CRC count
   required int32  min_sinr        = 4;   // minimum SINR (dB, integer)
   required int32  max_sinr        = 5;   // maximum SINR (dB, integer)
   required int32  sum_sinr        = 6;   // sum of SINR samples
   required uint32 cnt_sinr        = 7;   // SINR sample count
   required int32  sum_sq_sinr     = 8;   // sum of squared SINR (for variance)
   required int32  sinr_variance   = 9;   // computed variance = E[X²] − E[X]²
   required int32  sinr_sliding_avg = 10; // sliding window average (last 16)
   required uint32 sinr_sliding_cnt = 11; // samples in sliding window (≤ 16)
}

message crc_stats_custom {
   required uint64 timestamp = 1;         // nanosecond timestamp
   repeated t_crc_stats_custom stats = 2; // per-UE stats (max 32)
}
```

---

## Build Instructions

```bash
# Source environment
cd /path/to/jrtc-apps
source set_vars.sh

# Build proto + serializer + codelets
cd codelets/mac
make mac_sched_crc_stats_custom^crc_stats_custom   # proto + serializer
make mac_sched_crc_stats_custom.o                    # hook codelet
make mac_stats_collect_custom.o                      # collector codelet
```

Both codelets pass the srsRAN BPF verifier:
- Hook codelet: **698 instructions** (well under the 1M limit)
- Collector: **203 instructions**

---

## Deployment

Load the custom codelet set alongside (or instead of) the standard `mac_stats`:

```bash
# Load custom SINR analytics
jrtc-ctl --load mac_stats_custom.yaml

# Or, to run alongside the original:
jrtc-ctl --load mac_stats.yaml
jrtc-ctl --load mac_stats_custom.yaml
```

Both codelet sets hook `mac_sched_crc_indication` independently.  The custom
set outputs to its own UDP channel with its own protobuf schema.

---

## Output Fields Explained

When received by the telemetry pipeline, each ~1 s report contains:

| Field | Meaning | Example |
|-------|---------|---------|
| `min_sinr` | Lowest SINR in this window | 26 dB |
| `max_sinr` | Highest SINR in this window | 30 dB |
| `sum_sinr / cnt_sinr` | Mean SINR for this window | 28.3 dB |
| `sinr_variance` | Spread of SINR values ($\text{dB}^2$) | 2 |
| `sinr_sliding_avg` | Smoothed SINR (last 16 CRC events) | 28 dB |
| `sinr_sliding_cnt` | Window fill level (max 16) | 16 |
| `succ_tx / cnt_tx` | CRC success rate | 0.97 |

### Interpreting Variance

- **Variance ≈ 0**: SINR is very stable (typical for a static ZMQ test setup)
- **Variance > 5**: Noticeable fluctuation (channel variation or interference)
- **Variance > 20**: Significant instability (fading, mobility, or interference)

### Interpreting Sliding Average

The sliding average smooths over the last 16 CRC events (not time-based).
At typical traffic rates this spans roughly 16 ms to a few hundred ms, providing
a short-term trend indicator that is less noisy than the raw per-event SINR but
more responsive than the 1-second window mean.
