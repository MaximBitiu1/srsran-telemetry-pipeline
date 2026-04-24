// BSR custom codelet — sliding window average on buffer bytes.
// Accumulates BSR byte reports; computes a 16-sample sliding window average (in KB).
// Based on mac_sched_bsr_stats.cpp + mac_sched_crc_stats_custom.cpp

#include <linux/bpf.h>

#include "jbpf_srsran_contexts.h"
#include "srsran/scheduler/scheduler_feedback_handler.h"

#include "mac_helpers.h"
#include "mac_sched_bsr_stats_custom.pb.h"

#include "../utils/misc_utils.h"
#include "../utils/hashmap_utils.h"

#include "jbpf_defs.h"
#include "jbpf_helper.h"
#include "jbpf_helper_utils.h"


// ── Sliding-window ring buffer (16 BSR events, stored in KB) ─────────────────

#define BSR_WINDOW_SIZE 16   // must be power of 2

struct bsr_window_entry {
    int32_t  samples[BSR_WINDOW_SIZE];
    uint32_t write_idx;
    uint32_t count;
    int32_t  window_sum;  // sum of samples currently in window (KB)
};

struct bsr_window_data {
    bsr_window_entry entries[MAX_NUM_UE];
};

struct jbpf_load_map_def SEC("maps") bsr_window_map = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(bsr_window_data),
    .max_entries = 1,
};


// ── Shared maps (linked with collector via mac_bsr_custom.yaml) ──────────────

struct jbpf_load_map_def SEC("maps") bsr_custom_not_empty = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(uint32_t),
    .max_entries = 1,
};

struct jbpf_load_map_def SEC("maps") stats_map_bsr_custom = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(bsr_stats_custom),
    .max_entries = 1,
};

DEFINE_PROTOHASH_32(bsr_custom_hash, MAX_NUM_UE);


// ── Ring buffer helpers (switch/case avoids dynamic index for verifier) ───────

static __attribute__((always_inline))
int32_t window_read(bsr_window_entry *w, uint32_t idx)
{
    switch (idx & (BSR_WINDOW_SIZE - 1)) {
        case 0:  return w->samples[0];   case 1:  return w->samples[1];
        case 2:  return w->samples[2];   case 3:  return w->samples[3];
        case 4:  return w->samples[4];   case 5:  return w->samples[5];
        case 6:  return w->samples[6];   case 7:  return w->samples[7];
        case 8:  return w->samples[8];   case 9:  return w->samples[9];
        case 10: return w->samples[10];  case 11: return w->samples[11];
        case 12: return w->samples[12];  case 13: return w->samples[13];
        case 14: return w->samples[14];  default: return w->samples[15];
    }
}

static __attribute__((always_inline))
void window_write(bsr_window_entry *w, uint32_t idx, int32_t val)
{
    switch (idx & (BSR_WINDOW_SIZE - 1)) {
        case 0:  w->samples[0]  = val; break;  case 1:  w->samples[1]  = val; break;
        case 2:  w->samples[2]  = val; break;  case 3:  w->samples[3]  = val; break;
        case 4:  w->samples[4]  = val; break;  case 5:  w->samples[5]  = val; break;
        case 6:  w->samples[6]  = val; break;  case 7:  w->samples[7]  = val; break;
        case 8:  w->samples[8]  = val; break;  case 9:  w->samples[9]  = val; break;
        case 10: w->samples[10] = val; break;  case 11: w->samples[11] = val; break;
        case 12: w->samples[12] = val; break;  case 13: w->samples[13] = val; break;
        case 14: w->samples[14] = val; break;  default: w->samples[15] = val; break;
    }
}

static __attribute__((always_inline))
int32_t signed_div(int32_t num, uint32_t den)
{
    if (den == 0) return 0;
    return (num >= 0) ? (int32_t)((uint32_t)num / den)
                      : -(int32_t)((uint32_t)(-num) / den);
}


// ── Main entry point ──────────────────────────────────────────────────────────

extern "C" SEC("jbpf_ran_mac_sched")
uint64_t jbpf_main(void* state)
{
    int zero_index = 0;
    struct jbpf_mac_sched_ctx *ctx = (jbpf_mac_sched_ctx *)state;

    const srsran::ul_bsr_indication_message& mac_ctx =
        *reinterpret_cast<const srsran::ul_bsr_indication_message*>(ctx->data);

    if (reinterpret_cast<const uint8_t*>(&mac_ctx) + sizeof(srsran::ul_bsr_indication_message) >
        reinterpret_cast<const uint8_t*>(ctx->data_end)) {
        return JBPF_CODELET_FAILURE;
    }

    uint32_t *not_empty = (uint32_t*)jbpf_map_lookup_elem(&bsr_custom_not_empty, &zero_index);
    if (!not_empty) return JBPF_CODELET_FAILURE;

    bsr_stats_custom *out = (bsr_stats_custom *)jbpf_map_lookup_elem(&stats_map_bsr_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;

    int new_val = 0;
    uint32_t ind = JBPF_PROTOHASH_LOOKUP_ELEM_32(out, stats, bsr_custom_hash, mac_ctx.ue_index, new_val);
    if (ind >= MAX_NUM_UE) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(ind));
    uint32_t safe_ind = ind & (MAX_NUM_UE - 1);

    out = (bsr_stats_custom *)jbpf_map_lookup_elem(&stats_map_bsr_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));

    if (new_val) {
        out->stats[safe_ind].du_ue_index    = mac_ctx.ue_index;
        out->stats[safe_ind].cnt            = 0;
        out->stats[safe_ind].total_bytes    = 0;
        out->stats[safe_ind].max_bytes      = 0;
        out->stats[safe_ind].bsr_sliding_avg_kb = 0;
        out->stats[safe_ind].bsr_sliding_cnt    = 0;
    }

    // ── Accumulate bytes from all LCGs in this BSR report ────────────────────
    uint64_t event_bytes = 0;
    size_t n = mac_ctx.reported_lcgs.size();
    if (n > srsran::MAX_NOF_LCGS) n = srsran::MAX_NOF_LCGS;
    const srsran::ul_bsr_lcg_report* base = mac_ctx.reported_lcgs.data();

    #pragma clang loop unroll(full)
    for (size_t i = 0; i < srsran::MAX_NOF_LCGS; ++i) {
        if (i >= n) break;
        const srsran::ul_bsr_lcg_report* rep = &base[i];
        if ((const uint8_t*)rep + sizeof(*rep) > (const uint8_t*)ctx->data_end)
            return JBPF_CODELET_FAILURE;
        event_bytes += rep->nof_bytes;
    }

    out->stats[safe_ind].cnt++;
    out->stats[safe_ind].total_bytes += event_bytes;
    if (event_bytes > out->stats[safe_ind].max_bytes)
        out->stats[safe_ind].max_bytes = event_bytes;

    // ── Sliding window (bytes → KB to avoid int32 overflow) ──────────────────

    out = (bsr_stats_custom *)jbpf_map_lookup_elem(&stats_map_bsr_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));
    asm volatile("" : "+r"(safe_ind));
    safe_ind &= (MAX_NUM_UE - 1);

    int32_t event_kb = (int32_t)(event_bytes >> 10);

    bsr_window_data *wdata = (bsr_window_data *)jbpf_map_lookup_elem(&bsr_window_map, &zero_index);
    if (wdata) {
        asm volatile("" : "+r"(wdata));
        asm volatile("" : "+r"(safe_ind));
        safe_ind &= (MAX_NUM_UE - 1);

        bsr_window_entry *w = &wdata->entries[safe_ind];

        // Evict oldest sample when window is full
        if (w->count >= BSR_WINDOW_SIZE) {
            int32_t old_val = window_read(w, w->write_idx);
            w->window_sum -= old_val;
        }

        // Insert new sample
        window_write(w, w->write_idx, event_kb);
        w->window_sum += event_kb;
        w->write_idx++;
        if (w->count < BSR_WINDOW_SIZE)
            w->count++;

        uint32_t wcnt = w->count;
        if (wcnt > 0) {
            out = (bsr_stats_custom *)jbpf_map_lookup_elem(&stats_map_bsr_custom, &zero_index);
            if (!out) return JBPF_CODELET_FAILURE;
            asm volatile("" : "+r"(out));
            asm volatile("" : "+r"(safe_ind));
            safe_ind &= (MAX_NUM_UE - 1);

            out->stats[safe_ind].bsr_sliding_avg_kb = signed_div(w->window_sum, wcnt);
            out->stats[safe_ind].bsr_sliding_cnt    = wcnt;
        }
    }

    *not_empty = 1;
    return JBPF_CODELET_SUCCESS;
}
