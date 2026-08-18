"""
Tests for CSV Recorder
========================
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv
import tempfile
import time

import pytest
from recorder import Recorder
from config import CSV_COLUMNS, NEURO_CSV_COLUMNS


class TestRecorder:

    def test_start_creates_file(self, tmp_path, monkeypatch):
        """Starting a recording should create a CSV file."""
        monkeypatch.setattr("recorder.RECORDING_DIR", str(tmp_path))

        rec = Recorder()
        rec.start()
        time.sleep(0.1)

        rec.start_recording()
        assert rec.is_recording is True
        assert rec.filepath is not None
        assert os.path.exists(rec.filepath)

        rec.stop_recording()
        rec.stop()

    def test_csv_columns(self, tmp_path, monkeypatch):
        """CSV header should match CSV_COLUMNS."""
        monkeypatch.setattr("recorder.RECORDING_DIR", str(tmp_path))

        rec = Recorder()
        rec.start()
        time.sleep(0.1)

        rec.start_recording()

        # Enqueue a row
        row = {col: 0 for col in CSV_COLUMNS}
        row["timestamp"] = "2025-01-01T00:00:00"
        rec.enqueue(row)
        time.sleep(0.2)  # let the writer drain

        path = rec.stop_recording()
        rec.stop()

        with open(path, "r") as f:
            reader = csv.DictReader(f)
            assert list(reader.fieldnames) == CSV_COLUMNS
            rows = list(reader)
            assert len(rows) >= 1

    def test_neuro_mode_columns(self, tmp_path, monkeypatch):
        """Neuro-mode CSV should have extra columns."""
        monkeypatch.setattr("recorder.RECORDING_DIR", str(tmp_path))

        rec = Recorder()
        rec.start()
        time.sleep(0.1)

        rec.start_recording(neuro_mode=True)
        path = rec.stop_recording()
        rec.stop()

        with open(path, "r") as f:
            reader = csv.DictReader(f)
            assert list(reader.fieldnames) == NEURO_CSV_COLUMNS

    def test_stop_without_start(self):
        """Stopping without starting should not crash."""
        rec = Recorder()
        rec.start()
        time.sleep(0.1)
        result = rec.stop_recording()
        assert result is None
        rec.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
