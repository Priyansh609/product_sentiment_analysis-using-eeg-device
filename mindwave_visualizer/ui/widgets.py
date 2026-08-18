"""
MindWave Visualizer — Custom Widgets
======================================
QPainter-based gauge, status indicator, signal-quality bar, blink counter,
and EEG band-power bars.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QConicalGradient,
    QRadialGradient, QLinearGradient, QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QFrame, QProgressBar, QGraphicsOpacityEffect,
)

from config import COLORS, BAND_NAMES


# ═══════════════════════════════════════════════════════════════════════════
#  Circular Gauge Widget
# ═══════════════════════════════════════════════════════════════════════════

class GaugeWidget(QWidget):
    """
    Animated circular gauge (0 – 100) rendered with QPainter.

    Parameters
    ----------
    title : str
        Label drawn below the gauge.
    color : str
        Accent hex colour for the filled arc.
    """

    def __init__(self, title: str = "", color: str = COLORS["primary"],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._color = QColor(color)
        self._value: float = 0.0
        self._display_value: float = 0.0  # animated
        self.setMinimumSize(140, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Animation
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── property for animation ─────────────────────────────────────────

    def _get_display_value(self) -> float:
        return self._display_value

    def _set_display_value(self, v: float) -> None:
        self._display_value = v
        self.update()

    displayValue = pyqtProperty(float, _get_display_value, _set_display_value)

    # ── public API ─────────────────────────────────────────────────────

    def set_value(self, value: float) -> None:
        value = max(0.0, min(100.0, value))
        if value != self._value:
            self._value = value
            self._anim.stop()
            self._anim.setStartValue(self._display_value)
            self._anim.setEndValue(value)
            self._anim.start()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    # ── paint ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        side = min(w, h - 28)
        cx, cy = w / 2, (h - 28) / 2
        radius = side / 2 - 12
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        arc_width = 10
        start_angle = 225 * 16
        span_total  = -270 * 16
        span_value  = int(span_total * self._display_value / 100)

        # ── Background track ──────────────────────────────────────
        pen = QPen(QColor(COLORS["surface_light"]), arc_width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, start_angle, span_total)

        # ── Value arc with gradient ───────────────────────────────
        if self._display_value > 0:
            grad = QConicalGradient(cx, cy, 225)
            c = QColor(self._color)
            c_light = QColor(self._color)
            c_light.setAlpha(180)
            grad.setColorAt(0.0, c)
            grad.setColorAt(0.75, c_light)
            grad.setColorAt(1.0, c)

            pen = QPen(grad, arc_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, start_angle, span_value)

        # ── Glow dot at arc tip ───────────────────────────────────
        if self._display_value > 0:
            angle_deg = 225 - 270 * self._display_value / 100
            angle_rad = math.radians(angle_deg)
            dot_x = cx + radius * math.cos(angle_rad)
            dot_y = cy - radius * math.sin(angle_rad)

            glow = QRadialGradient(dot_x, dot_y, 8)
            glow_color = QColor(self._color)
            glow_color.setAlpha(120)
            glow.setColorAt(0, glow_color)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(dot_x - 8, dot_y - 8, 16, 16))

        # ── Value text ────────────────────────────────────────────
        font = QFont("Segoe UI", 22, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(self._display_value)}")

        # ── Title ─────────────────────────────────────────────────
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text_secondary"]))
        title_rect = QRectF(0, h - 26, w, 24)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         self._title)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  Connection Status Indicator
# ═══════════════════════════════════════════════════════════════════════════

class StatusIndicator(QWidget):
    """Small coloured dot: green = connected, red = disconnected, yellow = poor signal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = "disconnected"
        self.setFixedSize(18, 18)

    def set_status(self, status: str) -> None:
        """Set status to 'connected', 'disconnected', or 'poor'."""
        self._status = status
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_map = {
            "connected":    COLORS["success"],
            "disconnected": COLORS["error"],
            "poor":         COLORS["warning"],
            "simulation":   COLORS["primary"],
        }
        color = QColor(color_map.get(self._status, COLORS["error"]))

        # Glow
        glow = QRadialGradient(9, 9, 9)
        glow_c = QColor(color)
        glow_c.setAlpha(80)
        glow.setColorAt(0, glow_c)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(0, 0, 18, 18)

        # Dot
        painter.setBrush(color)
        painter.drawEllipse(4, 4, 10, 10)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  Signal Quality Bar
# ═══════════════════════════════════════════════════════════════════════════

class SignalQualityBar(QWidget):
    """
    Horizontal bar that visualises signal quality.
    0 = excellent (green, full), 200 = no contact (red, empty).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quality: int = 200
        self.setFixedHeight(22)
        self.setMinimumWidth(100)

    def set_quality(self, value: int) -> None:
        self._quality = max(0, min(200, value))
        self.update()

    def quality_text(self) -> str:
        q = self._quality
        if q == 0:
            return "Excellent"
        elif q < 50:
            return "Good"
        elif q < 100:
            return "Fair"
        elif q < 200:
            return "Poor"
        return "No Signal"

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["surface_light"]))
        painter.drawRoundedRect(0, 0, w, h, 4, 4)

        # Fill (0 = full, 200 = empty)
        fill_ratio = max(0, 1.0 - self._quality / 200.0)
        fill_w = int(w * fill_ratio)

        if fill_w > 0:
            if fill_ratio > 0.7:
                bar_color = QColor(COLORS["signal_good"])
            elif fill_ratio > 0.4:
                bar_color = QColor(COLORS["signal_ok"])
            else:
                bar_color = QColor(COLORS["signal_bad"])

            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, bar_color)
            lighter = QColor(bar_color)
            lighter.setAlpha(180)
            grad.setColorAt(1, lighter)
            painter.setBrush(grad)
            painter.drawRoundedRect(0, 0, fill_w, h, 4, 4)

        # Text
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                         self.quality_text())

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  Blink Counter
# ═══════════════════════════════════════════════════════════════════════════

class BlinkCounter(QFrame):
    """
    Displays total blink count with a flash animation on each detection.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = 0
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            BlinkCounter {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)

        self._title_label = QLabel("BLINKS")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")

        self._count_label = QLabel("0")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setStyleSheet(
            f"color: {COLORS['blink']}; font-size: 28px; font-weight: bold;"
        )

        self._flash_label = QLabel("⚡")
        self._flash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._flash_label.setStyleSheet("font-size: 20px;")
        self._flash_effect = QGraphicsOpacityEffect(self._flash_label)
        self._flash_effect.setOpacity(0.0)
        self._flash_label.setGraphicsEffect(self._flash_effect)

        layout.addWidget(self._title_label)
        layout.addWidget(self._count_label)
        layout.addWidget(self._flash_label)

    def register_blink(self, strength: int) -> None:
        if strength <= 0:
            return
        self._count += 1
        self._count_label.setText(str(self._count))

        # Flash animation
        anim = QPropertyAnimation(self._flash_effect, b"opacity")
        anim.setDuration(400)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start()
        # prevent garbage collection
        self._last_anim = anim

    def reset(self) -> None:
        self._count = 0
        self._count_label.setText("0")

    @property
    def count(self) -> int:
        return self._count


# ═══════════════════════════════════════════════════════════════════════════
#  EEG Band Power Bars
# ═══════════════════════════════════════════════════════════════════════════

class BandPowerBar(QWidget):
    """Single horizontal bar for one EEG band."""

    def __init__(self, name: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._color = QColor(color)
        self._value: float = 0
        self._max_value: float = 1
        self.setFixedHeight(20)
        self.setMinimumWidth(80)

    def set_value(self, value: float, max_value: float = 0) -> None:
        self._value = value
        if max_value > 0:
            self._max_value = max_value
        elif value > self._max_value:
            self._max_value = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["surface_light"]))
        painter.drawRoundedRect(0, 0, w, h, 3, 3)

        # Fill
        ratio = min(self._value / max(self._max_value, 1), 1.0)
        fill_w = int(w * ratio)
        if fill_w > 0:
            c = QColor(self._color)
            c.setAlpha(200)
            painter.setBrush(c)
            painter.drawRoundedRect(0, 0, fill_w, h, 3, 3)

        # Label
        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        label = self._name.replace("_", " ").title()
        painter.drawText(QRectF(4, 0, w - 8, h), Qt.AlignmentFlag.AlignVCenter, label)

        # Value
        painter.drawText(
            QRectF(4, 0, w - 8, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            f"{int(self._value):,}",
        )

        painter.end()


class BandPowerPanel(QFrame):
    """Stacked bar panel for all 8 EEG frequency bands."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            BandPowerPanel {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(3)

        title = QLabel("EEG BAND POWER")
        title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._bars: dict[str, BandPowerBar] = {}
        for name in BAND_NAMES:
            bar = BandPowerBar(name, COLORS.get(name, COLORS["primary"]))
            self._bars[name] = bar
            layout.addWidget(bar)

    def update_values(self, data: dict) -> None:
        max_val = 1
        for name in BAND_NAMES:
            v = data.get(name, 0)
            if v > max_val:
                max_val = v
        for name in BAND_NAMES:
            self._bars[name].set_value(data.get(name, 0), max_val)


# ═══════════════════════════════════════════════════════════════════════════
#  Styled Card / Section Frame
# ═══════════════════════════════════════════════════════════════════════════

class CardFrame(QFrame):
    """Reusable dark-themed card container."""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            CardFrame {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 1px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(lbl)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._layout
