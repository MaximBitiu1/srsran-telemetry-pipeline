// Copyright (c) Microsoft Corporation. All rights reserved.
// Custom SINR codelet — adds variance and sliding window average
// Based on mac_sched_crc_stats.cpp

#include <linux/bpf.h>

#include "jbpf_srsran_contexts.h"
#include "srsran/scheduler/scheduler_feedback_handler.h"

#include "mac_helpers.h"
#include "mac_sched_crc_stats_custom.pb.h"

#include "../utils/misc_utils.h"
#include "../utils/hashmap_utils.h"

#include "jbpf_defs.h"
#include "jbpf_helper.h"
#include "jbpf_helper_utils.h"


// ── Sliding-window ring buffer (persists across reporting windows) ──────────

#define SINR_WINDOW_SIZE 16  // must be power of 2

struct sinr_window_entry {
    int32_t samples[SINR_WINDOW_SIZE];
    uint32_t write_idx;
    uint32_t count;
    int32_t window_sum;
};

struct sinr_window_data {
    sinr_window_entry entries[MAX_NUM_UE];
};

// Ring buffer map — NOT cleared by collector, persists across windows
struct jbpf_load_map_def SEC("maps") sinr_window_map = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(sinr_window_data),
    .max_entries = 1,
};


// ── Shared maps (linked with collector) ─────────────────────────────────────

struct jbpf_load_map_def SEC("maps") crc_custom_not_empty = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(uint32_t),
    .max_entries = 1,
};

struct jbpf_load_map_def SEC("maps") stats_map_crc_custom = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(crc_stats_custom),
    .max_entries = 1,
};

DEFINE_PROTOHASH_32(crc_custom_hash, MAX_NUM_UE);


// ── Ring buffer read/write helpers (switch/case for BPF verifier) ───────────

static __attribute__((always_inline))
int32_t window_read(sinr_window_entry *w, uint32_t idx)
{
    switch (idx & (SINR_WINDOW_SIZE - 1)) {
        case 0:  return w->samples[0];
        case 1:  return w->samples[1];
        case 2:  return w->samples[2];
        case 3:  return w->samples[3];
        case 4:  return w->samples[4];
        case 5:  return w->samples[5];
        case 6:  return w->samples[6];
        case 7:  return w->samples[7];
        case 8:  return w->samples[8];
        case 9:  return w->samples[9];
        case 10: return w->samples[10];
        case 11: return w->samples[11];
        case 12: return w->samples[12];
        case 13: return w->samples[13];
        case 14: return w->samples[14];
        default: return w->samples[15];
    }
}

static __attribute__((always_inline))
void window_write(sinr_window_entry *w, uint32_t idx, int32_t val)
{
    switch (idx & (SINR_WINDOW_SIZE - 1)) {
        case 0:  w->samples[0]  = val; break;
        case 1:  w->samples[1]  = val; break;
        case 2:  w->samples[2]  = val; break;
        case 3:  w->samples[3]  = val; break;
        case 4:  w->samples[4]  = val; break;
        case 5:  w->samples[5]  = val; break;
        case 6:  w->samples[6]  = val; break;
        case 7:  w->samples[7]  = val; break;
        case 8:  w->samples[8]  = val; break;
        case 9:  w->samples[9]  = val; break;
        case 10: w->samples[10] = val; break;
        case 11: w->samples[11] = val; break;
        case 12: w->samples[12] = val; break;
        case 13: w->samples[13] = val; break;
        case 14: w->samples[14] = val; break;
        default: w->samples[15] = val; break;
    }
}


// ── Unsigned division helper (BPF has no signed division) ───────────────────

static __attribute__((always_inline))
int32_t signed_div(int32_t num, uint32_t den)
{
    if (den == 0) return 0;
    if (num >= 0)
        return (int32_t)((uint32_t)num / den);
    else
        return -(int32_t)((uint32_t)(-num) / den);
}


// ── Main entry point ────────────────────────────────────────────────────────

extern "C" SEC("jbpf_ran_mac_sched")
uint64_t jbpf_main(void* state)
{
    int zero_index = 0;
    struct jbpf_mac_sched_ctx *ctx = (jbpf_mac_sched_ctx *)state;

    const srsran::ul_crc_pdu_indication& mac_ctx =
        *reinterpret_cast<const srsran::ul_crc_pdu_indication*>(ctx->data);

    // Bounds check
    if (reinterpret_cast<const uint8_t*>(&mac_ctx) + sizeof(srsran::ul_crc_pdu_indication) >
        reinterpret_cast<const uint8_t*>(ctx->data_end)) {
        return JBPF_CODELET_FAILURE;
    }

    uint32_t *not_empty = (uint32_t*)jbpf_map_lookup_elem(&crc_custom_not_empty, &zero_index);
    if (!not_empty)
        return JBPF_CODELET_FAILURE;

    crc_stats_custom *out = (crc_stats_custom *)jbpf_map_lookup_elem(&stats_map_crc_custom, &zero_index);
    if (!out)
        return JBPF_CODELET_FAILURE;

    bool processed = (bool)(ctx->srs_meta_data1 >> 32);
    if (!processed)
        return JBPF_CODELET_SUCCESS;

    // ── UE hash lookup ──────────────────────────────────────────────────

    int new_val = 0;
    uint32_t ind = JBPF_PROTOHASH_LOOKUP_ELEM_32(out, stats, crc_custom_hash, ctx->du_ue_index, new_val);

    if (ind >= MAX_NUM_UE) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(ind));
    uint32_t safe_ind = ind & (MAX_NUM_UE - 1);

    // Re-lookup for verifier
    out = (crc_stats_custom *)jbpf_map_lookup_elem(&stats_map_crc_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));

    // ── Initialise new UE entry ─────────────────────────────────────────

    if (new_val) {
        out->stats[safe_ind].succ_tx = 0;
        out->stats[safe_ind].cnt_tx = 0;
        out->stats[safe_ind].min_sinr = INT16_MAX;
        out->stats[safe_ind].max_sinr = INT16_MIN;
        out->stats[safe_ind].sum_sinr = 0;
        out->stats[safe_ind].cnt_sinr = 0;
        out->stats[safe_ind].sum_sq_sinr = 0;
        out->stats[safe_ind].sinr_variance = 0;
        out->stats[safe_ind].sinr_sliding_avg = 0;
        out->stats[safe_ind].sinr_sliding_cnt = 0;
    }

    // ── TX success/count ────────────────────────────────────────────────

    out->stats[safe_ind].cnt_tx++;
    if (mac_ctx.tb_crc_success) {
        out->stats[safe_ind].succ_tx++;
    }

    // ── SINR: basic stats + variance + sliding window ───────────────────

    // Re-lookup for verifier
    out = (crc_stats_custom *)jbpf_map_lookup_elem(&stats_map_crc_custom, &zero_index);
    if (!out) return JBPF_CODELET_FAILURE;
    asm volatile("" : "+r"(out));
    asm volatile("" : "+r"(safe_ind));
    safe_ind &= (MAX_NUM_UE - 1);

    if (mac_ctx.ul_sinr_dB.has_value()) {

        int32_t ul_sinr_dB = (int32_t)fixedpt_toint(float_to_fixed(mac_ctx.ul_sinr_dB.value()));

        // ── Basic min/max/sum/count ─────────────────────────────────────
        if (ul_sinr_dB < out->stats[safe_ind].min_sinr)
            out->stats[safe_ind].min_sinr = ul_sinr_dB;
        if (ul_sinr_dB > out->stats[safe_ind].max_sinr)
            out->stats[safe_ind].max_sinr = ul_sinr_dB;

        out->stats[safe_ind].sum_sinr += ul_sinr_dB;
        out->stats[safe_ind].cnt_sinr++;

        // ── Variance: accumulate sum of squares ─────────────────────────
        out->stats[safe_ind].sum_sq_sinr += (ul_sinr_dB * ul_sinr_dB);

        // Compute running variance: Var = E[X^2] - (E[X])^2
        uint32_t cnt = out->stats[safe_ind].cnt_sinr;
        if (cnt > 0) {
            int32_t mean = signed_div(out->stats[safe_ind].sum_sinr, cnt);
            int32_t mean_sq = mean * mean;
            // sum_sq_sinr is always >= 0, safe to use unsigned div
            int32_t e_sq = (int32_t)((uint32_t)out->stats[safe_ind].sum_sq_sinr / cnt);
            out->stats[safe_ind].sinr_variance = e_sq - mean_sq;
        }

        // ── Sliding window average (last 16 samples) ───────────────────
        sinr_window_data *wdata = (sinr_window_data *)jbpf_map_lookup_elem(&sinr_window_map, &zero_index);
        if (wdata) {
            asm volatile("" : "+r"(wdata));
            asm volatile("" : "+r"(safe_ind));
            safe_ind &= (MAX_NUM_UE - 1);

            sinr_window_entry *w = &wdata->entries[safe_ind];

            // If window full, subtract oldest sample
            if (w->count >= SINR_WINDOW_SIZE) {
                int32_t old_val = window_read(w, w->write_idx);
                w->window_sum -= old_val;
            }

            // Write new sample
            window_write(w, w->write_idx, ul_sinr_dB);
            w->window_sum += ul_sinr_dB;
            w->write_idx++;
            if (w->count < SINR_WINDOW_SIZE)
                w->count++;

            // Compute sliding average
            uint32_t wcnt = w->count;
            if (wcnt > 0) {
                // Re-lookup out for verifier after window map access
                out = (crc_stats_custom *)jbpf_map_lookup_elem(&stats_map_crc_custom, &zero_index);
                if (!out) return JBPF_CODELET_FAILURE;
                asm volatile("" : "+r"(out));
                asm volatile("" : "+r"(safe_ind));
                safe_ind &= (MAX_NUM_UE - 1);

                out->stats[safe_ind].sinr_sliding_avg = signed_div(w->window_sum, wcnt);
                out->stats[safe_ind].sinr_sliding_cnt = wcnt;
            }
        }
    }

    *not_empty = 1;

    return JBPF_CODELET_SUCCESS;
}
