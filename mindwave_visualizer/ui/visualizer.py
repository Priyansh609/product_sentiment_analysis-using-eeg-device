"""
MindWave Visualizer — PyQtGraph Visualization Widgets
=======================================================
Real-time scrolling waveforms and time-series plots for EEG data.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame

from config import (
    COLORS, RAW_BUFFER_SIZE, METRIC_BUFFER_SIZE,
    RAW_EEG_RATE, RAW_EEG_WINDOW_SEC, METRIC_WINDOW_SEC,
)


# ── PyQtGraph global config ──────────────────────────────────────────────
pg.setConfigOptions(
    antialias=True,
    background=COLORS["background"],
    foreground=COLORS["text"],
)


def _styled_plot(title: str = "", y_label: str = "",
                 x_range: tuple | None = None) -> pg.PlotWidget:
    """Return a dark-themed PlotWidget with consistent styling."""
    pw = pg.PlotWidget()
    pw.setTitle(title, color=COLORS["text_secondary"], size="10pt")
    pw.showGrid(x=True, y=True, alpha=0.15)
    pw.setLabel("left", y_label, color=COLORS["text_secondary"])
    pw.getAxis("left").setTextPen(COLORS["text_secondary"])
    pw.getAxis("bottom").setTextPen(COLORS["text_secondary"])

    # Style the plot background
    pw.setBackground(COLORS["surface"])
    pw.getPlotItem().getViewBox().setBackgroundColor(COLORS["background"])
    pw.getPlotItem().getViewBox().setBorder({"color": COLORS["border"], "width": 1})

    if x_range:
        pw.setXRange(*x_range, padding=0)

    return pw


# ═══════════════════════════════════════════════════════════════════════════
#  Raw EEG Waveform (10-second scrolling)
# ═══════════════════════════════════════════════════════════════════════════

class RawEEGPlot(QFrame):
    """
    Scrolling raw EEG waveform — ring buffer of 5 120 samples (10 s @ 512 Hz).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 6px;")

        self._buffer = deque(maxlen=RAW_BUFFER_SIZE)
        self._time_axis = np.linspace(
            -RAW_EEG_WINDOW_SEC, 0, RAW_BUFFER_SIZE, dtype=np.float32,
        )
        self._good_signal = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._plot = _styled_plot("Raw EEG", "µV")
        self._plot.setXRange(-RAW_EEG_WINDOW_SEC, 0, padding=0)
        self._plot.setLabel("bottom", "Time (s)", color=COLORS["text_secondary"])
        self._pen_good = pg.mkPen(color=COLORS["raw_eeg"], width=1)
        self._pen_bad  = pg.mkPen(color=COLORS["error"], width=1, style=Qt.PenStyle.SolidLine)
        self._curve = self._plot.plot(pen=self._pen_good)

        # "NO SIGNAL" overlay text
        self._no_signal_text = pg.TextItem(
            "⚠  NO SIGNAL — Noise Only",
            color=COLORS["error"],
            anchor=(0.5, 0.5),
        )
        self._no_signal_text.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._no_signal_text.setPos(-RAW_EEG_WINDOW_SEC / 2, 0)
        self._no_signal_text.setVisible(False)
        self._plot.addItem(self._no_signal_text)

        layout.addWidget(self._plot)

    def set_signal_quality(self, quality: int) -> None:
        """Switch waveform appearance based on signal quality (0=good, 200=none)."""
        good = quality < 200
        if good != self._good_signal:
            self._good_signal = good
            self._curve.setPen(self._pen_good if good else self._pen_bad)
            self._no_signal_text.setVisible(not good)
            title_suffix = "" if good else "  [NO CONTACT]"
            self._plot.setTitle(f"Raw EEG{title_suffix}",
                                color=COLORS["text_secondary"] if good else COLORS["error"],
                                size="10pt")

    def append(self, value: int) -> None:
        self._buffer.append(value)

    def refresh(self) -> None:
        n = len(self._buffer)
        if n < 2:
            return
        data = np.array(self._buffer, dtype=np.float32)
        t = np.linspace(-n / RAW_EEG_RATE, 0, n, dtype=np.float32)
        self._curve.setData(t, data)


# ═══════════════════════════════════════════════════════════════════════════
#  Metric Time-Series (60-second history)
# ═══════════════════════════════════════════════════════════════════════════

class MetricPlot(QFrame):
    """
    Time-series plot for a single metric (attention, meditation, blink, etc.).
    Keeps 60 seconds of history.
    """

    def __init__(self, title: str, color: str, y_range: tuple = (0, 100),
                 parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 6px;")

        self._buffer = deque(maxlen=METRIC_BUFFER_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._plot = _styled_plot(title, "")
        self._plot.setXRange(-METRIC_WINDOW_SEC, 0, padding=0)
        self._plot.setYRange(*y_range, padding=0.05)
        self._plot.setLabel("bottom", "Time (s)", color=COLORS["text_secondary"])

        pen = pg.mkPen(color=color, width=2)
        self._curve = self._plot.plot(pen=pen)

        # Fill under curve
        self._fill = pg.FillBetweenItem(self._curve, self._curve, brush=pg.mkBrush(color + "30"))
        # We'll skip the fill for cleanliness — just the line

        layout.addWidget(self._plot)

    def append(self, value: float) -> None:
        self._buffer.append(value)

    def refresh(self) -> None:
        n = len(self._buffer)
        if n < 2:
            return
        data = np.array(self._buffer, dtype=np.float32)
        t = np.linspace(-n, 0, n, dtype=np.float32)
        self._curve.setData(t, data)

    def clear_data(self) -> None:
        self._buffer.clear()


# ═══════════════════════════════════════════════════════════════════════════
#  Combined Visualizer Panel (center area)
# ═══════════════════════════════════════════════════════════════════════════

class VisualizerPanel(QFrame):
    """
    Stacked layout of all EEG plots with pause / reset / export controls.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paused = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── Controls bar ──────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(6)

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setFixedWidth(100)
        self._pause_btn.clicked.connect(self._toggle_pause)

        self._reset_btn = QPushButton("↻  Reset")
        self._reset_btn.setFixedWidth(100)
        self._reset_btn.clicked.connect(self._reset_plots)

        self._export_btn = QPushButton("📷  Export PNG")
        self._export_btn.setFixedWidth(120)
        self._export_btn.clicked.connect(self._export_png)

        for btn in (self._pause_btn, self._reset_btn, self._export_btn):
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['surface_light']};
                    color: {COLORS['text']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: {COLORS['primary']};
                    color: white;
                }}
            """)

        controls.addWidget(self._pause_btn)
        controls.addWidget(self._reset_btn)
        controls.addStretch()
        controls.addWidget(self._export_btn)

        main_layout.addLayout(controls)

        # ── Plots ─────────────────────────────────────────────────────
        self.raw_eeg_plot = RawEEGPlot()
        self.attention_plot = MetricPlot("Attention", COLORS["attention"])
        self.meditation_plot = MetricPlot("Meditation", COLORS["meditation"])
        self.blink_plot = MetricPlot("Blink Strength", COLORS["blink"], y_range=(0, 255))

        main_layout.addWidget(self.raw_eeg_plot, stretch=3)
        main_layout.addWidget(self.attention_plot, stretch=1)
        main_layout.addWidget(self.meditation_plot, stretch=1)
        main_layout.addWidget(self.blink_plot, stretch=1)

    @property
    def is_paused(self) -> bool:
        return self._paused

    def refresh_all(self) -> None:
        """Called at 20 FPS by the dashboard timer."""
        if self._paused:
            return
        self.raw_eeg_plot.refresh()
        self.attention_plot.refresh()
        self.meditation_plot.refresh()
        self.blink_plot.refresh()

    # ── Button handlers ────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._pause_btn.setText("▶  Resume" if self._paused else "⏸  Pause")

    def _reset_plots(self) -> None:
        self.raw_eeg_plot._buffer.clear()
        self.attention_plot.clear_data()
        self.meditation_plot.clear_data()
        self.blink_plot.clear_data()
        self.refresh_all()

    def _export_png(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plot", "eeg_plot.png", "PNG Images (*.png)",
        )
        if path:
            self.grab().save(path)
