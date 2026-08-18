"""
MindWave EEG Visualizer — Entry Point
=======================================
Launch the PyQt6 dashboard application.
"""

import sys
import os

# Ensure the package root is on sys.path so relative imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from config import COLORS
from logger import setup_logger
from ui.dashboard import Dashboard

log = setup_logger("main")


def main() -> None:
    """Application entry point."""
    # High-DPI scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("MindWave Visualizer")
    app.setOrganizationName("NeuroSkyVisualizer")
    app.setStyle("Fusion")

    # ── Dark palette ──────────────────────────────────────────────────
    from PyQt6.QtGui import QPalette, QColor

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(COLORS["background"]))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base,            QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(COLORS["surface_light"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Text,            QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button,          QColor(COLORS["surface_light"]))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor(COLORS["accent"]))
    palette.setColor(QPalette.ColorRole.Link,            QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    # Global font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ── Launch ────────────────────────────────────────────────────────
    log.info("Starting MindWave Visualizer")
    window = Dashboard()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
