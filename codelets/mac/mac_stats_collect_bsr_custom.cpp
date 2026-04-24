// BSR custom collector — reads accumulated BSR sliding window stats and outputs them.
// Fires on report_stats (jbpf_ran_layer2); shares maps with mac_sched_bsr_stats_custom.

#include <linux/bpf.h>

#include "jbpf_srsran_contexts.h"
#include "mac_sched_bsr_stats_custom.pb.h"

#include "jbpf_defs.h"
#include "jbpf_helper.h"
#include "../utils/misc_utils.h"
#include "../utils/hashmap_utils.h"
#include "mac_helpers.h"

jbpf_ringbuf_map(output_map_bsr_custom, bsr_stats_custom, 1000);

struct jbpf_load_map_def SEC("maps") last_time_bsr_custom = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(uint64_t),
    .max_entries = 1,
};

// Shared with accumulator via linked_maps
struct jbpf_load_map_def SEC("maps") stats_map_bsr_custom = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(bsr_stats_custom),
    .max_entries = 1,
};

DEFINE_PROTOHASH_32(bsr_custom_hash, MAX_NUM_UE);

struct jbpf_load_map_def SEC("maps") bsr_custom_not_empty = {
    .type       = JBPF_MAP_TYPE_ARRAY,
    .key_size   = sizeof(int),
    .value_size = sizeof(uint32_t),
    .max_entries = 1,
};


extern "C" SEC("jbpf_ran_layer2")
uint64_t jbpf_main(void *state)
{
    uint64_t zero_index = 0;
    uint64_t timestamp  = jbpf_time_get_ns();
    uint64_t timestamp32 = (uint64_t)(timestamp >> 30);

    uint32_t *not_empty = (uint32_t*)jbpf_map_lookup_elem(&bsr_custom_not_empty, &zero_index);
    if (!not_empty) return JBPF_CODELET_FAILURE;

    void *c = jbpf_map_lookup_elem(&stats_map_bsr_custom, &zero_index);
    if (!c) return JBPF_CODELET_FAILURE;
    bsr_stats_custom *out = (bsr_stats_custom *)c;

    uint64_t *last_ts = (uint64_t*)jbpf_map_lookup_elem(&last_time_bsr_custom, &zero_index);
    if (!last_ts) return JBPF_CODELET_FAILURE;

    if (*not_empty && *last_ts < timestamp32) {
        out->timestamp = timestamp;

        int ret = jbpf_ringbuf_output(&output_map_bsr_custom, (void *)out, sizeof(bsr_stats_custom));

        JBPF_HASHMAP_CLEAR(&bsr_custom_hash);
        jbpf_map_clear(&stats_map_bsr_custom);

        *not_empty = 0;
        *last_ts   = timestamp32;

        if (ret < 0) return JBPF_CODELET_FAILURE;
    }

    return JBPF_CODELET_SUCCESS;
}
