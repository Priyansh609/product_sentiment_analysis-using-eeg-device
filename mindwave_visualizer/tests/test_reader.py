"""
Tests for EEG Reader
======================
Covers port enumeration and reader construction (no real serial device needed).
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from eeg_reader import EEGReader


class TestEEGReader:

    def test_available_ports_returns_list(self):
        """available_ports() should return a list (possibly empty)."""
        ports = EEGReader.available_ports()
        assert isinstance(ports, list)

    def test_available_ports_detailed(self):
        """available_ports_detailed() returns list of dicts."""
        ports = EEGReader.available_ports_detailed()
        assert isinstance(ports, list)
        for p in ports:
            assert "device" in p
            assert "description" in p

    def test_reader_initial_state(self):
        """Reader starts in disconnected state."""
        reader = EEGReader()
        assert reader._connected is False
        assert reader._running is False

    def test_change_port(self):
        """change_port updates the internal port."""
        reader = EEGReader()
        reader.change_port("COM5")
        assert reader._port == "COM5"

    @patch("eeg_reader.serial.Serial")
    def test_connect_emits_signal(self, mock_serial_class):
        """Verify that successful connection emits the right signal."""
        mock_serial_class.return_value = MagicMock()

        reader = EEGReader()
        signals = []
        reader.connection_changed.connect(lambda c, p: signals.append((c, p)))

        # Directly test _try_connect
        reader._try_connect()
        assert reader._connected is True
        assert len(signals) == 1
        assert signals[0][0] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
