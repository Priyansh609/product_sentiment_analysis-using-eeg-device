"""
MindWave Visualizer — ThinkGear Packet Decoder
================================================
State-machine implementation of the NeuroSky ThinkGear Serial Stream Protocol.

Packet structure
~~~~~~~~~~~~~~~~
    [SYNC] [SYNC] [PLENGTH] [PAYLOAD…] [CHECKSUM]

    SYNC      = 0xAA  (two consecutive bytes)
    PLENGTH   = payload length (1 byte, must be < 0xAA)
    PAYLOAD   = sequence of <code, value> rows
    CHECKSUM  = (~sum_of_payload_bytes) & 0xFF

Payload row codes
~~~~~~~~~~~~~~~~~
    Single-byte value codes (code < 0x80):
        0x02  Poor Signal Quality   (0 = good, 200 = no contact)
        0x04  Attention eSense      (0 – 100)
        0x05  Meditation eSense     (0 – 100)
        0x16  Blink Strength        (1 – 255)

    Multi-byte value codes (code >= 0x80, followed by length byte):
        0x80  Raw Wave Value        (2 bytes, big-endian signed int16)
        0x83  ASIC EEG Power        (24 bytes, 8 × 3-byte unsigned ints)
              Order: delta, theta, low_alpha, high_alpha,
                     low_beta, high_beta, low_gamma, high_gamma
"""

from __future__ import annotations

import struct
from datetime import datetime
from typing import Optional

from config import (
    SYNC_BYTE,
    MAX_PAYLOAD_LENGTH,
    CODE_POOR_SIGNAL,
    CODE_ATTENTION,
    CODE_MEDITATION,
    CODE_BLINK,
    CODE_RAW_WAVE,
    CODE_ASIC_EEG_POWER,
)
from logger import setup_logger

log = setup_logger("decoder")


# ═══════════════════════════════════════════════════════════════════════════
#  Data template
# ═══════════════════════════════════════════════════════════════════════════

def empty_packet() -> dict:
    """Return a data dict with every field set to its neutral default."""
    return {
        "timestamp":       "",
        "raw_eeg":         0,
        "attention":       0,
        "meditation":      0,
        "signal_quality":  200,   # 200 = no contact
        "blink_strength":  0,
        "delta":           0,
        "theta":           0,
        "low_alpha":       0,
        "high_alpha":      0,
        "low_beta":        0,
        "high_beta":       0,
        "low_gamma":       0,
        "high_gamma":      0,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  ThinkGear State-Machine Parser
# ═══════════════════════════════════════════════════════════════════════════

class ThinkGearParser:
    """
    Feed individual bytes via :meth:`feed`.  Each time a valid packet is
    fully received and passes checksum validation, :meth:`feed` returns a
    decoded ``dict``.  Otherwise it returns ``None``.

    Corrupted or truncated packets are silently dropped (with a log warning)
    and the parser re-synchronises automatically.
    """

    # Parser states
    _SYNC1      = 0
    _SYNC2      = 1
    _PLENGTH    = 2
    _PAYLOAD    = 3
    _CHECKSUM   = 4

    def __init__(self) -> None:
        self._state: int = self._SYNC1
        self._plength: int = 0
        self._payload: bytearray = bytearray()
        self._payload_sum: int = 0

        # Running statistics
        self.valid_packets: int = 0
        self.invalid_packets: int = 0
        self.total_bytes: int = 0

        # Last signal quality state (200 = no contact, 0 = good)
        self.last_signal_quality: int = 200

        # Last raw packet bytes (for the inspector panel)
        self.last_raw_packet: bytes = b""

    # ── public API ─────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset parser state (but keep statistics)."""
        self._state = self._SYNC1
        self._plength = 0
        self._payload = bytearray()
        self._payload_sum = 0
        self.last_signal_quality = 200

    def feed(self, byte_val: int) -> Optional[dict]:
        """
        Feed a single byte (0–255).

        Returns
        -------
        dict or None
            Decoded packet data if a complete valid packet was received,
            otherwise ``None``.
        """
        self.total_bytes += 1

        if self._state == self._SYNC1:
            if byte_val == SYNC_BYTE:
                self._state = self._SYNC2

        elif self._state == self._SYNC2:
            if byte_val == SYNC_BYTE:
                self._state = self._PLENGTH
            else:
                # Not a valid sync pair — restart
                self._state = self._SYNC1

        elif self._state == self._PLENGTH:
            if byte_val == SYNC_BYTE:
                # Extra sync byte; stay in PLENGTH state
                pass
            elif byte_val > MAX_PAYLOAD_LENGTH:
                log.warning("Payload length 0x%02X exceeds maximum — dropping", byte_val)
                self._state = self._SYNC1
            else:
                self._plength = byte_val
                self._payload = bytearray()
                self._payload_sum = 0
                if self._plength == 0:
                    # Zero-length payload — go straight to checksum
                    self._state = self._CHECKSUM
                else:
                    self._state = self._PAYLOAD

        elif self._state == self._PAYLOAD:
            self._payload.append(byte_val)
            self._payload_sum += byte_val
            if len(self._payload) >= self._plength:
                self._state = self._CHECKSUM

        elif self._state == self._CHECKSUM:
            expected = (~self._payload_sum) & 0xFF
            self._state = self._SYNC1

            if byte_val == expected:
                self.valid_packets += 1
                self.last_raw_packet = bytes(self._payload)
                return self._parse_payload(self._payload)
            else:
                self.invalid_packets += 1
                log.debug(
                    "Checksum mismatch: expected 0x%02X, got 0x%02X "
                    "(payload len=%d)",
                    expected, byte_val, self._plength,
                )
                return None

        return None

    # ── payload parser ─────────────────────────────────────────────────

    def _parse_payload(self, payload: bytearray) -> dict:
        """Parse a validated payload into a data dictionary."""
        data = empty_packet()
        data["signal_quality"] = self.last_signal_quality
        data["timestamp"] = datetime.now().isoformat(timespec="milliseconds")
        i = 0
        n = len(payload)

        while i < n:
            code = payload[i]
            i += 1

            if code >= 0x80:
                # ── Multi-byte value ────────────────────────────────
                if i >= n:
                    break
                length = payload[i]
                i += 1
                if i + length > n:
                    log.warning(
                        "Truncated multi-byte row: code=0x%02X, "
                        "declared_len=%d, remaining=%d",
                        code, length, n - i,
                    )
                    break
                value_bytes = payload[i : i + length]
                i += length

                if code == CODE_RAW_WAVE and length == 2:
                    raw = struct.unpack(">h", bytes(value_bytes))[0]
                    data["raw_eeg"] = raw

                elif code == CODE_ASIC_EEG_POWER and length == 24:
                    bands = []
                    for j in range(8):
                        b0, b1, b2 = value_bytes[j * 3 : j * 3 + 3]
                        bands.append((b0 << 16) | (b1 << 8) | b2)
                    (
                        data["delta"],
                        data["theta"],
                        data["low_alpha"],
                        data["high_alpha"],
                        data["low_beta"],
                        data["high_beta"],
                        data["low_gamma"],
                        data["high_gamma"],
                    ) = bands
                else:
                    log.debug("Unknown extended code 0x%02X (len=%d)", code, length)

            else:
                # ── Single-byte value ───────────────────────────────
                if i >= n:
                    break
                value = payload[i]
                i += 1

                if code == CODE_POOR_SIGNAL:
                    self.last_signal_quality = value
                    data["signal_quality"] = value
                elif code == CODE_ATTENTION:
                    data["attention"] = value
                elif code == CODE_MEDITATION:
                    data["meditation"] = value
                elif code == CODE_BLINK:
                    data["blink_strength"] = value
                else:
                    log.debug("Unknown single-byte code 0x%02X = %d", code, value)

        return data
