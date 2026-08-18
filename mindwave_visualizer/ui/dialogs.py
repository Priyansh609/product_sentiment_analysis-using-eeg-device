"""
MindWave Visualizer — Dialogs
===============================
Error, about, and export helper dialogs.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTextEdit,
)

from config import COLORS


class AboutDialog(QDialog):
    """Simple 'About' dialog."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About MindWave Visualizer")
        self.setFixedSize(420, 280)
        self.setStyleSheet(f"""
            QDialog {{
                background: {COLORS['surface']};
            }}
            QLabel {{
                color: {COLORS['text']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("🧠  MindWave Visualizer")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['primary']};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "Real-time EEG visualiser and neuromarketing dashboard\n"
            "for the NeuroSky MindWave Mobile headset.\n\n"
            "Features:\n"
            "• Live raw EEG waveform & eSense metrics\n"
            "• Product engagement analysis\n"
            "• CSV recording with ML labels\n"
            "• Simulation mode for testing"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        layout.addWidget(desc)

        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        layout.addWidget(version)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
            }}
            QPushButton:hover {{ background: {COLORS['accent']}; }}
        """)
        close_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


class ErrorDialog(QDialog):
    """Modal error dialog with detail text."""

    def __init__(self, title: str, message: str, details: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"QDialog {{ background: {COLORS['surface']}; }}")

        layout = QVBoxLayout(self)

        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 32px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
        layout.addWidget(msg)

        if details:
            det = QTextEdit()
            det.setPlainText(details)
            det.setReadOnly(True)
            det.setMaximumHeight(100)
            det.setStyleSheet(f"""
                QTextEdit {{
                    background: {COLORS['background']};
                    color: {COLORS['text_secondary']};
                    font-family: Consolas, monospace;
                    font-size: 10px;
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                }}
            """)
            layout.addWidget(det)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['error']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
            }}
        """)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)


def export_csv_dialog(parent, default_name: str = "eeg_data.csv") -> str | None:
    """Show a save-file dialog for CSV export.  Returns the chosen path or None."""
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export CSV", default_name, "CSV Files (*.csv);;All Files (*)",
    )
    return path if path else None
