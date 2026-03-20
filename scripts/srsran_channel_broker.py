#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: srsRAN 5G NR Channel Broker
#
# Description:
#   ZMQ Channel Broker for srsRAN 5G NR with advanced impairments.
#
#   Capabilities BEYOND the C broker (zmq_channel_broker):
#     1. Frequency-selective fading (3GPP EPA/EVA/ETU multi-tap FIR)
#        — causes ISI that stresses the equalizer
#     2. Carrier Frequency Offset (CFO) injection
#        — phase drift that stresses synchronization tracking
#     3. Burst error injection (random subframe drops)
#        — simulates deep fades / interference blanking
#     4. Time-varying scenarios (Drive-by, Urban Walk, Edge-of-cell)
#        — automatically varies parameters for diverse telemetry
#     5. Live QT GUI with interactive sliders and real-time visualization

import sys
import signal
import math
import collections
import threading
import time as _time

import numpy as np
from packaging.version import Version as StrictVersion

from gnuradio import gr
from gnuradio import blocks
from gnuradio import qtgui
from gnuradio.filter import firdes
from gnuradio.fft import window
import sip

import zmq as _zmq
from scipy.special import j0 as bessel_j0
from scipy.signal import lfilter

from PyQt5 import Qt
from PyQt5 import QtCore


# ── 3GPP Delay Profiles (TS 36.104 Table B.2) ───────────────────────────────

DELAY_PROFILES = {
    'epa': {  # Extended Pedestrian A — 7 taps, max delay 410 ns
        'delays_ns': [0, 30, 70, 90, 110, 190, 410],
        'powers_db': [0.0, -1.0, -2.0, -3.0, -8.0, -17.2, -20.8],
        'default_doppler': 5.0,
    },
    'eva': {  # Extended Vehicular A — 9 taps, max delay 2510 ns
        'delays_ns': [0, 30, 150, 310, 370, 710, 1090, 1730, 2510],
        'powers_db': [0.0, -1.5, -1.4, -3.6, -0.6, -9.1, -7.0, -12.0, -16.9],
        'default_doppler': 70.0,
    },
    'etu': {  # Extended Typical Urban — 9 taps, max delay 5000 ns
        'delays_ns': [0, 50, 120, 200, 230, 500, 1600, 2300, 5000],
        'powers_db': [-1.0, -1.0, -1.0, 0.0, 0.0, 0.0, -3.0, -5.0, -7.0],
        'default_doppler': 300.0,
    },
}

FADING_MODES = {
    0: "Off (AWGN only)",
    1: "Flat Rician",
    2: "Flat Rayleigh",
    3: "EPA (7-tap, 410 ns)",
    4: "EVA (9-tap, 2510 ns)",
    5: "ETU (9-tap, 5000 ns)",
}

FADING_MODE_PROFILES = {3: 'epa', 4: 'eva', 5: 'etu'}

SCENARIO_NAMES = {
    0: "Manual",
    1: "Drive-by (30s cycle)",
    2: "Urban Walk (random)",
    3: "Edge of Cell (60s ramp)",
}


# ── Flat Fading (AR1 Jake's model) ──────────────────────────────────────────

class FadingState:
    """Flat fading: Rician (K>0) or Rayleigh (K=0), AR(1) Jake's Bessel model."""

    def __init__(self, enabled, doppler, samp_rate, k_db, rng):
        self.enabled = enabled
        self.doppler = doppler
        self.samp_rate = samp_rate
        self.rng = rng
        self._set_k(k_db)
        if enabled:
            self.h_I = rng.standard_normal() * math.sqrt(0.5)
            self.h_Q = rng.standard_normal() * math.sqrt(0.5)
        else:
            self.h_I = 1.0
            self.h_Q = 0.0

    def _set_k(self, k_db):
        k_lin = 10.0 ** (k_db / 10.0)
        kp1 = k_lin + 1.0
        self.los_amp = math.sqrt(k_lin / kp1)
        self.scatter_amp = math.sqrt(1.0 / kp1)

    def update_and_apply(self, iq):
        if not self.enabled:
            return iq
        n = len(iq)
        T = n / self.samp_rate
        alpha = float(bessel_j0(2.0 * math.pi * self.doppler * T))
        sigma = math.sqrt(max(0.0, (1.0 - alpha * alpha) * 0.5))
        n1, n2 = self.rng.standard_normal(2)
        self.h_I = alpha * self.h_I + sigma * n1
        self.h_Q = alpha * self.h_Q + sigma * n2
        h = complex(self.los_amp + self.scatter_amp * self.h_I,
                    self.scatter_amp * self.h_Q)
        return iq * np.complex64(h)

    def reconfigure(self, enabled, doppler, k_db=None):
        self.enabled = enabled
        self.doppler = doppler
        if k_db is not None:
            self._set_k(k_db)


# ── Frequency-Selective Fading (3GPP multi-tap) ─────────────────────────────

class FrequencySelectiveFading:
    """Multi-tap freq-selective fading with 3GPP EPA/EVA/ETU delay profiles.

    Each tap has an independent AR(1) Jake's fading process, applied as
    FIR convolution — causing inter-symbol interference (ISI) that the
    flat-fading C broker cannot produce.
    """

    def __init__(self, profile_name, samp_rate, doppler_hz, rng):
        prof = DELAY_PROFILES[profile_name]
        self.profile_name = profile_name
        self.samp_rate = samp_rate
        self.doppler = doppler_hz
        self.rng = rng
        self.enabled = True

        sample_period_ns = 1e9 / samp_rate
        self.tap_indices = [int(round(d / sample_period_ns)) for d in prof['delays_ns']]
        self.ntaps = max(1, self.tap_indices[-1] + 1)

        powers_lin = [10.0 ** (p / 20.0) for p in prof['powers_db']]
        total_power = sum(p * p for p in powers_lin)
        norm = math.sqrt(total_power) if total_power > 0 else 1.0
        self.tap_amplitudes = [p / norm for p in powers_lin]

        self.num_path_taps = len(self.tap_indices)
        self.tap_h_I = [rng.standard_normal() * math.sqrt(0.5)
                        for _ in range(self.num_path_taps)]
        self.tap_h_Q = [rng.standard_normal() * math.sqrt(0.5)
                        for _ in range(self.num_path_taps)]
        # lfilter state for seamless FIR across subframe boundaries
        self._zi = np.zeros(self.ntaps - 1, dtype=np.complex128)

    def update_and_apply(self, iq):
        if not self.enabled:
            return iq
        n = len(iq)
        T = n / self.samp_rate
        alpha = float(bessel_j0(2.0 * math.pi * self.doppler * T))
        sigma = math.sqrt(max(0.0, (1.0 - alpha * alpha) * 0.5))

        h = np.zeros(self.ntaps, dtype=np.complex128)
        for i, idx in enumerate(self.tap_indices):
            n1, n2 = self.rng.standard_normal(2)
            self.tap_h_I[i] = alpha * self.tap_h_I[i] + sigma * n1
            self.tap_h_Q[i] = alpha * self.tap_h_Q[i] + sigma * n2
            h[idx] = complex(
                self.tap_amplitudes[i] * self.tap_h_I[i],
                self.tap_amplitudes[i] * self.tap_h_Q[i])

        # scipy.signal.lfilter with zi state — seamless across subframes
        y, self._zi = lfilter(h, [1.0], iq, zi=self._zi)
        return y.astype(np.complex64)

    def reconfigure(self, enabled, doppler, _k_db=None):
        self.enabled = enabled
        self.doppler = doppler


# ── Impairment functions ─────────────────────────────────────────────────────

def add_awgn(iq, snr_linear, rng):
    """Add AWGN scaled to measured signal power (matches C broker)."""
    sig_power = float(np.mean(np.real(iq)**2 + np.imag(iq)**2))
    if sig_power < 1e-20:
        return iq
    noise_std = np.float32(np.sqrt(sig_power / snr_linear))
    buf = rng.standard_normal(2 * len(iq)).astype(np.float32)
    buf *= noise_std
    return iq + buf.view(np.complex64)


def apply_cfo(iq, cfo_hz, samp_rate, phase_state):
    """Carrier frequency offset — cumulative phase rotation across subframes."""
    if abs(cfo_hz) < 0.01:
        return iq
    n = len(iq)
    t = np.arange(n, dtype=np.float64) / samp_rate
    phase = 2.0 * np.pi * cfo_hz * t + phase_state[0]
    iq_out = iq * np.exp(1j * phase).astype(np.complex64)
    phase_state[0] = float(
        (phase_state[0] + 2.0 * np.pi * cfo_hz * n / samp_rate) % (2.0 * np.pi))
    return iq_out


# ── Scenario Runner ──────────────────────────────────────────────────────────

class ScenarioRunner:
    """Time-varying channel scenarios that auto-vary parameters."""

    def __init__(self):
        self.scenario = 0
        self._t0 = _time.time()
        self._snr_walk = 28.0
        self._dop_walk = 5.0
        self._rng = np.random.default_rng(99)

    def set_scenario(self, idx):
        self.scenario = idx
        self._t0 = _time.time()
        self._snr_walk = 28.0
        self._dop_walk = 5.0

    def tick(self):
        """Returns dict of parameter updates, or None if manual mode."""
        if self.scenario == 0:
            return None
        t = _time.time() - self._t0

        if self.scenario == 1:  # Drive-by: 30s sinusoidal cycle
            phase = math.pi * (t % 30.0) / 30.0
            s = math.sin(phase)
            return {
                'snr_db': 30.0 - 15.0 * s,       # 30 → 15 → 30 dB
                'doppler_hz': 5.0 + 195.0 * s,    # 5 → 200 → 5 Hz
                'drop_prob': 0.02 * s,             # 0 → 2% → 0
            }

        elif self.scenario == 2:  # Urban walk: bounded random perturbations
            self._snr_walk += float(self._rng.uniform(-1.5, 1.5))
            self._snr_walk = max(12.0, min(35.0, self._snr_walk))
            self._dop_walk += float(self._rng.uniform(-2.0, 2.0))
            self._dop_walk = max(1.0, min(20.0, self._dop_walk))
            drop = 0.05 if float(self._rng.random()) < 0.15 else 0.0
            return {
                'snr_db': self._snr_walk,
                'doppler_hz': self._dop_walk,
                'drop_prob': drop,
            }

        elif self.scenario == 3:  # Edge of cell: 60s linear decline
            frac = min(1.0, t / 60.0)
            return {
                'snr_db': 30.0 - 22.0 * frac,     # 30 → 8 dB
                'doppler_hz': 5.0,
                'drop_prob': 0.10 * frac,           # 0 → 10%
            }

        return None


# ── ZMQ Relay Thread ────────────────────────────────────────────────────────

def relay_thread(label, src_addr, dst_addr, imp, rng,
                 stop_ev, viz_buf, msg_counter):
    """Relay ZMQ REQ/REP with full impairment chain.

    imp: dict with mutable [val] entries:
        snr_linear, fading, cfo_hz, cfo_phase, drop_prob
    """
    ctx = _zmq.Context()
    tmo = 500
    req = ctx.socket(_zmq.REQ)
    req.setsockopt(_zmq.LINGER, 0)
    req.setsockopt(_zmq.RCVTIMEO, tmo)
    req.setsockopt(_zmq.SNDTIMEO, tmo)
    req.connect(src_addr)

    rep = ctx.socket(_zmq.REP)
    rep.setsockopt(_zmq.LINGER, 0)
    rep.setsockopt(_zmq.RCVTIMEO, tmo)
    rep.setsockopt(_zmq.SNDTIMEO, tmo)
    rep.bind(dst_addr)

    count = 0
    drops = 0
    while not stop_ev.is_set():
        try:
            try:
                downstream_req = rep.recv()
            except _zmq.Again:
                continue

            req.send(downstream_req)

            while not stop_ev.is_set():
                try:
                    raw = req.recv()
                    break
                except _zmq.Again:
                    continue
            if stop_ev.is_set():
                break

            iq = np.frombuffer(raw, dtype=np.complex64).copy()

            # ── Impairment chain ──
            # 1) Burst drop (zero entire subframe)
            if imp['drop_prob'][0] > 0.0 and rng.random() < imp['drop_prob'][0]:
                iq = np.zeros_like(iq)
                drops += 1
            else:
                fader = imp['fading'][0]
                # 2) Fading (flat or frequency-selective)
                iq = fader.update_and_apply(iq)
                # 3) CFO (cumulative phase rotation)
                iq = apply_cfo(iq, imp['cfo_hz'][0],
                               fader.samp_rate, imp['cfo_phase'])
                # 4) AWGN — skip when using freq-selective fading (ISI
                #    already provides sufficient impairment, and noise gen
                #    would exceed the real-time processing budget)
                if not isinstance(fader, FrequencySelectiveFading):
                    iq = add_awgn(iq, imp['snr_linear'][0], rng)

            rep.send(iq.tobytes())

            count += 1
            if label == "DL" and viz_buf is not None:
                viz_buf.append(iq)
            if count == 1:
                print(f"[GRC] {label}: first msg relayed ({len(iq)} samples)")
            msg_counter[0] = count

        except _zmq.ZMQError as e:
            if stop_ev.is_set():
                break
            print(f"[GRC] {label}: ZMQ error: {e}")
            break

    req.close()
    rep.close()
    ctx.term()
    drop_str = f" ({100*drops/count:.1f}% dropped)" if count > 0 and drops > 0 else ""
    print(f"[GRC] {label}: exiting (relayed {count} msgs{drop_str})")


# ── Embedded Python Block: ZMQ Broker Source ────────────────────────────────

class channel_broker_source(gr.sync_block):
    """ZMQ Channel Broker — relays IQ with impairments, outputs DL for viz."""

    def __init__(self, snr_db=28.0, k_factor_db=3.0, doppler_hz=5.0,
                 fading_mode=1, samp_rate=23.04e6, cfo_hz=0.0, drop_prob=0.0,
                 gnb_tx_port=4000, gnb_rx_port=4001,
                 ue_rx_port=2000, ue_tx_port=2001):
        gr.sync_block.__init__(self, name="srsRAN ZMQ Channel Broker",
                               in_sig=[], out_sig=[np.complex64])
        self.samp_rate = samp_rate
        self.snr_db = snr_db
        self.k_factor_db = k_factor_db
        self.doppler_hz = doppler_hz
        self.fading_mode = fading_mode
        self.gnb_tx_port = gnb_tx_port
        self.gnb_rx_port = gnb_rx_port
        self.ue_rx_port = ue_rx_port
        self.ue_tx_port = ue_tx_port
        self._stop = threading.Event()
        self._viz_buf = collections.deque(maxlen=4)
        self._dl_rng = np.random.default_rng(42)
        self._ul_rng = np.random.default_rng(137)
        self._dl_msg_count = [0]
        self._ul_msg_count = [0]

        snr_lin = pow(10.0, snr_db / 10.0)
        self._dl_imp = self._make_impairments(
            snr_lin, fading_mode, doppler_hz, k_factor_db, cfo_hz, drop_prob, self._dl_rng)
        # UL: Rician flat fading (no FIR) to stay within real-time budget
        # and avoid deep fades that kill PUCCH decoding
        ul_mode = min(fading_mode, 1) if fading_mode >= 3 else fading_mode
        self._ul_imp = self._make_impairments(
            snr_lin, ul_mode, doppler_hz, k_factor_db, 0.0, 0.0, self._ul_rng)

    def _make_fading(self, mode, rng):
        if mode in FADING_MODE_PROFILES:
            return FrequencySelectiveFading(
                FADING_MODE_PROFILES[mode], self.samp_rate, self.doppler_hz, rng)
        elif mode == 2:
            return FadingState(True, self.doppler_hz, self.samp_rate, -100.0, rng)
        elif mode == 1:
            return FadingState(True, self.doppler_hz, self.samp_rate,
                               self.k_factor_db, rng)
        else:
            return FadingState(False, self.doppler_hz, self.samp_rate,
                               self.k_factor_db, rng)

    def _make_impairments(self, snr_linear, mode, doppler, k_db, cfo, drop, rng):
        fading = self._make_fading(mode, rng)
        return {
            'snr_linear': [snr_linear],
            'fading':    [fading],
            'cfo_hz':    [cfo],
            'cfo_phase': [0.0],
            'drop_prob': [drop],
        }

    def start(self):
        self._stop.clear()
        addr = "127.0.0.1"
        self._dl_thread = threading.Thread(
            target=relay_thread,
            args=("DL",
                  f"tcp://{addr}:{self.gnb_tx_port}",
                  f"tcp://0.0.0.0:{self.ue_rx_port}",
                  self._dl_imp, self._dl_rng, self._stop, self._viz_buf,
                  self._dl_msg_count),
            daemon=True)
        self._ul_thread = threading.Thread(
            target=relay_thread,
            args=("UL",
                  f"tcp://{addr}:{self.ue_tx_port}",
                  f"tcp://0.0.0.0:{self.gnb_rx_port}",
                  self._ul_imp, self._ul_rng, self._stop, None,
                  self._ul_msg_count),
            daemon=True)
        self._dl_thread.start()
        self._ul_thread.start()
        print("[GRC] Relay threads started")
        return True

    def stop(self):
        self._stop.set()
        print("[GRC] Stopping relay threads...")
        return True

    def work(self, input_items, output_items):
        out = output_items[0]
        n = len(out)
        if self._viz_buf:
            iq = self._viz_buf[-1]
            use = min(n, len(iq))
            out[:use] = iq[:use]
            if use < n:
                out[use:] = 0
        else:
            out[:] = 0
        return n

    # ── Callbacks for GUI / scenario parameter changes ──

    def set_snr_db(self, val):
        self.snr_db = val
        snr_lin = pow(10.0, val / 10.0)
        self._dl_imp['snr_linear'][0] = snr_lin
        self._ul_imp['snr_linear'][0] = snr_lin

    def set_k_factor_db(self, val):
        self.k_factor_db = val
        if self.fading_mode <= 2:
            k = -100.0 if self.fading_mode == 2 else val
            self._dl_imp['fading'][0].reconfigure(
                self.fading_mode >= 1, self.doppler_hz, k)
            self._ul_imp['fading'][0].reconfigure(
                self.fading_mode >= 1, self.doppler_hz, k)

    def set_doppler_hz(self, val):
        self.doppler_hz = val
        if self.fading_mode <= 2:
            k = -100.0 if self.fading_mode == 2 else self.k_factor_db
            self._dl_imp['fading'][0].reconfigure(
                self.fading_mode >= 1, val, k)
            self._ul_imp['fading'][0].reconfigure(
                self.fading_mode >= 1, val, k)
        else:
            self._dl_imp['fading'][0].reconfigure(True, val)
            self._ul_imp['fading'][0].reconfigure(True, val)

    def set_fading_mode(self, val):
        self.fading_mode = val
        self._dl_imp['fading'][0] = self._make_fading(val, self._dl_rng)
        self._ul_imp['fading'][0] = self._make_fading(val, self._ul_rng)

    def set_cfo_hz(self, val):
        self._dl_imp['cfo_hz'][0] = val
        self._ul_imp['cfo_hz'][0] = val

    def set_drop_prob(self, val):
        self._dl_imp['drop_prob'][0] = val
        self._ul_imp['drop_prob'][0] = val


# ── QT GUI Flow Graph ──────────────────────────────────────────────────────

class srsran_channel_broker(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "srsRAN 5G NR Channel Broker",
                              catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("srsRAN 5G NR Channel Broker")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme("gnuradio-grc"))
        except:
            pass
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "srsran_channel_broker")
        try:
            self.restoreGeometry(self.settings.value("geometry"))
        except:
            pass

        # ── Variables ─────────────────────────────────────────────────────
        self.samp_rate = samp_rate = 23.04e6
        self.snr_db = snr_db = 28.0
        self.k_factor_db = k_factor_db = 3.0
        self.doppler_hz = doppler_hz = 5.0
        self.fading_mode = fading_mode = 1
        self.cfo_hz = cfo_hz = 0.0
        self.drop_prob = drop_prob = 0.0
        self.scenario_id = 0

        # ── Row 0: SNR slider + K-factor slider ──────────────────────────
        self._snr_db_range = qtgui.Range(5, 40, 0.5, snr_db, 200)
        self._snr_db_win = qtgui.RangeWidget(self._snr_db_range,
            self.set_snr_db, "SNR (dB)", "counter_slider", float,
            QtCore.Qt.Horizontal)
        self.top_grid_layout.addWidget(self._snr_db_win, 0, 0, 1, 2)

        self._k_factor_db_range = qtgui.Range(-10, 20, 0.5, k_factor_db, 200)
        self._k_factor_db_win = qtgui.RangeWidget(self._k_factor_db_range,
            self.set_k_factor_db, "K-Factor (dB)", "counter_slider", float,
            QtCore.Qt.Horizontal)
        self.top_grid_layout.addWidget(self._k_factor_db_win, 0, 2, 1, 2)

        # ── Row 1: Doppler slider + Fading mode dropdown ─────────────────
        self._doppler_hz_range = qtgui.Range(0.1, 300, 1, doppler_hz, 200)
        self._doppler_hz_win = qtgui.RangeWidget(self._doppler_hz_range,
            self.set_doppler_hz, "Doppler (Hz)", "counter_slider", float,
            QtCore.Qt.Horizontal)
        self.top_grid_layout.addWidget(self._doppler_hz_win, 1, 0, 1, 2)

        self._fading_combo = Qt.QComboBox()
        for k in sorted(FADING_MODES.keys()):
            self._fading_combo.addItem(FADING_MODES[k], k)
        self._fading_combo.setCurrentIndex(fading_mode)
        self._fading_combo.currentIndexChanged.connect(
            lambda idx: self.set_fading_mode(self._fading_combo.itemData(idx)))
        fading_group = Qt.QGroupBox("Fading Mode:")
        fading_lay = Qt.QHBoxLayout()
        fading_lay.addWidget(self._fading_combo)
        fading_group.setLayout(fading_lay)
        self.top_grid_layout.addWidget(fading_group, 1, 2, 1, 2)

        # ── Row 2: CFO slider + Drop prob slider + Scenario dropdown ─────
        self._cfo_hz_range = qtgui.Range(-500, 500, 1.0, cfo_hz, 200)
        self._cfo_hz_win = qtgui.RangeWidget(self._cfo_hz_range,
            self.set_cfo_hz, "CFO (Hz)", "counter_slider", float,
            QtCore.Qt.Horizontal)
        self.top_grid_layout.addWidget(self._cfo_hz_win, 2, 0, 1, 1)

        self._drop_range = qtgui.Range(0, 0.25, 0.01, drop_prob, 200)
        self._drop_win = qtgui.RangeWidget(self._drop_range,
            self.set_drop_prob, "Drop Prob", "counter_slider", float,
            QtCore.Qt.Horizontal)
        self.top_grid_layout.addWidget(self._drop_win, 2, 1, 1, 1)

        self._scenario_combo = Qt.QComboBox()
        for k in sorted(SCENARIO_NAMES.keys()):
            self._scenario_combo.addItem(SCENARIO_NAMES[k], k)
        self._scenario_combo.currentIndexChanged.connect(
            lambda idx: self.set_scenario(self._scenario_combo.itemData(idx)))
        scenario_group = Qt.QGroupBox("Scenario:")
        scenario_lay = Qt.QHBoxLayout()
        scenario_lay.addWidget(self._scenario_combo)
        scenario_group.setLayout(scenario_lay)
        self.top_grid_layout.addWidget(scenario_group, 2, 2, 1, 2)

        # ── Blocks ────────────────────────────────────────────────────────
        self.epy_block_broker = channel_broker_source(
            snr_db=snr_db, k_factor_db=k_factor_db, doppler_hz=doppler_hz,
            fading_mode=fading_mode, samp_rate=samp_rate,
            cfo_hz=cfo_hz, drop_prob=drop_prob)

        self.blocks_throttle_0 = blocks.throttle(
            gr.sizeof_gr_complex, samp_rate, True)

        # Frequency Sink
        self.qtgui_freq_sink_0 = qtgui.freq_sink_c(
            2048, window.WIN_BLACKMAN_hARRIS, 0, samp_rate,
            "DL Channel Spectrum", 1)
        self.qtgui_freq_sink_0.set_update_time(0.10)
        self.qtgui_freq_sink_0.set_y_axis(-80, 10)
        self.qtgui_freq_sink_0.set_y_label("Relative Gain", "dB")
        self.qtgui_freq_sink_0.set_trigger_mode(
            qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_0.enable_autoscale(False)
        self.qtgui_freq_sink_0.enable_grid(True)
        self.qtgui_freq_sink_0.set_fft_average(1.0)
        self.qtgui_freq_sink_0.enable_control_panel(False)
        self.qtgui_freq_sink_0.set_line_label(0, "DL IQ Spectrum")
        self.qtgui_freq_sink_0.set_line_width(0, 2)
        self.qtgui_freq_sink_0.set_line_color(0, "blue")
        self._qtgui_freq_sink_0_win = sip.wrapinstance(
            self.qtgui_freq_sink_0.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(
            self._qtgui_freq_sink_0_win, 3, 0, 2, 2)

        # Time Sink
        self.qtgui_time_sink_0 = qtgui.time_sink_c(
            2048, samp_rate, "DL IQ Waveform", 1, None)
        self.qtgui_time_sink_0.set_update_time(0.10)
        self.qtgui_time_sink_0.set_y_axis(-1, 1)
        self.qtgui_time_sink_0.set_y_label("Amplitude", "")
        self.qtgui_time_sink_0.enable_tags(True)
        self.qtgui_time_sink_0.set_trigger_mode(
            qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_0.enable_autoscale(True)
        self.qtgui_time_sink_0.enable_grid(True)
        self.qtgui_time_sink_0.set_line_label(0, "I")
        self.qtgui_time_sink_0.set_line_label(1, "Q")
        self.qtgui_time_sink_0.set_line_color(0, "blue")
        self.qtgui_time_sink_0.set_line_color(1, "red")
        self._qtgui_time_sink_0_win = sip.wrapinstance(
            self.qtgui_time_sink_0.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(
            self._qtgui_time_sink_0_win, 3, 2, 2, 2)

        # Constellation Sink
        self.qtgui_const_sink_0 = qtgui.const_sink_c(
            2048, "DL Constellation", 1, None)
        self.qtgui_const_sink_0.set_update_time(0.10)
        self.qtgui_const_sink_0.set_y_axis(-2, 2)
        self.qtgui_const_sink_0.set_x_axis(-2, 2)
        self.qtgui_const_sink_0.set_trigger_mode(
            qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, "")
        self.qtgui_const_sink_0.enable_autoscale(True)
        self.qtgui_const_sink_0.enable_grid(True)
        self.qtgui_const_sink_0.set_line_label(0, "DL IQ")
        self.qtgui_const_sink_0.set_line_color(0, "blue")
        self.qtgui_const_sink_0.set_line_style(0, 0)
        self.qtgui_const_sink_0.set_line_marker(0, 0)
        self._qtgui_const_sink_0_win = sip.wrapinstance(
            self.qtgui_const_sink_0.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(
            self._qtgui_const_sink_0_win, 5, 0, 2, 2)

        # Waterfall Sink
        self.qtgui_waterfall_sink_0 = qtgui.waterfall_sink_c(
            2048, window.WIN_BLACKMAN_hARRIS, 0, samp_rate,
            "DL Waterfall", 1)
        self.qtgui_waterfall_sink_0.set_update_time(0.10)
        self.qtgui_waterfall_sink_0.enable_grid(True)
        self.qtgui_waterfall_sink_0.enable_axis_labels(True)
        self.qtgui_waterfall_sink_0.set_intensity_range(-80, 10)
        self._qtgui_waterfall_sink_0_win = sip.wrapinstance(
            self.qtgui_waterfall_sink_0.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(
            self._qtgui_waterfall_sink_0_win, 5, 2, 2, 2)

        # ── Connections ───────────────────────────────────────────────────
        self.connect((self.epy_block_broker, 0), (self.blocks_throttle_0, 0))
        self.connect((self.blocks_throttle_0, 0), (self.qtgui_freq_sink_0, 0))
        self.connect((self.blocks_throttle_0, 0), (self.qtgui_time_sink_0, 0))
        self.connect((self.blocks_throttle_0, 0), (self.qtgui_const_sink_0, 0))
        self.connect(
            (self.blocks_throttle_0, 0), (self.qtgui_waterfall_sink_0, 0))

        # ── Scenario timer (1s tick) ──────────────────────────────────────
        self._scenario = ScenarioRunner()
        self._scenario_timer = Qt.QTimer()
        self._scenario_timer.timeout.connect(self._scenario_tick)
        self._scenario_timer.start(1000)

    def _scenario_tick(self):
        updates = self._scenario.tick()
        if updates is None:
            return
        if 'snr_db' in updates:
            self.epy_block_broker.set_snr_db(updates['snr_db'])
        if 'doppler_hz' in updates:
            self.epy_block_broker.set_doppler_hz(updates['doppler_hz'])
        if 'drop_prob' in updates:
            self.epy_block_broker.set_drop_prob(updates['drop_prob'])

    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "srsran_channel_broker")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()
        event.accept()

    def set_snr_db(self, snr_db):
        self.snr_db = snr_db
        self.epy_block_broker.set_snr_db(snr_db)

    def set_k_factor_db(self, k_factor_db):
        self.k_factor_db = k_factor_db
        self.epy_block_broker.set_k_factor_db(k_factor_db)

    def set_doppler_hz(self, doppler_hz):
        self.doppler_hz = doppler_hz
        self.epy_block_broker.set_doppler_hz(doppler_hz)

    def set_fading_mode(self, mode):
        self.fading_mode = mode
        self.epy_block_broker.set_fading_mode(mode)

    def set_cfo_hz(self, val):
        self.cfo_hz = val
        self.epy_block_broker.set_cfo_hz(val)

    def set_drop_prob(self, val):
        self.drop_prob = val
        self.epy_block_broker.set_drop_prob(val)

    def set_scenario(self, idx):
        self.scenario_id = idx
        self._scenario.set_scenario(idx)


# ── Headless mode (no QT GUI — for launch script) ───────────────────────────

class srsran_channel_broker_headless(gr.top_block):
    """Runs the broker without QT GUI."""

    def __init__(self, snr_db=28.0, k_factor_db=3.0, doppler_hz=5.0,
                 fading_mode=1, samp_rate=23.04e6,
                 cfo_hz=0.0, drop_prob=0.0):
        gr.top_block.__init__(self, "srsRAN Channel Broker (headless)",
                              catch_exceptions=True)
        self.broker = channel_broker_source(
            snr_db=snr_db, k_factor_db=k_factor_db, doppler_hz=doppler_hz,
            fading_mode=fading_mode, samp_rate=samp_rate,
            cfo_hz=cfo_hz, drop_prob=drop_prob)
        self.null_sink = blocks.null_sink(gr.sizeof_gr_complex)
        self.throttle = blocks.throttle(gr.sizeof_gr_complex, samp_rate, True)
        self.connect((self.broker, 0), (self.throttle, 0))
        self.connect((self.throttle, 0), (self.null_sink, 0))


# ── Main ─────────────────────────────────────────────────────────────────────

def main(top_block_cls=srsran_channel_broker, options=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="srsRAN 5G NR Channel Broker (GNU Radio)")
    parser.add_argument("--snr", type=float, default=28.0,
                        help="SNR in dB (default: 28)")
    parser.add_argument("--k-factor", type=float, default=3.0,
                        help="Rician K-factor dB (default: 3)")
    parser.add_argument("--doppler", type=float, default=None,
                        help="Max Doppler Hz (default: auto from profile)")
    parser.add_argument("--fading", action="store_true",
                        help="Enable flat Rician fading")
    parser.add_argument("--rayleigh", action="store_true",
                        help="Enable flat Rayleigh fading")
    parser.add_argument("--profile", type=str, default="flat",
                        choices=["flat", "epa", "eva", "etu"],
                        help="Delay profile (epa/eva/etu = freq-selective)")
    parser.add_argument("--cfo", type=float, default=0.0,
                        help="Carrier freq offset Hz (default: 0)")
    parser.add_argument("--drop-prob", type=float, default=0.0,
                        help="Burst drop probability 0-1 (default: 0)")
    parser.add_argument("--scenario", type=str, default="none",
                        choices=["none", "drive-by", "urban-walk",
                                 "edge-of-cell"],
                        help="Time-varying scenario (default: none)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Run headless (no QT GUI)")
    parser.add_argument("--samp-rate", type=float, default=23.04e6)
    # Compat flags (accepted, ignored)
    parser.add_argument("--dl-snr", type=float, default=None)
    parser.add_argument("--ul-snr", type=float, default=None)
    args = parser.parse_args()

    # Resolve fading mode
    if args.profile in ('epa', 'eva', 'etu'):
        fading_mode = {'epa': 3, 'eva': 4, 'etu': 5}[args.profile]
        if args.doppler is None:
            args.doppler = DELAY_PROFILES[args.profile]['default_doppler']
    elif args.rayleigh:
        fading_mode = 2
    elif args.fading:
        fading_mode = 1
    else:
        fading_mode = 0

    if args.doppler is None:
        args.doppler = 5.0

    scenario_id = {
        "none": 0, "drive-by": 1, "urban-walk": 2, "edge-of-cell": 3
    }[args.scenario]

    # Print banner
    print("=" * 65)
    print("  srsRAN 5G NR Channel Broker (GNU Radio Companion)")
    print("=" * 65)
    print(f"  Fading:    {FADING_MODES[fading_mode]}")
    if fading_mode >= 1:
        print(f"  Doppler:   {args.doppler} Hz")
    if fading_mode == 1:
        print(f"  K-factor:  {args.k_factor} dB")
    if fading_mode >= 3:
        prof = DELAY_PROFILES[FADING_MODE_PROFILES[fading_mode]]
        print(f"  Taps:      {len(prof['delays_ns'])}, "
              f"max delay {prof['delays_ns'][-1]} ns")
    snr_lin = pow(10.0, args.snr / 10.0)
    print(f"  SNR:       {args.snr} dB  (adaptive noise, snr_linear={snr_lin:.1f})")
    if abs(args.cfo) > 0.01:
        print(f"  CFO:       {args.cfo} Hz")
    if args.drop_prob > 0:
        print(f"  Drop:      {args.drop_prob*100:.1f}%")
    if scenario_id > 0:
        print(f"  Scenario:  {SCENARIO_NAMES[scenario_id]}")
    gui_label = "headless" if args.no_gui else "QT GUI"
    print(f"  Interface: {gui_label}")
    print("-" * 65)
    # List capabilities beyond C broker
    extras = []
    if fading_mode >= 3:
        extras.append(f"freq-selective fading ({args.profile.upper()})")
    if abs(args.cfo) > 0.01:
        extras.append(f"CFO {args.cfo} Hz")
    if args.drop_prob > 0:
        extras.append(f"burst drops {args.drop_prob*100:.0f}%")
    if scenario_id > 0:
        extras.append(f"scenario: {SCENARIO_NAMES[scenario_id]}")
    if not args.no_gui:
        extras.append("live GUI control")
    if extras:
        print(f"  Beyond C broker: {', '.join(extras)}")
    print(f"  DL: gNB:4000 -> broker -> :2000 UE")
    print(f"  UL: UE:2001  -> broker -> :4001 gNB")
    print("=" * 65)

    if args.no_gui:
        tb = srsran_channel_broker_headless(
            snr_db=args.snr, k_factor_db=args.k_factor,
            doppler_hz=args.doppler, fading_mode=fading_mode,
            cfo_hz=args.cfo, drop_prob=args.drop_prob)
        tb.start()

        # Scenario runner in background thread
        scenario = ScenarioRunner()
        scenario.set_scenario(scenario_id)
        scenario_stop = threading.Event()

        def scenario_loop():
            while not scenario_stop.is_set():
                updates = scenario.tick()
                if updates:
                    if 'snr_db' in updates:
                        tb.broker.set_snr_db(updates['snr_db'])
                    if 'doppler_hz' in updates:
                        tb.broker.set_doppler_hz(updates['doppler_hz'])
                    if 'drop_prob' in updates:
                        tb.broker.set_drop_prob(updates['drop_prob'])
                scenario_stop.wait(1.0)

        if scenario_id > 0:
            st = threading.Thread(target=scenario_loop, daemon=True)
            st.start()

        def sig_handler(sig, frame):
            print("\n[GRC] Signal caught, stopping...")
            scenario_stop.set()
            tb.stop()
            tb.wait()
            sys.exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        print("[GRC] Broker running (headless). Ctrl+C to stop.")
        try:
            tb.wait()
        except KeyboardInterrupt:
            pass
        scenario_stop.set()
        tb.stop()
        tb.wait()
        print("[GRC] Broker stopped.")

    else:
        # QT GUI mode
        if (StrictVersion("4.5.0") <= StrictVersion(Qt.qVersion())
                < StrictVersion("5.0.0")):
            style = gr.prefs().get_string("qtgui", "style", "raster")
            Qt.QApplication.setGraphicsSystem(style)

        qapp = Qt.QApplication(sys.argv)

        tb = top_block_cls()
        tb.set_snr_db(args.snr)
        tb.set_k_factor_db(args.k_factor)
        tb.set_doppler_hz(args.doppler)
        tb.set_fading_mode(fading_mode)
        tb.set_cfo_hz(args.cfo)
        tb.set_drop_prob(args.drop_prob)
        tb.set_scenario(scenario_id)

        tb.start()
        tb.show()

        def sig_handler(sig=None, frame=None):
            tb.stop()
            tb.wait()
            Qt.QApplication.quit()

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        timer = Qt.QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)

        qapp.aboutToQuit.connect(tb.stop)
        qapp.exec_()


if __name__ == "__main__":
    main()
