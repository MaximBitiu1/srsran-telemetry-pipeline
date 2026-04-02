# Stress Anomaly Dataset — Plain-Language Summary

---

## What This Work Is About

The thesis instruments a 5G base station (gNB) with ~60 eBPF hooks that record
telemetry at every layer of the protocol stack: how fast the scheduler runs, how full
the uplink buffer is, how many retransmissions happen, what the signal quality is.
The goal is to collect a labelled dataset of both normal and anomalous behaviour so
that an anomaly detector can be trained on it.

The radio channel broker (built earlier) covers one class of anomaly: bad radio
conditions — noise, fading, interference. This extension covers a second class:
**the base station software behaving abnormally due to system-level problems**.

---

## The 5 Stressor Categories — What They Mean

### CPU Stressors (scenarios 01–06)

**What they simulate:** A cloud-hosted or virtualised gNB sharing a physical server
with other workloads that consume CPU. In a real deployment this could be another
network function, a noisy VM neighbour, or a runaway process consuming compute.

**What we do:** Use `stress-ng` to saturate CPU cores, or `cpulimit` to cap the gNB
process's CPU budget.

**What happened:** Nothing observable. The gNB runs at hard real-time priority
(`SCHED_FIFO:96`) — the Linux scheduler always runs it before any normal process,
regardless of CPU load. These scenarios are indistinguishable from baseline.

**What this tells us:** The 5G stack's real-time design deliberately protects it from
ordinary CPU contention. An attacker or fault that only adds CPU load without touching
scheduling policy will have no measurable effect on the telemetry.

---

### Memory Pressure (scenarios 07–10)

**What they simulate:** A gNB running low on available RAM — for example, a memory
leak in another process on the same host, a large model being loaded alongside the
gNB, or an orchestrator that has over-allocated the node.

**What we do:** Use Linux cgroups to cap how much RAM the gNB process can hold in
memory (forcing page reclaim), or use `stress-ng` to balloon system-wide free memory.

**What happened:**
- Capping the gNB's own RSS (scenarios 07–09): modest buffer growth of 1.2–1.3×.
  The gNB keeps running normally because the scheduler isn't affected; only minor
  memory pressure on iperf3's send buffer is visible.
- System-wide memory balloon (scenario 10): BSR grows 4.6×, SINR drops 1.8 dB.
  When the whole system runs out of RAM, iperf3's socket buffers start getting
  evicted and the uplink queue backs up noticeably.

**What this tells us:** Moderate memory pressure barely registers. Severe system-wide
memory exhaustion does show up — mainly in the buffer size, not in radio metrics.

---

### Scheduler Attacks (scenarios 11–14)

**What they simulate:** A misconfiguration or malicious action that changes the gNB's
OS scheduling priority. In containerised or virtualised deployments, the orchestrator
(Kubernetes, OpenStack) sets thread priorities. A misconfigured deployment manifest,
a privilege escalation, or a bug in the container runtime could accidentally demote
the gNB's time-critical threads from real-time to normal scheduling class.

**What we do:**
- Place a competing thread at SCHED_FIFO:97 (one step above the gNB) to preempt it.
- Demote the gNB's 5 RT threads from `SCHED_FIFO:96` to `SCHED_BATCH` or
  `SCHED_OTHER` — the two lowest-priority scheduling classes in Linux.

**What happened:** The most dramatic anomaly in the entire dataset.

Demoting to `SCHED_BATCH` caused the FAPI-UL eBPF hook to record a maximum latency
of **7.3 milliseconds** — 103 times the baseline of 70 µs. What this means: the
gNB's MAC scheduler is supposed to run every 1 ms (one 5G slot). When its thread is
demoted, the OS stops waking it up on time. The scheduler stalls mid-slot, and the
jBPF hook records the full stall duration. The radio link keeps working (SINR and MCS
stay normal) but the gNB's internal timing is severely degraded — exactly the kind of
subtle software fault that would be invisible without telemetry instrumentation.

**What this tells us:** The jBPF hook latency metric is a direct sensor for OS
scheduling health. A 10–100× spike means "the gNB's real-time threads are not running
on time." No radio channel measurement can reveal this.

---

### Traffic Flooding (scenarios 15–19)

**What they simulate:** A misbehaving UE, a DDoS attack on the UE's application, a
runaway iperf3 session, or a legitimate burst of data (e.g. a video upload) that
exceeds the uplink's physical capacity. In all cases, more data arrives at the 5G
stack than the radio interface can carry.

**What we do:**
- Inject 100–150 Mbps UDP upstream (the 5G uplink can carry ~10 Mbps at MCS=28).
- Add artificial network delay and jitter via Linux `tc netem` to simulate a congested
  backhaul that forces queuing.
- Send aggressive short bursts at 400 Mbps for 200 ms windows.

**What happened:** The uplink buffer (BSR) grew to 25–33 MB — 12 to 16 times the
baseline — while the radio link remained completely healthy: SINR 23.3 dB (only 2 dB
below baseline), MCS=28 (maximum), zero HARQ failures. The MAC scheduler correctly
allocated all available PRBs every slot but could not drain the queue faster than
data was arriving.

**What this tells us:** Traffic-induced congestion and radio-induced congestion look
completely different in the telemetry. With the GRC broker you can also cause BSR
buildup, but only by degrading the channel — so BSR always rises together with SINR
drop and MCS reduction. Here BSR spikes in isolation, with a perfectly clean link.
A classifier can distinguish these two failure modes using the joint (BSR, SINR, MCS)
signature.

---

### Combined Stressors (scenarios 20–22)

**What they simulate:** Multiple simultaneous faults — the kind of compound failure
that tends to actually bring networks down. For example: a burst of user traffic
arrives at the same moment that an orchestrator restarts a service, temporarily
disrupting RT thread priorities.

**What we do:** Apply two stressors at once — for example, demote gNB RT threads
(scheduling attack) while also injecting a 100 Mbps UDP flood (traffic flood).

**What happened:**
- Scenario 22 (demote + 100M flood): hook latency 34× + BSR 18× simultaneously.
  This is a two-dimensional anomaly — both the software timing and the buffer depth
  are out of range at the same time.
- Scenario 20 (RT competitor + flood): BSR 17× but hook latency unchanged. The RT
  competitor at priority 97 is not strong enough to stall the gNB's threads, only
  the traffic flood signal is visible.

**What this tells us:** Compound faults produce multi-metric signatures. Single-cause
faults only activate one anomaly axis. This distinction is useful for training
detectors that not only flag anomalies but attribute them to a root cause.

---

## The Core Result in One Table

| Stressor | Unique vs radio broker? | Primary signal |
|----------|------------------------|----------------|
| CPU load | No — gNB immune | None |
| Memory RSS cap | No — broker does better | Weak BSR |
| Memory balloon | Partial | BSR ↑, SINR ↓ slightly |
| Sched RT competitor | Partial | BSR ↑ |
| **Sched RT demotion** | **Yes** | **Hook latency 40–103×** |
| **Traffic flood** | **Yes** | **BSR 12–16×, SINR/MCS unchanged** |
| **Combined** | **Yes** | **Hook + BSR simultaneously** |

The GRC broker owns the "radio channel degrades" anomaly class.
The scheduling and traffic stressors own two new classes: "gNB software timing
degrades" and "application-layer congestion". Together they give a richer, more
realistic training set for anomaly detection.

---

*Dataset: `~/Desktop/dataset/stress_20260325_204950` (23 scenarios, fading baseline)*
*Figures: `~/Desktop/bep_extension/figures/`*
