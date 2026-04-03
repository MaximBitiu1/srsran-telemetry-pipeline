// Custom CRC stats collector — reads accumulated custom SINR stats and outputs
// Based on the CRC section of mac_stats_collect.cpp

#include <linux/bpf.h>

#include "jbpf_srsran_contexts.h"

#include "mac_sched_crc_stats_custom.pb.h"

#include "jbpf_defs.h"
#include "jbpf_helper.h"

#include "../utils/misc_utils.h"
#include "../utils/hashmap_utils.h"
#include "mac_helpers.h"


jbpf_ringbuf_map(output_map_crc_custom, crc_stats_custom, 1000);

struct jbpf_load_map_def SEC("maps") last_time_crc_custom = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(uint64_t),
    .max_entries = 1,
};

// Shared with hook codelet via linked_maps
struct jbpf_load_map_def SEC("maps") stats_map_crc_custom = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(crc_stats_custom),
    .max_entries = 1,
};

DEFINE_PROTOHASH_32(crc_custom_hash, MAX_NUM_UE);

struct jbpf_load_map_def SEC("maps") crc_custom_not_empty = {
    .type = JBPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(int),
    .value_size = sizeof(uint32_t),
    .max_entries = 1,
};


extern "C" SEC("jbpf_ran_layer2")
uint64_t jbpf_main(void *state)
{
    uint64_t zero_index = 0;
    uint64_t timestamp = jbpf_time_get_ns();

    // Report approximately every second (timestamp >> 30 ≈ /1e9)
    uint64_t timestamp32 = (uint64_t)(timestamp >> 30);

    uint32_t *not_empty = (uint32_t*)jbpf_map_lookup_elem(&crc_custom_not_empty, &zero_index);
    if (!not_empty)
        return JBPF_CODELET_FAILURE;

    void *c = jbpf_map_lookup_elem(&stats_map_crc_custom, &zero_index);
    if (!c)
        return JBPF_CODELET_FAILURE;
    crc_stats_custom *out = (crc_stats_custom *)c;

    uint64_t *last_timestamp = (uint64_t*)jbpf_map_lookup_elem(&last_time_crc_custom, &zero_index);
    if (!last_timestamp)
        return JBPF_CODELET_FAILURE;

    if (*not_empty && *last_timestamp < timestamp32) {
        out->timestamp = timestamp;

        int ret = jbpf_ringbuf_output(&output_map_crc_custom, (void *)out, sizeof(crc_stats_custom));

        JBPF_HASHMAP_CLEAR(&crc_custom_hash);

        // Clear per-window accumulation stats
        // NOTE: not thread safe, acceptable per original design
        jbpf_map_clear(&stats_map_crc_custom);

        *not_empty = 0;
        *last_timestamp = timestamp32;

        if (ret < 0) {
            return JBPF_CODELET_FAILURE;
        }
    }

    return JBPF_CODELET_SUCCESS;
}
