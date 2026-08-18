"""
MindWave Visualizer — Packet Inspector Panel
===============================================
Collapsible developer panel showing raw packet hex, decoded JSON,
and packet statistics.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QGroupBox, QApplication, QFileDialog,
    QSplitter,
)

from config import COLORS


class PacketInspector(QFrame):
    """
    Developer panel that shows:
    * Packet rate (packets/sec)
    * Valid / invalid packet counts
    * Last raw packet in hex
    * Last decoded packet as JSON
    * Scrolling hex log
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            PacketInspector {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)

        self._packet_times: deque = deque(maxlen=100)
        self._hex_log: list[str] = []
        self._max_log_lines = 500

        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("🔍  PACKET INSPECTOR")
        title.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 11px; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch()
        main.addLayout(header)

        # ── Statistics row ────────────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['background']};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)

        self._rate_label    = self._stat_label("RATE", "0 pkt/s")
        self._valid_label   = self._stat_label("VALID", "0")
        self._invalid_label = self._stat_label("INVALID", "0")
        self._bytes_label   = self._stat_label("BYTES", "0")

        for lbl_pair in (self._rate_label, self._valid_label,
                         self._invalid_label, self._bytes_label):
            stats_layout.addWidget(lbl_pair[0])

        main.addWidget(stats_frame)

        # ── Last raw packet ───────────────────────────────────────────
        raw_group = QGroupBox("Last Raw Packet (Hex)")
        raw_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 14px;
                font-size: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
            }}
        """)
        raw_layout = QVBoxLayout(raw_group)
        self._raw_hex_label = QLabel("—")
        self._raw_hex_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        self._raw_hex_label.setWordWrap(True)
        self._raw_hex_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        raw_layout.addWidget(self._raw_hex_label)
        main.addWidget(raw_group)

        # ── Last decoded packet (JSON) ────────────────────────────────
        json_group = QGroupBox("Last Decoded Packet")
        json_group.setStyleSheet(raw_group.styleSheet())
        json_layout = QVBoxLayout(json_group)
        self._json_text = QTextEdit()
        self._json_text.setReadOnly(True)
        self._json_text.setMaximumHeight(160)
        self._json_text.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['background']};
                color: {COLORS['raw_eeg']};
                font-family: 'Consolas', monospace;
                font-size: 10px;
                border: none;
                border-radius: 4px;
            }}
        """)
        json_layout.addWidget(self._json_text)
        main.addWidget(json_group)

        # ── Hex log ───────────────────────────────────────────────────
        log_group = QGroupBox("Packet Log")
        log_group.setStyleSheet(raw_group.styleSheet())
        log_layout = QVBoxLayout(log_group)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(150)
        self._log_text.setStyleSheet(self._json_text.styleSheet())
        log_layout.addWidget(self._log_text)

        # Buttons
        btn_layout = QHBoxLayout()
        copy_btn  = self._action_btn("📋 Copy", self._copy_last)
        clear_btn = self._action_btn("🗑 Clear", self._clear_log)
        save_btn  = self._action_btn("💾 Save", self._save_log)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        log_layout.addLayout(btn_layout)

        main.addWidget(log_group)
        main.addStretch()

    # ── Public API ─────────────────────────────────────────────────────

    def update_packet(self, raw_bytes: bytes, decoded: dict) -> None:
        """Called for every decoded packet."""
        now = datetime.now()
        self._packet_times.append(now.timestamp())

        # Hex display
        hex_str = " ".join(f"{b:02X}" for b in raw_bytes)
        self._raw_hex_label.setText(hex_str)

        # JSON display
        display_data = {k: v for k, v in decoded.items() if v != 0 or k in ("signal_quality",)}
        self._json_text.setText(json.dumps(display_data, indent=2))

        # Log
        ts = now.strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{ts}] {hex_str}"
        self._hex_log.append(log_line)
        if len(self._hex_log) > self._max_log_lines:
            self._hex_log = self._hex_log[-self._max_log_lines:]

    def update_stats(self, stats: dict) -> None:
        """Update the statistics display."""
        self._valid_label[1].setText(f"{stats.get('valid', 0):,}")
        self._invalid_label[1].setText(f"{stats.get('invalid', 0):,}")
        self._bytes_label[1].setText(f"{stats.get('total_bytes', 0):,}")

        # Packet rate
        now_ts = datetime.now().timestamp()
        recent = [t for t in self._packet_times if now_ts - t < 1.0]
        self._rate_label[1].setText(f"{len(recent)} pkt/s")

    def refresh_log(self) -> None:
        """Append recent log lines to the display (called less frequently)."""
        self._log_text.setText("\n".join(self._hex_log[-50:]))
        scrollbar = self._log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ── Helpers ────────────────────────────────────────────────────────

    def _stat_label(self, title: str, initial: str):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(1)

        t = QLabel(title)
        t.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9px;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v = QLabel(initial)
        v.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px; font-weight: bold;")
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(t)
        layout.addWidget(v)
        return (container, v)

    def _action_btn(self, text: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(26)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface_light']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background: {COLORS['primary']};
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _copy_last(self) -> None:
        text = self._raw_hex_label.text()
        QApplication.clipboard().setText(text)

    def _clear_log(self) -> None:
        self._hex_log.clear()
        self._log_text.clear()

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Packet Log", "packet_log.txt", "Text Files (*.txt)",
        )
        if path:
            with open(path, "w") as f:
                f.write("\n".join(self._hex_log))
