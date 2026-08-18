"""
MindWave Visualizer — EEG Simulator
=====================================
Generates synthetic EEG data that mirrors the real ThinkGear data format
so the entire dashboard can be tested without a physical headset.
"""

from __future__ import annotations

import math
import random
from datetime import datetime

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config import RAW_EEG_RATE, TARGET_FPS
from logger import setup_logger

log = setup_logger("simulator")


class EEGSimulator(QThread):
    """
    Drop-in replacement for :class:`EEGReader` that emits synthetic data.

    Signals are identical to ``EEGReader`` so the dashboard can switch
    between live and simulated modes without code changes.
    """

    data_received       = pyqtSignal(dict)
    raw_packet_received = pyqtSignal(bytes, dict)
    connection_changed  = pyqtSignal(bool, str)
    error_occurred      = pyqtSignal(str)
    stats_updated       = pyqtSignal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._t: float = 0.0                # continuous time counter
        self._packet_count: int = 0
        self._blink_counter: int = 0

        # Smoothed metric state (for realistic wandering values)
        self._attention: float = 50.0
        self._meditation: float = 50.0

    # ── Public API (mirrors EEGReader) ─────────────────────────────────

    def connect_device(self) -> None:
        if not self.isRunning():
            self.start()

    def disconnect_device(self) -> None:
        self.stop()

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def change_port(self, port: str) -> None:
        pass  # no-op in simulation

    @staticmethod
    def available_ports():
        return ["SIM"]

    @property
    def parser(self):
        """Minimal duck-type so the dashboard can read stats."""
        return _FakeParser(self._packet_count)

    # ── Thread entry ───────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        self.connection_changed.emit(True, "Simulator")
        log.info("Simulator started")

        samples_per_frame = RAW_EEG_RATE // TARGET_FPS  # ~25 samples per 50 ms
        metric_interval   = RAW_EEG_RATE                # every 512 raw samples
        sample_counter    = 0

        while self._running:
            for _ in range(samples_per_frame):
                data = {
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "raw_eeg":   self._raw_eeg(),
                    "signal_quality": 0,
                    "attention": 0,
                    "meditation": 0,
                    "blink_strength": 0,
                    "delta": 0, "theta": 0,
                    "low_alpha": 0, "high_alpha": 0,
                    "low_beta": 0, "high_beta": 0,
                    "low_gamma": 0, "high_gamma": 0,
                }

                sample_counter += 1

                # Emit eSense metrics once per second (like real hardware)
                if sample_counter >= metric_interval:
                    sample_counter = 0
                    data.update(self._metrics())

                self._packet_count += 1
                self.data_received.emit(data)
                self.raw_packet_received.emit(b"\xaa\xaa\x04\x80\x02\x00\x00\x00", data)

                self._t += 1.0 / RAW_EEG_RATE

            # Emit stats
            self.stats_updated.emit({
                "valid":   self._packet_count,
                "invalid": 0,
                "total_bytes": self._packet_count * 6,
            })

            self.msleep(1000 // TARGET_FPS)

        self.connection_changed.emit(False, "Simulator")
        log.info("Simulator stopped")

    # ── Signal generators ──────────────────────────────────────────────

    def _raw_eeg(self) -> int:
        """Composite waveform resembling real EEG."""
        t = self._t
        signal = (
            60.0 * math.sin(2 * math.pi * 1.5 * t)           # delta  ~1.5 Hz
            + 40.0 * math.sin(2 * math.pi * 5.5 * t)         # theta  ~5.5 Hz
            + 25.0 * math.sin(2 * math.pi * 10.0 * t)        # alpha ~10 Hz
            + 12.0 * math.sin(2 * math.pi * 20.0 * t)        # beta  ~20 Hz
            + 6.0  * math.sin(2 * math.pi * 42.0 * t)        # gamma ~42 Hz
            + random.gauss(0, 15)                             # noise
        )
        return int(max(-2048, min(2047, signal)))

    def _metrics(self) -> dict:
        """Generate slowly-wandering eSense values and band powers."""
        # Random-walk attention & meditation
        self._attention  += random.gauss(0, 4)
        self._meditation += random.gauss(0, 3)
        self._attention  = max(0, min(100, self._attention))
        self._meditation = max(0, min(100, self._meditation))

        # Occasional blink (≈10 % chance per second)
        blink = 0
        if random.random() < 0.10:
            blink = random.randint(40, 200)
            self._blink_counter += 1

        return {
            "attention":      int(round(self._attention)),
            "meditation":     int(round(self._meditation)),
            "signal_quality": 0,
            "blink_strength": blink,
            "delta":          random.randint(20_000, 600_000),
            "theta":          random.randint(15_000, 350_000),
            "low_alpha":      random.randint(5_000, 120_000),
            "high_alpha":     random.randint(5_000, 120_000),
            "low_beta":       random.randint(3_000, 60_000),
            "high_beta":      random.randint(3_000, 60_000),
            "low_gamma":      random.randint(1_000, 35_000),
            "high_gamma":     random.randint(500, 25_000),
        }


# ── Minimal duck-type for parser stats ─────────────────────────────────

class _FakeParser:
    def __init__(self, valid: int) -> None:
        self.valid_packets = valid
        self.invalid_packets = 0
        self.total_bytes = valid * 6
        self.last_raw_packet = b""

    def reset(self):
        pass
