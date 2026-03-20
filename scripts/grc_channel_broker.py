#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNU Radio Channel Broker for srsRAN ZMQ Radio

Message-boundary-preserving ZMQ broker using pyzmq + numpy.
Sits between gNB and UE on ZMQ REQ/REP sockets, forwarding IQ samples
while applying realistic RF impairments:
  - AWGN (Additive White Gaussian Noise) — always active
  - Rician/Rayleigh flat fading (AR1 Jake's model) — optional
  - Doppler spread

Port topology (same as C broker):
  gNB TX (REP :4000) -> Broker DL (REQ->4000, impair, REP :2000) -> UE RX (REQ->2000)
  UE  TX (REP :2001) -> Broker UL (REQ->2001, impair, REP :4001) -> gNB RX (REQ->4001)

Usage:
  python3 grc_channel_broker.py --snr 28 --fading --k-factor 3
  python3 grc_channel_broker.py --snr 20 --fading --doppler 70
  python3 grc_channel_broker.py --snr 28 --fading --rayleigh
  python3 grc_channel_broker.py --help
"""

import sys
import signal
import argparse
import math
import threading
import numpy as np
import zmq
from scipy.special import j0 as bessel_j0


# ── Fading State (AR1 Jake's model, same as C broker) ──────────────────────
#
# Scatter (NLOS) component, updated once per message:
#   h_I[n] = alpha * h_I[n-1] + sigma_inn * N(0,1)
#   h_Q[n] = alpha * h_Q[n-1] + sigma_inn * N(0,1)
#
# Total channel coefficient:
#   h = sqrt(K/(K+1)) * 1.0  +  sqrt(1/(K+1)) * (h_I + j*h_Q)
#       └── LoS (fixed) ──┘      └── scattered (fading) ──┘
#
# where:
#   K       = Rician K-factor (linear). K=0 → Rayleigh, K→∞ → AWGN-like.
#   alpha   = J0(2*pi*f_d*T)             (Jake's Bessel autocorrelation)
#   sigma   = sqrt((1 - alpha^2) * 0.5)  (innovation std, unit mean power)
#   T       = num_samples / sample_rate   (message duration)
#   f_d     = max Doppler frequency (Hz)

class FadingState:
    """Flat fading model with Rician/Rayleigh support."""

    def __init__(self, enabled, doppler_hz, sample_rate, k_factor_db, rng):
        self.enabled = enabled
        self.doppler_hz = doppler_hz
        self.sample_rate = sample_rate
        self.rng = rng

        # Convert K-factor dB -> linear
        k_lin = 10.0 ** (k_factor_db / 10.0)
        kp1 = k_lin + 1.0
        self.los_amp = math.sqrt(k_lin / kp1)
        self.scatter_amp = math.sqrt(1.0 / kp1)

        if enabled:
            self.h_I = rng.standard_normal() * math.sqrt(0.5)
            self.h_Q = rng.standard_normal() * math.sqrt(0.5)
        else:
            self.h_I = 1.0
            self.h_Q = 0.0

    def update_and_apply(self, iq_samples):
        """Update fading state and return faded IQ samples (complex64 array)."""
        if not self.enabled:
            return iq_samples

        n = len(iq_samples)
        T = n / self.sample_rate
        alpha = float(bessel_j0(2.0 * math.pi * self.doppler_hz * T))
        a2 = alpha * alpha
        sigma = math.sqrt(max(0.0, (1.0 - a2) * 0.5))

        # Update scatter component
        n1, n2 = self.rng.standard_normal(2)
        self.h_I = alpha * self.h_I + sigma * n1
        self.h_Q = alpha * self.h_Q + sigma * n2

        # Total channel coefficient (flat — single complex scalar)
        h = complex(
            self.los_amp + self.scatter_amp * self.h_I,
            self.scatter_amp * self.h_Q,
        )

        return iq_samples * np.complex64(h)


def add_awgn(iq_samples, noise_std, rng):
    """Add AWGN to complex64 IQ samples."""
    noise = (rng.standard_normal(len(iq_samples))
             + 1j * rng.standard_normal(len(iq_samples))) * np.float32(noise_std)
    return iq_samples + noise.astype(np.complex64)


def relay_thread(label, src_addr, dst_addr, noise_std, fading, rng, stop_event):
    """Worker thread matching C broker pattern:
    1) Wait for downstream REQ  2) Forward to upstream  3) Get IQ  4) Impair  5) Reply
    """
    ctx = zmq.Context()
    timeout_ms = 500

    # REQ socket to pull IQ from source (gNB TX or UE TX)
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.LINGER, 0)
    req.setsockopt(zmq.RCVTIMEO, timeout_ms)
    req.setsockopt(zmq.SNDTIMEO, timeout_ms)
    req.connect(src_addr)

    # REP socket to serve IQ to destination (UE RX or gNB RX)
    rep = ctx.socket(zmq.REP)
    rep.setsockopt(zmq.LINGER, 0)
    rep.setsockopt(zmq.RCVTIMEO, timeout_ms)
    rep.setsockopt(zmq.SNDTIMEO, timeout_ms)
    rep.bind(dst_addr)

    count = 0
    while not stop_event.is_set():
        try:
            # 1) Wait for REQ from downstream (UE-RX or gNB-RX)
            try:
                downstream_req = rep.recv()
            except zmq.Again:
                continue  # timeout — check stop_event and retry

            # 2) Forward request to upstream (gNB-TX or UE-TX)
            req.send(downstream_req)

            # 3) Receive IQ data from upstream (must complete — REQ state machine)
            while not stop_event.is_set():
                try:
                    raw = req.recv()
                    break
                except zmq.Again:
                    continue  # keep waiting for upstream reply

            if stop_event.is_set():
                break

            iq = np.frombuffer(raw, dtype=np.complex64).copy()

            # 4) Apply channel impairments
            iq = fading.update_and_apply(iq)
            iq = add_awgn(iq, noise_std, rng)

            # 5) Send impaired IQ back to downstream
            rep.send(iq.tobytes())

            count += 1
            if count == 1:
                print(f"[GRC] {label}: first message relayed ({len(iq)} samples)")

        except zmq.ZMQError as e:
            if stop_event.is_set():
                break
            print(f"[GRC] {label}: ZMQ error: {e}")
            break

    req.close()
    rep.close()
    ctx.term()
    print(f"[GRC] {label}: thread exiting (relayed {count} messages)")


running = True


def parse_args():
    p = argparse.ArgumentParser(
        description="GNU Radio Channel Broker for srsRAN ZMQ Radio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # AWGN only (no fading)
  python3 grc_channel_broker.py --snr 28

  # Rician fading (recommended — triggers HARQ failures)
  python3 grc_channel_broker.py --snr 28 --fading --k-factor 3

  # Rayleigh fading (deep nulls, may crash UE)
  python3 grc_channel_broker.py --snr 28 --fading --rayleigh

  # Asymmetric DL/UL SNR
  python3 grc_channel_broker.py --dl-snr 25 --ul-snr 15 --fading
        """,
    )

    # SNR
    p.add_argument("--snr", type=float, default=28.0,
                   help="SNR in dB for both DL and UL (default: 28)")
    p.add_argument("--dl-snr", type=float, default=None,
                   help="DL SNR in dB (overrides --snr for DL)")
    p.add_argument("--ul-snr", type=float, default=None,
                   help="UL SNR in dB (overrides --snr for UL)")

    # Fading
    p.add_argument("--fading", action="store_true",
                   help="Enable fading channel (Rician by default)")
    p.add_argument("--rayleigh", action="store_true",
                   help="Use Rayleigh fading (no LoS, deep nulls possible)")
    p.add_argument("--k-factor", type=float, default=3.0,
                   help="Rician K-factor in dB (default: 3). Ignored with --rayleigh")
    p.add_argument("--doppler", type=float, default=5.0,
                   help="Max Doppler frequency in Hz (default: 5)")
    # Kept for CLI compat with launch script; not used in flat model
    p.add_argument("--profile", type=str, default="flat",
                   choices=["flat", "epa", "eva", "etu"],
                   help="Power delay profile (default: flat). Currently flat only.")

    # Network
    p.add_argument("--gnb-addr", type=str, default="127.0.0.1",
                   help="gNB address (default: 127.0.0.1)")
    p.add_argument("--ue-addr", type=str, default="127.0.0.1",
                   help="UE address (default: 127.0.0.1)")
    p.add_argument("--gnb-tx-port", type=int, default=4000,
                   help="gNB TX port (default: 4000)")
    p.add_argument("--gnb-rx-port", type=int, default=4001,
                   help="gNB RX port (default: 4001)")
    p.add_argument("--ue-rx-port", type=int, default=2000,
                   help="UE RX port (default: 2000)")
    p.add_argument("--ue-tx-port", type=int, default=2001,
                   help="UE TX port (default: 2001)")

    # System
    p.add_argument("--samp-rate", type=float, default=23.04e6,
                   help="Sample rate in Hz (default: 23.04e6)")

    args = p.parse_args()

    # Resolve SNR
    if args.dl_snr is None:
        args.dl_snr = args.snr
    if args.ul_snr is None:
        args.ul_snr = args.snr

    # Resolve fading model
    if args.rayleigh:
        args.k_factor = 0.0

    return args


def main():
    args = parse_args()

    # Ensure output is visible in log files (unbuffered)
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, line_buffering=True)

    fading_enabled = args.fading
    k_db = args.k_factor

    # Noise std dev: for complex noise split across I/Q
    dl_noise_std = 1.0 / math.sqrt(2.0 * 10.0 ** (args.dl_snr / 10.0))
    ul_noise_std = 1.0 / math.sqrt(2.0 * 10.0 ** (args.ul_snr / 10.0))

    print("=" * 60)
    print("  GRC Channel Broker (pyzmq + numpy)")
    print("=" * 60)
    print(f"  Mode: {'Fading' if fading_enabled else 'AWGN only'}")
    if fading_enabled:
        ftype = "Rayleigh" if args.rayleigh else f"Rician (K={k_db} dB)"
        print(f"  Model: {ftype}")
        print(f"  Doppler: {args.doppler} Hz")
    print(f"  DL SNR: {args.dl_snr} dB | UL SNR: {args.ul_snr} dB")
    print(f"  Noise std: DL={dl_noise_std:.6f}  UL={ul_noise_std:.6f}")
    gnb_tx = args.gnb_tx_port
    gnb_rx = args.gnb_rx_port
    ue_rx = args.ue_rx_port
    ue_tx = args.ue_tx_port
    print(f"  DL: gNB:{gnb_tx} -> broker -> :{ue_rx} UE")
    print(f"  UL: UE:{ue_tx} -> broker -> :{gnb_rx} gNB")
    print("=" * 60)

    # Create per-thread RNGs and fading states
    dl_rng = np.random.default_rng(42)
    ul_rng = np.random.default_rng(137)
    dl_fading = FadingState(fading_enabled, args.doppler, args.samp_rate, k_db, dl_rng)
    ul_fading = FadingState(fading_enabled, args.doppler, args.samp_rate, k_db, ul_rng)

    stop_event = threading.Event()

    gnb_addr = args.gnb_addr
    ue_addr = args.ue_addr

    dl_thread = threading.Thread(
        target=relay_thread,
        args=("DL",
              f"tcp://{gnb_addr}:{gnb_tx}",
              f"tcp://0.0.0.0:{ue_rx}",
              dl_noise_std, dl_fading, dl_rng, stop_event),
        daemon=True,
    )
    ul_thread = threading.Thread(
        target=relay_thread,
        args=("UL",
              f"tcp://{ue_addr}:{ue_tx}",
              f"tcp://0.0.0.0:{gnb_rx}",
              ul_noise_std, ul_fading, ul_rng, stop_event),
        daemon=True,
    )

    def sig_handler(sig=None, frame=None):
        print("\n[GRC] Signal caught, stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    print("[GRC] Starting relay threads...")
    dl_thread.start()
    ul_thread.start()

    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    except KeyboardInterrupt:
        sig_handler()

    dl_thread.join(timeout=3)
    ul_thread.join(timeout=3)
    print("[GRC] Broker stopped.")


if __name__ == "__main__":
    main()
