"""
MindWave Visualizer — CSV Recorder
====================================
Threaded writer that saves decoded EEG packets to timestamped CSV files
without blocking the UI.
"""

from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from queue import Queue, Empty
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from config import RECORDING_DIR, RECORDING_FLUSH_INTERVAL, CSV_COLUMNS, NEURO_CSV_COLUMNS
from logger import setup_logger

log = setup_logger("recorder")


class Recorder(QThread):
    """
    Consumer thread: drains a queue of data dicts and writes them to CSV.
    Supports both standard EEG recording and neuromarketing mode (with
    extra columns for product_name, engagement_score, label).
    """

    recording_started  = pyqtSignal(str)   # filepath
    recording_stopped  = pyqtSignal(str)   # filepath
    recording_error    = pyqtSignal(str)   # error message
    rows_written       = pyqtSignal(int)   # total row count
    duration_updated   = pyqtSignal(float) # seconds elapsed

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._queue: Queue = Queue(maxsize=50_000)
        self._running: bool = False
        self._recording: bool = False
        self._neuro_mode: bool = False

        self._filepath: Optional[str] = None
        self._file = None
        self._writer: Optional[csv.writer] = None
        self._row_count: int = 0
        self._start_time: float = 0.0

    # ── Public API (called from UI thread) ─────────────────────────────

    def start_recording(self, neuro_mode: bool = False) -> None:
        """Begin a new CSV recording session."""
        os.makedirs(RECORDING_DIR, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = "neuro" if neuro_mode else "eeg"
        self._filepath = os.path.join(RECORDING_DIR, f"{prefix}_{ts}.csv")
        self._neuro_mode = neuro_mode
        self._row_count = 0
        self._start_time = time.monotonic()

        try:
            columns = NEURO_CSV_COLUMNS if neuro_mode else CSV_COLUMNS
            self._file = open(self._filepath, "w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._file, fieldnames=columns, extrasaction="ignore")
            self._writer.writeheader()
            self._recording = True
            log.info("Recording started → %s", self._filepath)
            self.recording_started.emit(self._filepath)
        except OSError as exc:
            log.error("Failed to open recording file: %s", exc)
            self.recording_error.emit(str(exc))

    def stop_recording(self) -> str | None:
        """Stop recording and flush the file.  Returns the filepath."""
        self._recording = False
        self._flush_and_close()
        path = self._filepath
        if path:
            log.info("Recording stopped (%d rows) → %s", self._row_count, path)
            self.recording_stopped.emit(path)
        return path

    def enqueue(self, data: dict) -> None:
        """
        Thread-safe: push one data dict into the write queue.
        Non-blocking — drops data silently if the queue is full.
        """
        if self._recording:
            try:
                self._queue.put_nowait(data)
            except Exception:
                pass  # queue full — drop sample

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def filepath(self) -> Optional[str]:
        return self._filepath

    @property
    def elapsed(self) -> float:
        if self._start_time and self._recording:
            return time.monotonic() - self._start_time
        return 0.0

    def stop(self) -> None:
        """Stop the thread."""
        self._running = False
        self._recording = False
        self.wait(3000)

    # ── Thread entry ───────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        log.info("Recorder thread started")
        last_flush = time.monotonic()

        while self._running:
            # Drain all queued rows
            wrote = False
            try:
                while True:
                    data = self._queue.get_nowait()
                    if self._recording and self._writer is not None:
                        try:
                            self._writer.writerow(data)
                            self._row_count += 1
                            wrote = True
                        except Exception as exc:
                            log.error("Write error: %s", exc)
                            self.recording_error.emit(str(exc))
            except Empty:
                pass

            # Periodic flush
            now = time.monotonic()
            if wrote and (now - last_flush) >= RECORDING_FLUSH_INTERVAL:
                self._flush()
                last_flush = now
                self.rows_written.emit(self._row_count)

            # Emit duration
            if self._recording:
                self.duration_updated.emit(self.elapsed)

            self.msleep(50)

        self._flush_and_close()
        log.info("Recorder thread stopped")

    # ── Internal ───────────────────────────────────────────────────────

    def _flush(self) -> None:
        if self._file is not None:
            try:
                self._file.flush()
            except Exception:
                pass

    def _flush_and_close(self) -> None:
        self._flush()
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
            self._writer = None
