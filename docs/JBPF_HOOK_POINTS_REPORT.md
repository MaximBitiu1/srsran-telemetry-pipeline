# Complete jbpf Hook Points Report — srsRAN_Project_jbpf

## Summary

**Total hook points declared:** 68 unique hooks
- **srsRAN-specific hooks** (in `jbpf_srsran_hooks.h`): 66
- **jbpf built-in hooks** (in `jbpf_agent_hooks.h`): 2 (`report_stats`, `periodic_call`)
- **Hooks referenced by codelets but not found in current codebase:** 4 (`mac_sched_slice_mgmt`, `cucp_pdu_session_bearer_setup`, `cucp_pdu_session_bearer_modify`, `cucp_pdu_session_remove`)

---

## 1. Complete List of All jbpf Hook Points

### 1.1 FAPI (PHY ↔ MAC Interface) — 9 hooks

| # | Hook Name | Type | Context | Declared In | Defined (DEFINE_JBPF_HOOK) In | Has Codelet? |
|---|-----------|------|---------|-------------|-------------------------------|--------------|
| 1 | `fapi_rx_data_indication` | FAPI phy→mac | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/fapi_to_mac_data_msg_translator.cpp:35` | NO |
| 2 | `fapi_crc_indication` | FAPI phy→mac | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/fapi_to_mac_data_msg_translator.cpp:36` | YES (fapi_ul_crc) |
| 3 | `fapi_uci_indication` | FAPI phy→mac | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/fapi_to_mac_data_msg_translator.cpp:37` | NO |
| 4 | `fapi_srs_indication` | FAPI phy→mac | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/fapi_to_mac_data_msg_translator.cpp:38` | NO |
| 5 | `fapi_rach_indication` | FAPI phy→mac | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/fapi_to_mac_data_msg_translator.cpp:39` | YES (fapi_rach) |
| 6 | `fapi_dl_tti_request` | FAPI mac→phy | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/mac_to_fapi_translator.cpp:40` | YES (fapi_dl_conf) |
| 7 | `fapi_ul_tti_request` | FAPI mac→phy | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/mac_to_fapi_translator.cpp:41` | YES (fapi_ul_conf) |
| 8 | `fapi_ul_dci_request` | FAPI mac→phy | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/mac_to_fapi_translator.cpp:42` | NO |
| 9 | `fapi_tx_data_request` | FAPI mac→phy | `jbpf_ran_layer2_ctx` | `jbpf_srsran_hooks.h` | `lib/fapi_adaptor/mac/mac_to_fapi_translator.cpp:43` | NO |

### 1.2 OFH (Open Fronthaul / xRAN) — 1 hook

| # | Hook Name | Context | Declared In | Defined In | Has Codelet? |
|---|-----------|---------|-------------|------------|--------------|
| 10 | `capture_xran_packet` | `jbpf_ran_ofh_ctx` | `jbpf_srsran_hooks.h:86` | `lib/ofh/receiver/ofh_message_receiver_impl.cpp:30` | YES (xran_packets) |

### 1.3 DU UE Context Management — 3 hooks

| # | Hook Name | Context | Declared In | Defined In | Has Codelet? |
|---|-----------|---------|-------------|------------|--------------|
| 11 | `du_ue_ctx_creation` | `jbpf_ran_generic_ctx` | `jbpf_srsran_hooks.h:140` | `lib/du/du_high/du_manager/procedures/ue_creation_procedure.cpp:32` | YES (ue_contexts) |
| 12 | `du_ue_ctx_update_crnti` | `jbpf_ran_generic_ctx` | `jbpf_srsran_hooks.h:151` | `lib/du/du_high/du_manager/du_ue/du_ue_manager.cpp:36` | YES (ue_contexts) |
| 13 | `du_ue_ctx_deletion` | `jbpf_ran_generic_ctx` | `jbpf_srsran_hooks.h:162` | `lib/du/du_high/du_manager/du_ue/du_ue_manager.cpp:35` | YES (ue_contexts) |

### 1.4 MAC Scheduler — 15 hooks

| # | Hook Name | Context | Declared In | Defined In | Has Codelet? |
|---|-----------|---------|-------------|------------|--------------|
| 14 | `mac_sched_ue_creation` | `jbpf_mac_sched_ctx` (no payload) | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:33` | NO |
| 15 | `mac_sched_ue_reconfig` | `jbpf_mac_sched_ctx` (no payload) | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:34` | NO |
| 16 | `mac_sched_ue_deletion` | `jbpf_mac_sched_ctx` (no payload) | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:35` | YES (mac) |
| 17 | `mac_sched_ue_config_applied` | `jbpf_mac_sched_ctx` (no payload) | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:36` | NO |
| 18 | `mac_sched_ul_bsr_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:37` | YES (mac) |
| 19 | `mac_sched_crc_indication` | `jbpf_mac_sched_ctx` (custom) | `jbpf_srsran_hooks.h:225` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:38` | YES (mac) |
| 20 | `mac_sched_uci_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:39` | YES (mac) |
| 21 | `mac_sched_dl_mac_ce_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:40` | NO |
| 22 | `mac_sched_ul_phr_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:41` | YES (mac) |
| 23 | `mac_sched_dl_buffer_state_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:42` | NO |
| 24 | `mac_sched_srs_indication` | `jbpf_mac_sched_ctx` | `jbpf_srsran_hooks.h` | `lib/scheduler/ue_scheduling/ue_event_manager.cpp:43` | NO |
| 25 | `mac_sched_harq_ul` | `jbpf_mac_sched_ctx` (HARQ) | `jbpf_srsran_hooks.h` | `lib/scheduler/cell/cell_harq_manager.cpp:30` | YES (mac) |
| 26 | `mac_sched_harq_dl` | `jbpf_mac_sched_ctx` (HARQ) | `jbpf_srsran_hooks.h` | `lib/scheduler/cell/cell_harq_manager.cpp:31` | YES (mac) |

**Referenced by codelets but NOT declared/defined in current codebase:**

| # | Hook Name | Referenced By | Status |
|---|-----------|---------------|--------|
| 27 | `mac_sched_slice_mgmt` | `codelets/slice_mgmt/slice_mgmt.yaml` | **NOT IN CODEBASE** — control hook, likely in a separate branch |

### 1.5 PDCP (Packet Data Convergence Protocol) — 18 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 28 | `pdcp_dl_creation` | DL entity created | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:33` | NO |
| 29 | `pdcp_dl_deletion` | DL entity deleted | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:34` | YES (pdcp) |
| 30 | `pdcp_dl_new_sdu` | New SDU from upper layers | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:35` | YES (pdcp) |
| 31 | `pdcp_dl_dropped_sdu` | SDU dropped | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:36` | NO |
| 32 | `pdcp_dl_tx_data_pdu` | Data PDU sent to lower layers | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:37` | YES (pdcp) |
| 33 | `pdcp_dl_tx_control_pdu` | Control PDU sent to lower layers | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:38` | YES (pdcp) |
| 34 | `pdcp_dl_handle_tx_notification` | First byte of SDU sent | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:39` | NO |
| 35 | `pdcp_dl_handle_delivery_notification` | SDU fully delivered | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:40` | NO |
| 36 | `pdcp_dl_discard_pdu` | SDU discarded | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:41` | YES (pdcp) |
| 37 | `pdcp_dl_reestablish` | Bearer re-established | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_tx.cpp:42` | NO |
| 38 | `pdcp_ul_creation` | UL entity created | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:32` | NO |
| 39 | `pdcp_ul_deletion` | UL entity deleted | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:33` | YES (pdcp) |
| 40 | `pdcp_ul_rx_data_pdu` | Data PDU received from lower layers | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:34` | YES (pdcp) |
| 41 | `pdcp_ul_rx_control_pdu` | Control PDU received | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:35` | YES (pdcp) |
| 42 | `pdcp_ul_rx_pdu_dropped` | Received PDU dropped | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:36` | NO |
| 43 | `pdcp_ul_deliver_sdu` | SDU delivered to upper layers | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:37` | YES (pdcp) |
| 44 | `pdcp_ul_reestablish` | Bearer re-established | `jbpf_ran_generic_ctx` | `lib/pdcp/pdcp_entity_rx.cpp:38` | NO |

### 1.6 RLC (Radio Link Control) — 17 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 45 | `rlc_dl_creation` | DL entity created | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:34` | NO |
| 46 | `rlc_dl_deletion` | DL entity deleted | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:35` | YES (rlc) |
| 47 | `rlc_dl_new_sdu` | SDU from upper layer | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:36` | YES (rlc) |
| 48 | `rlc_dl_lost_sdu` | SDU dropped on receive | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:37` | NO |
| 49 | `rlc_dl_discard_sdu` | SDU discarded | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:38` | NO |
| 50 | `rlc_dl_sdu_send_started` | SDU transmission starts | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:39` | YES (rlc) |
| 51 | `rlc_dl_sdu_send_completed` | All SDU bytes transmitted | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:40` | YES (rlc) |
| 52 | `rlc_dl_sdu_delivered` | SDU received by peer | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:41` | YES (rlc) |
| 53 | `rlc_dl_tx_pdu` | PDU delivered to lower layers | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:42` | YES (rlc) |
| 54 | `rlc_dl_rx_status` | STATUS PDU received | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:43` | NO |
| 55 | `rlc_dl_am_tx_pdu_retx_count` | AM PDU retx count updated | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:44` | YES (rlc) |
| 56 | `rlc_dl_am_tx_pdu_max_retx_count_reached` | AM PDU max retx reached | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_tx_am_entity.cpp:45` | NO (codelet exists but not in YAML) |
| 57 | `rlc_ul_creation` | UL entity created | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_rx_am_entity.cpp:29` | NO |
| 58 | `rlc_ul_deletion` | UL entity deleted | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_rx_am_entity.cpp:30` | YES (rlc) |
| 59 | `rlc_ul_rx_pdu` | PDU received from lower layers | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_rx_am_entity.cpp:31` | YES (rlc) |
| 60 | `rlc_ul_sdu_recv_started` | First PDU for an SDU received | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_rx_am_entity.cpp:32` | NO |
| 61 | `rlc_ul_sdu_delivered` | SDU delivered to upper layers | `jbpf_ran_generic_ctx` | `lib/rlc/rlc_rx_am_entity.cpp:33` | YES (rlc) |

### 1.7 RRC (Radio Resource Control) — 6 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 62 | `rrc_ue_add` | UE added | `jbpf_ran_generic_ctx` | `lib/rrc/rrc_du_impl.cpp:34` | YES (rrc) |
| 63 | `rrc_ue_remove` | UE removed | `jbpf_ran_generic_ctx` | `lib/rrc/rrc_du_impl.cpp:35` | YES (rrc) |
| 64 | `rrc_ue_procedure_started` | RRC procedure started | `jbpf_ran_generic_ctx` | `lib/rrc/ue/procedures/rrc_setup_procedure.cpp:31` | NO |
| 65 | `rrc_ue_procedure_completed` | RRC procedure completed | `jbpf_ran_generic_ctx` | `lib/rrc/ue/procedures/rrc_setup_procedure.cpp:32` | YES (rrc) |
| 66 | `rrc_ue_update_id` | UE 5G-TMSI update | `jbpf_ran_generic_ctx` | `lib/rrc/ue/procedures/rrc_setup_procedure.cpp:33` | YES (rrc) |
| 67 | `rrc_ue_update_context` | UE context update (reestablishment) | `jbpf_ran_generic_ctx` | `lib/rrc/ue/procedures/rrc_reestablishment_procedure.cpp:33` | YES (rrc) |

### 1.8 E1AP (E1 Application Protocol) — 7 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 68 | `e1_cucp_bearer_context_setup` | CU-CP bearer setup | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_cp/e1ap_cu_cp_impl.cpp:38` | YES (ue_contexts) |
| 69 | `e1_cucp_bearer_context_modification` | CU-CP bearer modification | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_cp/e1ap_cu_cp_impl.cpp:39` | NO |
| 70 | `e1_cucp_bearer_context_release` | CU-CP bearer release | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_cp/e1ap_cu_cp_impl.cpp:40` | NO |
| 71 | `e1_cucp_bearer_context_inactivity` | CU-CP bearer inactivity | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_cp/e1ap_cu_cp_impl.cpp:41` | NO |
| 72 | `e1_cuup_bearer_context_setup` | CU-UP bearer setup | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_up/e1ap_cu_up_impl.cpp:39` | YES (ue_contexts) |
| 73 | `e1_cuup_bearer_context_modification` | CU-UP bearer modification | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_up/e1ap_cu_up_impl.cpp:40` | NO |
| 74 | `e1_cuup_bearer_context_release` | CU-UP bearer release | `jbpf_ran_generic_ctx` | `lib/e1ap/cu_up/e1ap_cu_up_impl.cpp:41` | YES (ue_contexts) |

### 1.9 CUCP UE Manager — 3 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 75 | `cucp_uemgr_ue_add` | UE added at CU-CP | `jbpf_ran_generic_ctx` | `lib/cu_cp/ue_manager/ue_manager_impl.cpp:29` | YES (ue_contexts) |
| 76 | `cucp_uemgr_ue_update` | UE updated at CU-CP | `jbpf_ran_generic_ctx` | `lib/cu_cp/ue_manager/ue_manager_impl.cpp:30` | YES (ue_contexts) |
| 77 | `cucp_uemgr_ue_remove` | UE removed at CU-CP | `jbpf_ran_generic_ctx` | `lib/cu_cp/ue_manager/ue_manager_impl.cpp:31` | YES (ue_contexts) |

### 1.10 NGAP (NG Application Protocol) — 3 hooks

| # | Hook Name | Trigger | Context | Defined In | Has Codelet? |
|---|-----------|---------|---------|------------|--------------|
| 78 | `ngap_procedure_started` | NGAP procedure begins | `jbpf_ran_generic_ctx` | `lib/ngap/procedures/ngap_initial_context_setup_procedure.cpp:31` | YES (ngap) |
| 79 | `ngap_procedure_completed` | NGAP procedure ends | `jbpf_ran_generic_ctx` | `lib/ngap/procedures/ngap_initial_context_setup_procedure.cpp:32` | YES (ngap) |
| 80 | `ngap_reset` | NGAP reset | `jbpf_ran_generic_ctx` | `lib/ngap/ngap_impl.cpp:46` | YES (ngap) |

### 1.11 jbpf Built-in Hooks — 2 hooks

| # | Hook Name | Trigger | Context | Declared In | Has Codelet? |
|---|-----------|---------|---------|-------------|--------------|
| 81 | `report_stats` | Periodic (jbpf internal timer) | `jbpf_stats_ctx` | `external/jbpf/src/core/jbpf_agent_hooks.h` | YES (perf, mac, fapi_*, pdcp, rlc) |
| 82 | `periodic_call` | Periodic (configurable) | `jbpf_stats_ctx` | `external/jbpf/src/core/jbpf_agent_hooks.h` | NO |

### 1.12 Hooks Referenced by Codelets but NOT in Current Codebase — 4 hooks

| # | Hook Name | Referenced By | Notes |
|---|-----------|---------------|-------|
| 83 | `mac_sched_slice_mgmt` | `codelets/slice_mgmt/slice_mgmt.yaml` | Control hook for slice management; requires srsRAN modifications (per jrtc-apps README) |
| 84 | `cucp_pdu_session_bearer_setup` | `codelets/ue_contexts/ue_contexts.yaml` | CU-CP PDU session bearer setup; likely in a separate branch |
| 85 | `cucp_pdu_session_bearer_modify` | `codelets/ue_contexts/ue_contexts.yaml` | CU-CP PDU session bearer modify; likely in a separate branch |
| 86 | `cucp_pdu_session_remove` | `codelets/ue_contexts/ue_contexts.yaml` | CU-CP PDU session removal; likely in a separate branch |

---

## 2. Codelet Directory Structure

```
~/Desktop/jrtc-apps/codelets/
├── Makefile                    # Top-level build
├── Makefile.common             # Shared build rules
├── Makefile.defs               # Build definitions
├── make.sh                     # Build script
├── .gitignore
│
├── fapi_dl_conf/               # FAPI DL TTI request stats
│   ├── fapi_gnb_dl_config_stats_collect.cpp/.o
│   ├── fapi_gnb_dl_config_stats_report.cpp/.o
│   ├── fapi_gnb_dl_config_stats.proto/.pb/.pb.h/.py/.options
│   ├── fapi_gnb_dl_config_stats.yaml
│   └── Makefile
│
├── fapi_rach/                  # FAPI RACH indication stats
│   ├── fapi_gnb_rach_stats_collect.cpp/.o
│   ├── fapi_gnb_rach_stats_report.cpp/.o
│   ├── fapi_gnb_rach_stats.proto/.pb/.pb.h/.py/.options
│   ├── fapi_gnb_rach_stats.yaml
│   └── Makefile
│
├── fapi_ul_conf/               # FAPI UL TTI request stats
│   ├── fapi_gnb_ul_config_stats_collect.cpp/.o
│   ├── fapi_gnb_ul_config_stats_report.cpp/.o
│   ├── fapi_gnb_ul_config_stats.proto/.pb/.pb.h/.py/.options
│   ├── fapi_gnb_ul_config_stats.yaml
│   └── Makefile
│
├── fapi_ul_crc/                # FAPI CRC indication stats
│   ├── fapi_gnb_crc.cpp/.o + fapi_gnb_crc_stats_collect.cpp/.o
│   ├── fapi_gnb_crc_stats_report.cpp/.o
│   ├── fapi_gnb_crc.proto + fapi_gnb_crc_stats.proto
│   ├── fapi_gnb_crc.yaml + fapi_gnb_crc_stats.yaml
│   └── Makefile
│
├── mac/                        # MAC scheduler stats (11 codelets)
│   ├── mac_helpers.h
│   ├── mac_stats_collect.cpp/.o            # report_stats hook (CRC/BSR/PHR/UCI output)
│   ├── mac_stats_collect_dl_harq.cpp/.o    # report_stats hook (DL HARQ output)
│   ├── mac_stats_collect_ul_harq.cpp/.o    # report_stats hook (UL HARQ output)
│   ├── mac_stats_collect_harq.cpp/.o       # (legacy/backup)
│   ├── mac_sched_crc_stats.cpp/.o          # mac_sched_crc_indication hook
│   ├── mac_sched_bsr_stats.cpp/.o          # mac_sched_ul_bsr_indication hook
│   ├── mac_sched_phr_stats.cpp/.o          # mac_sched_ul_phr_indication hook
│   ├── mac_sched_uci_pdu_stats.cpp/.o      # mac_sched_uci_indication hook
│   ├── mac_sched_dl_harq_stats.cpp/.o      # mac_sched_harq_dl hook
│   ├── mac_sched_ul_harq_stats.cpp/.o      # mac_sched_harq_ul hook
│   ├── mac_sched_ue_deletion.cpp/.o        # mac_sched_ue_deletion hook
│   ├── mac_sched_*_stats.proto/.pb/.pb.h/.py/.options (5 proto schemas)
│   ├── mac_stats.yaml
│   └── Makefile
│
├── ngap/                       # NGAP procedure tracking (3 codelets)
│   ├── ngap_procedure_started.cpp/.o
│   ├── ngap_procedure_completed.cpp/.o
│   ├── ngap_reset.cpp/.o
│   ├── ngap.proto/.pb/.pb.h/.py
│   ├── ngap.yaml
│   └── Makefile
│
├── pdcp/                       # PDCP stats (9 codelets)
│   ├── pdcp_helpers.h
│   ├── pdcp_collect.cpp/.o                 # report_stats hook (DL + UL output)
│   ├── pdcp_dl_new_sdu.cpp/.o
│   ├── pdcp_dl_deletion.cpp/.o
│   ├── pdcp_dl_tx_data_pdu.cpp/.o
│   ├── pdcp_dl_tx_control_pdu.cpp/.o
│   ├── pdcp_dl_discard.cpp/.o
│   ├── pdcp_ul_rx_data_pdu.cpp/.o
│   ├── pdcp_ul_rx_control_pdu.cpp/.o
│   ├── pdcp_ul_deliver_sdu.cpp/.o
│   ├── pdcp_ul_deletion.cpp/.o
│   ├── pdcp_dl_stats.proto + pdcp_ul_stats.proto
│   ├── pdcp_stats.yaml
│   └── Makefile
│
├── perf/                       # jbpf performance stats (1 codelet)
│   ├── jbpf_stats_report.c/.o
│   ├── jbpf_stats_report.proto/.pb/.pb.h/.py/.options
│   ├── jbpf_stats.yaml
│   └── Makefile
│
├── rlc/                        # RLC stats (11 codelets)
│   ├── rlc_helpers.h
│   ├── rlc_collect.cpp/.o                  # report_stats hook (DL + UL output)
│   ├── rlc_dl_new_sdu.cpp/.o
│   ├── rlc_dl_tx_sdu_started.cpp/.o
│   ├── rlc_dl_tx_sdu_completed.cpp/.o
│   ├── rlc_dl_tx_sdu_delivered.cpp/.o
│   ├── rlc_dl_deletion.cpp/.o
│   ├── rlc_dl_tx_pdu.cpp/.o
│   ├── rlc_dl_am_tx_pdu_retx_count.cpp/.o
│   ├── rlc_dl_am_tx_pdu_retx_max_reached.cpp/.o
│   ├── rlc_ul_rx_pdu.cpp/.o
│   ├── rlc_ul_deliver_sdu.cpp/.o
│   ├── rlc_ul_deletion.cpp/.o
│   ├── rlc_dl_stats.proto + rlc_ul_stats.proto
│   ├── rlc_stats.yaml
│   └── Makefile
│
├── rrc/                        # RRC UE tracking (5 codelets)
│   ├── rrc_ue_add.cpp/.o + rrc_ue_add.proto
│   ├── rrc_ue_remove.cpp/.o + rrc_ue_remove.proto
│   ├── rrc_ue_procedure.cpp/.o + rrc_ue_procedure.proto
│   ├── rrc_ue_update_context.cpp/.o + rrc_ue_update_context.proto
│   ├── rrc_ue_update_id.cpp/.o + rrc_ue_update_id.proto
│   ├── rrc.yaml
│   └── Makefile
│
├── slice_mgmt/                 # Slice management control (1 codelet)
│   ├── slice_mgmt.cpp
│   ├── slice_mgmt.proto/.pb/.pb.h/.py/.options
│   ├── slice_mgmt.yaml
│   └── Makefile
│
├── ue_contexts/                # UE context lifecycle (12 codelets)
│   ├── du_ue_ctx_creation.cpp
│   ├── du_ue_ctx_update_crnti.cpp
│   ├── du_ue_ctx_deletion.cpp
│   ├── cucp_uemgr_ue_add.cpp
│   ├── cucp_uemgr_ue_update.cpp
│   ├── cucp_uemgr_ue_remove.cpp
│   ├── e1_cucp_bearer_context_setup.cpp
│   ├── e1_cuup_bearer_context_setup.cpp
│   ├── e1_cuup_bearer_context_release.cpp
│   ├── cucp_pdu_session_bearer_add_modify.cpp
│   ├── cucp_pdu_session_remove.cpp
│   ├── ue_contexts.proto/.pb/.pb.h/.py
│   ├── ue_contexts.yaml
│   ├── README.md
│   └── Makefile
│
├── utils/                      # Shared utility headers
│   ├── hashmap_utils.h
│   ├── misc_utils.h
│   ├── net_utils.h
│   └── stats_utils.h
│
└── xran_packets/               # xRAN/OFH packet capture (2 codelets)
    ├── xran_packets_collect.c/.o
    ├── xran_packets_report.c/.o
    ├── xran_format.h
    ├── xran_packet_info.proto/.pb/.pb.h/.py/.options
    ├── xran_packets.yaml
    └── Makefile
```

---

## 3. Codelet Loading Configuration Format

Deployment configs are YAML files loaded via `jrtc-ctl`. Format:

```yaml
codeletset_id: <unique_set_name>        # Identifier for the codelet set

codelet_descriptor:
  - codelet_name: <name>                # Unique codelet name within the set
    codelet_path: <path_to_.o>          # Path to compiled eBPF object
    hook_name: <jbpf_hook_name>         # Which hook to attach to
    priority: <int>                     # Execution priority (1 = highest)

    # Optional: output channels (telemetry egress)
    out_io_channel:
      - name: <output_map_name>         # Map name used in codelet code
        forward_destination: DestinationUDP | DestinationNone
        serde:
          file_path: <path_to_serializer.so>   # Nanopb serializer shared lib
          protobuf:
            package_path: <path_to_.pb>        # Compiled protobuf descriptor
            msg_name: <protobuf_message_name>  # Message type to serialize

    # Optional: input channels (control ingress)
    in_io_channel:
      - name: <input_map_name>
        serde:
          file_path: <path_to_serializer.so>
          protobuf:
            package_path: <path_to_.pb>
            msg_name: <protobuf_message_name>

    # Optional: shared maps between codelets in the same set
    linked_maps:
      - map_name: <map_name_in_this_codelet>
        linked_codelet_name: <other_codelet_name>
        linked_map_name: <map_name_in_other_codelet>
```

**Environment variables used:** `${JBPF_CODELETS}` → base path to codelets directory.

---

## 4. Protobuf Schema Files Found

| File | Directory | Used By |
|------|-----------|---------|
| `mac_sched_crc_stats.proto` | `codelets/mac/` | CRC stats output |
| `mac_sched_bsr_stats.proto` | `codelets/mac/` | BSR stats output |
| `mac_sched_phr_stats.proto` | `codelets/mac/` | PHR stats output |
| `mac_sched_uci_stats.proto` | `codelets/mac/` | UCI stats output |
| `mac_sched_harq_stats.proto` | `codelets/mac/` | DL/UL HARQ stats output |
| `fapi_gnb_dl_config_stats.proto` | `codelets/fapi_dl_conf/` | FAPI DL config stats |
| `fapi_gnb_ul_config_stats.proto` | `codelets/fapi_ul_conf/` | FAPI UL config stats |
| `fapi_gnb_rach_stats.proto` | `codelets/fapi_rach/` | FAPI RACH stats |
| `fapi_gnb_crc.proto` | `codelets/fapi_ul_crc/` | FAPI CRC raw |
| `fapi_gnb_crc_stats.proto` | `codelets/fapi_ul_crc/` | FAPI CRC stats |
| `pdcp_dl_stats.proto` | `codelets/pdcp/` | PDCP DL stats output |
| `pdcp_ul_stats.proto` | `codelets/pdcp/` | PDCP UL stats output |
| `rlc_dl_stats.proto` | `codelets/rlc/` | RLC DL stats output |
| `rlc_ul_stats.proto` | `codelets/rlc/` | RLC UL stats output |
| `ngap.proto` | `codelets/ngap/` | NGAP procedure events |
| `rrc_ue_add.proto` | `codelets/rrc/` | RRC UE add event |
| `rrc_ue_remove.proto` | `codelets/rrc/` | RRC UE remove event |
| `rrc_ue_procedure.proto` | `codelets/rrc/` | RRC procedure event |
| `rrc_ue_update_context.proto` | `codelets/rrc/` | RRC context update event |
| `rrc_ue_update_id.proto` | `codelets/rrc/` | RRC TMSI update event |
| `ue_contexts.proto` | `codelets/ue_contexts/` | UE lifecycle events (DU, CU-CP, E1AP, PDU session) |
| `slice_mgmt.proto` | `codelets/slice_mgmt/` | Slice management request/indication |
| `jbpf_stats_report.proto` | `codelets/perf/` | jbpf performance stats |
| `xran_packet_info.proto` | `codelets/xran_packets/` | xRAN packet capture stats |

---

## 5. Hooks Used vs Unused

### Hooks WITH existing codelets (used): 42 hooks consumed

| Layer | Hooks Used by Codelets |
|-------|----------------------|
| **FAPI** | `fapi_crc_indication`, `fapi_rach_indication`, `fapi_dl_tti_request`, `fapi_ul_tti_request` |
| **OFH** | `capture_xran_packet` |
| **DU UE** | `du_ue_ctx_creation`, `du_ue_ctx_update_crnti`, `du_ue_ctx_deletion` |
| **MAC Sched** | `mac_sched_crc_indication`, `mac_sched_ul_bsr_indication`, `mac_sched_uci_indication`, `mac_sched_ul_phr_indication`, `mac_sched_harq_dl`, `mac_sched_harq_ul`, `mac_sched_ue_deletion` |
| **PDCP** | `pdcp_dl_new_sdu`, `pdcp_dl_deletion`, `pdcp_dl_tx_data_pdu`, `pdcp_dl_tx_control_pdu`, `pdcp_dl_discard_pdu`, `pdcp_ul_deletion`, `pdcp_ul_rx_data_pdu`, `pdcp_ul_rx_control_pdu`, `pdcp_ul_deliver_sdu` |
| **RLC** | `rlc_dl_new_sdu`, `rlc_dl_deletion`, `rlc_dl_sdu_send_started`, `rlc_dl_sdu_send_completed`, `rlc_dl_sdu_delivered`, `rlc_dl_tx_pdu`, `rlc_dl_am_tx_pdu_retx_count`, `rlc_ul_rx_pdu`, `rlc_ul_sdu_delivered`, `rlc_ul_deletion` |
| **RRC** | `rrc_ue_add`, `rrc_ue_remove`, `rrc_ue_procedure_completed`, `rrc_ue_update_id`, `rrc_ue_update_context` |
| **E1AP** | `e1_cucp_bearer_context_setup`, `e1_cuup_bearer_context_setup`, `e1_cuup_bearer_context_release` |
| **CUCP UE Mgr** | `cucp_uemgr_ue_add`, `cucp_uemgr_ue_update`, `cucp_uemgr_ue_remove` |
| **NGAP** | `ngap_procedure_started`, `ngap_procedure_completed`, `ngap_reset` |
| **Built-in** | `report_stats` |

### Hooks WITHOUT codelets (unused/available): 24 hooks

| Layer | Unused Hooks | Notes |
|-------|-------------|-------|
| **FAPI** | `fapi_rx_data_indication`, `fapi_uci_indication`, `fapi_srs_indication`, `fapi_ul_dci_request`, `fapi_tx_data_request` | Raw FAPI data available for new telemetry |
| **MAC Sched** | `mac_sched_ue_creation`, `mac_sched_ue_reconfig`, `mac_sched_ue_config_applied`, `mac_sched_dl_mac_ce_indication`, `mac_sched_dl_buffer_state_indication`, `mac_sched_srs_indication` | UE lifecycle + DL buffer + SRS + MAC CE events |
| **PDCP** | `pdcp_dl_creation`, `pdcp_dl_dropped_sdu`, `pdcp_dl_handle_tx_notification`, `pdcp_dl_handle_delivery_notification`, `pdcp_dl_reestablish`, `pdcp_ul_creation`, `pdcp_ul_rx_pdu_dropped`, `pdcp_ul_reestablish` | Creation/reestablishment + notification hooks |
| **RLC** | `rlc_dl_creation`, `rlc_dl_lost_sdu`, `rlc_dl_discard_sdu`, `rlc_dl_rx_status`, `rlc_dl_am_tx_pdu_max_retx_count_reached`, `rlc_ul_creation`, `rlc_ul_sdu_recv_started` | SDU loss + status + creation hooks |
| **RRC** | `rrc_ue_procedure_started` | Procedure start (only completion is used) |
| **E1AP** | `e1_cucp_bearer_context_modification`, `e1_cucp_bearer_context_release`, `e1_cucp_bearer_context_inactivity`, `e1_cuup_bearer_context_modification` | Bearer modification/release/inactivity |
| **Built-in** | `periodic_call` | Generic periodic hook, can be used for any scheduled task |

---

## 6. Context Structure Types

| Context Type | Size (approx) | Used By | Key Fields |
|-------------|---------------|---------|------------|
| `jbpf_ran_ofh_ctx` | 27 bytes | `capture_xran_packet` | `data`, `data_end`, `meta_data`, `ctx_id`, `direction` |
| `jbpf_ran_layer2_ctx` | 32 bytes | All 9 FAPI hooks | `data`, `data_end`, `meta_data`, `ctx_id`, `frame`, `slot`, `cell_id` |
| `jbpf_mac_sched_ctx` | 40 bytes | All 15 MAC sched hooks | `data`, `data_end`, `meta_data`, `srs_meta_data1`, `ctx_id`, `du_ue_index`, `cell_id`, `rnti` |
| `jbpf_ran_generic_ctx` | 56 bytes | PDCP/RLC/RRC/E1AP/CUCP/NGAP/DU hooks | `data`, `data_end`, `meta_data`, `srs_meta_data1`-`4` |
| `jbpf_stats_ctx` | — | `report_stats`, `periodic_call` | `meas_period`, `data`, `data_end` |

---

## 7. Key Source Files

| File | Purpose |
|------|---------|
| `srsran_jbpf/verifier/specs/jbpf_srsran_hooks.h` | Master hook declarations for all srsRAN-specific hooks |
| `external/jbpf/src/core/jbpf_agent_hooks.h` | Built-in `report_stats` and `periodic_call` hook declarations |
| `out/inc/jbpf_hook.h` | `DECLARE_JBPF_HOOK` / `DEFINE_JBPF_HOOK` macro definitions |
| `out/inc/jbpf_hook_defs.h` | Hook struct definitions (`struct jbpf_hook`, `struct jbpf_hook_codelet`) |
| `srsran_jbpf/verifier/specs/context_descriptors.hpp` | Verifier context descriptors for each context type |
| `configs/jbpf_gnb_config.yml` | jbpf configuration for the gNB |
