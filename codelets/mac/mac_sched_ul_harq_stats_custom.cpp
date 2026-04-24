// UL HARQ MCS custom codelet — sliding window average + variance on MCS.
// MCS values (0–28) are small enough that int32 arithmetic is safe throughout.
// Based on mac_sched_ul_harq_stats.cpp + mac_sched_crc_stats_custom.cpp

#include <linux/bpf.h>

#include "jbpf_srsran_contexts.h"
#include "srsran/scheduler/scheduler_feedback_handler.h"

#include "mac_helpers.h"
#include "mac_sched_ul_harq_stats_custom.pb.h"

#include "../utils/misc_utils.h"
#include "../utils/hashmap_utils.h"

#include "jbpf_defs.h"
#include "jbpf_helper.h"
#include "jbpf_helper_utils.h"


// ── Sliding-window ring buffer (16 MCS samples) ───────────────────────────────

#define MCS_WINDOW_SIZE 16   // must be power of 2

struct mcs_window_entry {
    int32_t  samples[MCS_WINDOW_SIZE];
    uint32_t write_idx;
    uint32_t count;
    int32_t  window_sum;
    int32_t  window_sum_sq;  // sum of squares for variance (MCS^2 ≤ 784, 16×784=12544 — safe int32)
};

struct mcs_window_data {
    mcs_window_entry entries[MAX_NUM_UE];
};

struct jbpf_load_map_def SEC("maps") mcs_window_map = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(mcs_window_data),
    .max_entries = 1,
};


// ── Shared maps (linked with collector) ──────────────────────────────────────

struct jbpf_load_map_def SEC("maps") ul_harq_custom_not_empty = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(uint32_t),
    .max_entries = 1,
};

struct jbpf_load_map_def SEC("maps") stats_map_ul_harq_custom = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(ul_harq_stats_custom),
    .max_entries = 1,
};

DEFINE_PROTOHASH_32(ul_harq_custom_hash, MAX_NUM_UE);


// ── Ring buffer helpers ───────────────────────────────────────────────────────

static __attribute__((always_inline))
int32_t window_read(mcs_window_entry *w, uint32_t idx)
{
    switch (idx & (MCS_WINDOW_SIZE - 1)) {
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
void window_write(mcs_window_entry *w, uint32_t idx, int32_t val)
{
    switch (idx & (MCS_WINDOW_SIZE - 1)) {
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

    const jbpf_mac_sched_harq_ctx_info& harq_info =
        *reinterpret_cast<const jbpf_mac_sched_harq_ctx_info*>(ctx->data);

    if (reinterpret_cast<const uint8_t*>(&harq_info) + sizeof(jbpf_mac_sched_harq_ctx_info) >
        reinterpret_cast<const uint8_t*>(ctx->data_end)) {
        return JBPF_CODELET_FAILURE;
    }

    uint32_t *not_empty = (uint32_t*)jbpf_map_lookup_elem(&ul_harq_custom_not_empty, &zero_index);
    if (!not_empty) return JBPF_CODELET_FAILURE;

    ul_harq_stats_custom *out = (ul_harq_stats_custom *)jbpf_map_lookup_elem(&stats_map_ul_harq_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;

    int new_val = 0;
    uint32_t ind = JBPF_PROTOHASH_LOOKUP_ELEM_32(out, stats, ul_harq_custom_hash, ctx->du_ue_index, new_val);
    if (ind >= MAX_NUM_UE) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(ind));
    uint32_t safe_ind = ind & (MAX_NUM_UE - 1);

    out = (ul_harq_stats_custom *)jbpf_map_lookup_elem(&stats_map_ul_harq_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));

    if (new_val) {
        out->stats[safe_ind].du_ue_index   = ctx->du_ue_index;
        out->stats[safe_ind].mcs_count     = 0;
        out->stats[safe_ind].mcs_sum       = 0;
        out->stats[safe_ind].mcs_min       = 0xFFFFFFFF;
        out->stats[safe_ind].mcs_max       = 0;
        out->stats[safe_ind].mcs_sliding_avg = 0;
        out->stats[safe_ind].mcs_sliding_cnt = 0;
        out->stats[safe_ind].mcs_variance    = 0;
        out->stats[safe_ind].cons_retx_max   = 0;
    }

    int32_t mcs_val = (int32_t)harq_info.mcs;

    // ── Basic accumulation ────────────────────────────────────────────────────
    out->stats[safe_ind].mcs_count++;
    out->stats[safe_ind].mcs_sum += (uint32_t)mcs_val;
    if ((uint32_t)mcs_val < out->stats[safe_ind].mcs_min)
        out->stats[safe_ind].mcs_min = (uint32_t)mcs_val;
    if ((uint32_t)mcs_val > out->stats[safe_ind].mcs_max)
        out->stats[safe_ind].mcs_max = (uint32_t)mcs_val;

    // Track consecutive retransmissions
    if (harq_info.nof_retxs > out->stats[safe_ind].cons_retx_max)
        out->stats[safe_ind].cons_retx_max = harq_info.nof_retxs;

    // ── Sliding window + variance ─────────────────────────────────────────────

    out = (ul_harq_stats_custom *)jbpf_map_lookup_elem(&stats_map_ul_harq_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));
    asm volatile("" : "+r"(safe_ind));
    safe_ind &= (MAX_NUM_UE - 1);

    mcs_window_data *wdata = (mcs_window_data *)jbpf_map_lookup_elem(&mcs_window_map, &zero_index);
    if (wdata) {
        asm volatile("" : "+r"(wdata));
        asm volatile("" : "+r"(safe_ind));
        safe_ind &= (MAX_NUM_UE - 1);

        mcs_window_entry *w = &wdata->entries[safe_ind];

        // Evict oldest sample
        if (w->count >= MCS_WINDOW_SIZE) {
            int32_t old_val = window_read(w, w->write_idx);
            w->window_sum    -= old_val;
            w->window_sum_sq -= (old_val * old_val);
        }

        // Insert new sample
        window_write(w, w->write_idx, mcs_val);
        w->window_sum    += mcs_val;
        w->window_sum_sq += (mcs_val * mcs_val);
        w->write_idx++;
        if (w->count < MCS_WINDOW_SIZE)
            w->count++;

        uint32_t wcnt = w->count;
        if (wcnt > 0) {
            out = (ul_harq_stats_custom *)jbpf_map_lookup_elem(&stats_map_ul_harq_custom, &zero_index);
            if (!out) return JBPF_CODELET_FAILURE;
            asm volatile("" : "+r"(out));
            asm volatile("" : "+r"(safe_ind));
            safe_ind &= (MAX_NUM_UE - 1);

            // Sliding average
            out->stats[safe_ind].mcs_sliding_avg = signed_div(w->window_sum, wcnt);
            out->stats[safe_ind].mcs_sliding_cnt = wcnt;

            // Variance: E[X^2] - (E[X])^2
            // MCS max = 28 → MCS^2 max = 784 → sum_sq max = 16 × 784 = 12544 (safe int32)
            int32_t mean    = out->stats[safe_ind].mcs_sliding_avg;
            int32_t mean_sq = mean * mean;
            int32_t e_sq    = signed_div(w->window_sum_sq, wcnt);
            out->stats[safe_ind].mcs_variance = e_sq - mean_sq;
        }
    }

    *not_empty = 1;
    return JBPF_CODELET_SUCCESS;
}
