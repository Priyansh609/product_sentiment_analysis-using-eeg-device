"""
MindWave Visualizer — EEG Serial Reader
=========================================
QThread that continuously reads from the NeuroSky MindWave Mobile over
Bluetooth SPP, feeds bytes into the ThinkGear parser, and emits decoded
data dictionaries via Qt signals.

Features
--------
* COM-port enumeration & hot-swap
* Auto-reconnect with exponential back-off
* Thread-safe connect / disconnect / change_port
"""

from __future__ import annotations

import time
from typing import List

import serial
import serial.tools.list_ports
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from config import (
    DEFAULT_PORT,
    DEFAULT_BAUD,
    SERIAL_TIMEOUT,
    MAX_RECONNECT_ATTEMPTS,
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
)
from packet_decoder import ThinkGearParser
from logger import setup_logger

log = setup_logger("reader")


class EEGReader(QThread):
    """
    Producer thread: reads serial bytes → feeds ThinkGear parser → emits
    decoded dicts on ``data_received``.
    """

    # ── Signals ────────────────────────────────────────────────────────
    data_received      = pyqtSignal(dict)          # decoded EEG packet
    raw_packet_received = pyqtSignal(bytes, dict)  # (raw_bytes, decoded) for inspector
    connection_changed = pyqtSignal(bool, str)     # (connected?, port_name)
    error_occurred     = pyqtSignal(str)           # human-readable error
    stats_updated      = pyqtSignal(dict)          # parser statistics

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._port: str  = DEFAULT_PORT
        self._baud: int  = DEFAULT_BAUD
        self._serial: serial.Serial | None = None
        self._parser = ThinkGearParser()

        self._running: bool = False
        self._connected: bool = False
        self._should_connect: bool = False
        self._should_disconnect: bool = False

        self._reconnect_attempts: int = 0
        self._auto_reconnect: bool = True

        self._mutex = QMutex()
        self._stats_counter: int = 0

    # ── Public API (called from UI thread) ─────────────────────────────

    @staticmethod
    def available_ports() -> List[str]:
        """Return list of available COM port names."""
        return [p.device for p in serial.tools.list_ports.comports()]

    @staticmethod
    def available_ports_detailed() -> List[dict]:
        """Return detailed info for each COM port."""
        result = []
        for p in serial.tools.list_ports.comports():
            result.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
            })
        return result

    def connect_device(self) -> None:
        """Request the reader thread to open the serial port."""
        with QMutexLocker(self._mutex):
            self._should_connect = True
            self._should_disconnect = False
            self._auto_reconnect = True

    def disconnect_device(self) -> None:
        """Request the reader thread to close the serial port."""
        with QMutexLocker(self._mutex):
            self._should_disconnect = True
            self._should_connect = False
            self._auto_reconnect = False

    def change_port(self, port: str) -> None:
        """Switch to a different COM port (will reconnect automatically)."""
        with QMutexLocker(self._mutex):
            needs_reconnect = self._connected
            self._port = port

        if needs_reconnect:
            self.disconnect_device()
            # Small delay so the disconnect is processed
            QThread.msleep(200)
            self.connect_device()

    def stop(self) -> None:
        """Signal the thread to exit."""
        self._running = False
        self._auto_reconnect = False
        self.wait(3000)

    @property
    def parser(self) -> ThinkGearParser:
        return self._parser

    # ── Thread entry point ─────────────────────────────────────────────

    def run(self) -> None:  # noqa: C901 — intentionally linear state machine
        self._running = True
        log.info("EEG reader thread started")

        while self._running:
            # ── Handle connect / disconnect requests ───────────────
            with QMutexLocker(self._mutex):
                want_connect    = self._should_connect
                want_disconnect = self._should_disconnect
                self._should_connect    = False
                self._should_disconnect = False

            if want_disconnect:
                self._close_serial()

            if want_connect and not self._connected:
                self._try_connect()

            # ── Read bytes ─────────────────────────────────────────
            if self._connected and self._serial is not None:
                try:
                    data = self._serial.read(64)  # read up to 64 bytes at a time
                    if data:
                        for byte_val in data:
                            result = self._parser.feed(byte_val)
                            if result is not None:
                                self.data_received.emit(result)
                                self.raw_packet_received.emit(
                                    self._parser.last_raw_packet, result,
                                )

                        # Emit stats periodically (~every 500 bytes)
                        self._stats_counter += len(data)
                        if self._stats_counter >= 500:
                            self._stats_counter = 0
                            self.stats_updated.emit({
                                "valid":   self._parser.valid_packets,
                                "invalid": self._parser.invalid_packets,
                                "total_bytes": self._parser.total_bytes,
                            })
                except serial.SerialException as exc:
                    log.error("Serial read error: %s", exc)
                    self._handle_disconnect(str(exc))
                except OSError as exc:
                    log.error("OS error during read: %s", exc)
                    self._handle_disconnect(str(exc))
            else:
                # Not connected — sleep to avoid busy loop
                self.msleep(100)

        # Clean up on exit
        self._close_serial()
        log.info("EEG reader thread stopped")

    # ── Internal helpers ───────────────────────────────────────────────

    def _try_connect(self) -> None:
        """Attempt to open the serial port."""
        port = self._port
        try:
            log.info("Connecting to %s @ %d baud …", port, self._baud)
            self._serial = serial.Serial(
                port=port,
                baudrate=self._baud,
                timeout=SERIAL_TIMEOUT,
            )
            self._connected = True
            self._reconnect_attempts = 0
            self._parser.reset()
            log.info("Connected to %s", port)
            self.connection_changed.emit(True, port)
        except (serial.SerialException, OSError) as exc:
            log.warning("Connection failed on %s: %s", port, exc)
            self._connected = False
            self.error_occurred.emit(f"Cannot open {port}: {exc}")
            self.connection_changed.emit(False, port)

            # Auto-reconnect with exponential back-off
            if self._auto_reconnect and self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                delay = min(
                    INITIAL_RECONNECT_DELAY * (2 ** self._reconnect_attempts),
                    MAX_RECONNECT_DELAY,
                )
                self._reconnect_attempts += 1
                log.info(
                    "Reconnect attempt %d/%d in %.1f s …",
                    self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS, delay,
                )
                self.error_occurred.emit(
                    f"Reconnecting in {delay:.0f}s "
                    f"(attempt {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})"
                )
                # Sleep in small increments so we can respond to stop()
                end_time = time.monotonic() + delay
                while time.monotonic() < end_time and self._running:
                    self.msleep(200)
                if self._running:
                    with QMutexLocker(self._mutex):
                        self._should_connect = True

    def _handle_disconnect(self, error_msg: str) -> None:
        """Handle an unexpected disconnection."""
        self._close_serial()
        self.error_occurred.emit(f"Disconnected: {error_msg}")

        if self._auto_reconnect and self._running:
            with QMutexLocker(self._mutex):
                self._should_connect = True

    def _close_serial(self) -> None:
        """Close the serial port safely."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

        was_connected = self._connected
        self._connected = False
        if was_connected:
            log.info("Serial port closed")
            self.connection_changed.emit(False, self._port)
