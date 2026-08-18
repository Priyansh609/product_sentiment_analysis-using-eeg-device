"""
MindWave Visualizer — Neuromarketing Product Panel
=====================================================
Product selector, experiment controls, engagement display,
session analysis table, and ML label annotation.
"""

from __future__ import annotations

import os
import random
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSpinBox, QFileDialog, QListWidget,
    QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QMessageBox, QSizePolicy, QScrollArea,
)

from config import COLORS, LABELS


# ═══════════════════════════════════════════════════════════════════════════
#  Product Panel (full neuromarketing dashboard)
# ═══════════════════════════════════════════════════════════════════════════

class ProductPanel(QFrame):
    """
    Neuromarketing experiment panel:
    1. Load product images
    2. Run timed experiments per product
    3. Display real-time engagement
    4. Show rankings
    5. Annotate with ML labels
    """

    # Signals
    experiment_started  = pyqtSignal(str)          # product_name
    experiment_stopped  = pyqtSignal()
    label_applied       = pyqtSignal(str, str)     # product_name, label

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._products: List[dict] = []     # [{"name": str, "path": str}]
        self._current_index: int = -1
        self._experiment_active: bool = False
        self._experiment_timer: Optional[QTimer] = None
        self._experiment_elapsed: int = 0
        self._experiment_duration: int = 30  # seconds

        self._setup_ui()

    # ── UI construction ────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background: {COLORS['background']};")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Product list & controls ─────────────────────────────
        left_panel = QFrame()
        left_panel.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)

        # Header
        header = QLabel("🛍  PRODUCT TESTING")
        header.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 13px; font-weight: bold; border: none;"
        )
        left_layout.addWidget(header)

        # Product list
        self._product_list = QListWidget()
        self._product_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-size: 11px;
            }}
            QListWidget::item:selected {{
                background: {COLORS['primary']};
            }}
        """)
        self._product_list.currentRowChanged.connect(self._on_product_selected)
        left_layout.addWidget(self._product_list)

        # Load / remove buttons
        btn_row = QHBoxLayout()
        self._load_btn = self._make_btn("📁 Load Images", self._load_images)
        self._remove_btn = self._make_btn("✕ Remove", self._remove_product)
        btn_row.addWidget(self._load_btn)
        btn_row.addWidget(self._remove_btn)
        left_layout.addLayout(btn_row)

        # Navigation
        nav_row = QHBoxLayout()
        self._prev_btn = self._make_btn("◀ Prev", self._prev_product)
        self._next_btn = self._make_btn("Next ▶", self._next_product)
        self._rand_btn = self._make_btn("🔀 Randomize", self._randomize)
        nav_row.addWidget(self._prev_btn)
        nav_row.addWidget(self._next_btn)
        nav_row.addWidget(self._rand_btn)
        left_layout.addLayout(nav_row)

        # Experiment controls
        exp_group = QGroupBox("Experiment")
        exp_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 16px;
                font-size: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
            }}
        """)
        exp_layout = QVBoxLayout(exp_group)

        dur_row = QHBoxLayout()
        dur_label = QLabel("Duration (s):")
        dur_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 11px; border: none;")
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(5, 300)
        self._duration_spin.setValue(30)
        self._duration_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 2px;
            }}
        """)
        self._duration_spin.valueChanged.connect(
            lambda v: setattr(self, '_experiment_duration', v)
        )
        dur_row.addWidget(dur_label)
        dur_row.addWidget(self._duration_spin)
        exp_layout.addLayout(dur_row)

        self._start_exp_btn = self._make_btn("▶ Start Experiment", self._start_experiment,
                                              accent=True)
        self._stop_exp_btn = self._make_btn("⏹ Stop Experiment", self._stop_experiment)
        self._stop_exp_btn.setEnabled(False)

        exp_layout.addWidget(self._start_exp_btn)
        exp_layout.addWidget(self._stop_exp_btn)

        self._timer_label = QLabel("00:00")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 18px; font-weight: bold; border: none;"
        )
        exp_layout.addWidget(self._timer_label)

        left_layout.addWidget(exp_group)

        # Label selector
        label_group = QGroupBox("ML Label")
        label_group.setStyleSheet(exp_group.styleSheet())
        label_layout = QVBoxLayout(label_group)

        self._label_combo = QComboBox()
        self._label_combo.addItems(LABELS)
        self._label_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLORS['surface']};
                color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
            }}
        """)
        label_layout.addWidget(self._label_combo)

        self._apply_label_btn = self._make_btn("🏷 Apply Label", self._apply_label)
        label_layout.addWidget(self._apply_label_btn)

        left_layout.addWidget(label_group)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # ── Center: Product image & engagement ────────────────────────
        center_panel = QFrame()
        center_panel.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(10, 10, 10, 10)

        self._product_name_label = QLabel("No product selected")
        self._product_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._product_name_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 16px; font-weight: bold; border: none;"
        )
        center_layout.addWidget(self._product_name_label)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(300, 300)
        self._image_label.setStyleSheet(
            f"background: {COLORS['background']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px;"
        )
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        center_layout.addWidget(self._image_label, stretch=1)

        # Engagement display
        eng_frame = QFrame()
        eng_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['background']};
                border-radius: 8px;
                border: none;
            }}
        """)
        eng_layout = QHBoxLayout(eng_frame)

        self._engagement_label = self._metric_display("ENGAGEMENT", "—")
        self._peak_att_label = self._metric_display("PEAK ATTN", "—")
        self._avg_att_label = self._metric_display("AVG ATTN", "—")
        self._session_dur_label = self._metric_display("DURATION", "—")

        for w in (self._engagement_label, self._peak_att_label,
                  self._avg_att_label, self._session_dur_label):
            eng_layout.addWidget(w[0])

        center_layout.addWidget(eng_frame)

        splitter.addWidget(center_panel)

        # ── Right: Rankings table ─────────────────────────────────────
        right_panel = QFrame()
        right_panel.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)

        rank_header = QLabel("📊  SESSION RANKINGS")
        rank_header.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 13px; font-weight: bold; border: none;"
        )
        right_layout.addWidget(rank_header)

        self._rankings_table = QTableWidget()
        self._rankings_table.setColumnCount(6)
        self._rankings_table.setHorizontalHeaderLabels([
            "Rank", "Product", "Avg Attn", "Max Attn", "Avg Med", "Engagement",
        ])
        self._rankings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._rankings_table.setStyleSheet(f"""
            QTableWidget {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                gridline-color: {COLORS['border']};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background: {COLORS['surface_light']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                padding: 4px;
                font-size: 10px;
            }}
        """)
        self._rankings_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self._rankings_table)

        self._clear_rankings_btn = self._make_btn("🗑 Clear All Sessions", self._clear_rankings)
        right_layout.addWidget(self._clear_rankings_btn)

        splitter.addWidget(right_panel)

        # Splitter sizes
        splitter.setSizes([250, 500, 300])

        main_layout.addWidget(splitter)

    # ── Public API ─────────────────────────────────────────────────────

    @property
    def current_product_name(self) -> Optional[str]:
        if 0 <= self._current_index < len(self._products):
            return self._products[self._current_index]["name"]
        return None

    @property
    def current_label(self) -> str:
        return self._label_combo.currentText()

    @property
    def is_experiment_active(self) -> bool:
        return self._experiment_active

    def update_engagement(self, engagement: float, session_stats: dict | None) -> None:
        """Update the engagement display from the processor."""
        self._engagement_label[1].setText(f"{engagement:.1f}")

        if session_stats:
            self._peak_att_label[1].setText(f"{session_stats.get('max_attention', 0):.0f}")
            self._avg_att_label[1].setText(f"{session_stats.get('avg_attention', 0):.1f}")
            dur = session_stats.get('duration_s', 0)
            self._session_dur_label[1].setText(f"{dur:.0f}s")

    def update_rankings(self, rankings: list[dict]) -> None:
        """Refresh the rankings table."""
        self._rankings_table.setRowCount(len(rankings))
        for row, r in enumerate(rankings):
            items = [
                str(r.get("rank", "")),
                r.get("product_name", ""),
                f"{r.get('avg_attention', 0):.1f}",
                f"{r.get('max_attention', 0):.0f}",
                f"{r.get('avg_meditation', 0):.1f}",
                f"{r.get('avg_engagement', 0):.1f}",
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Highlight top product
                if row == 0:
                    item.setForeground(Qt.GlobalColor.yellow)
                self._rankings_table.setItem(row, col, item)

    # ── Internal handlers ──────────────────────────────────────────────

    def _load_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Load Product Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        for fpath in files:
            name = os.path.splitext(os.path.basename(fpath))[0]
            self._products.append({"name": name, "path": fpath})
            self._product_list.addItem(name)

        if self._products and self._current_index < 0:
            self._product_list.setCurrentRow(0)

    def _remove_product(self) -> None:
        row = self._product_list.currentRow()
        if row >= 0:
            self._products.pop(row)
            self._product_list.takeItem(row)

    def _on_product_selected(self, row: int) -> None:
        self._current_index = row
        if 0 <= row < len(self._products):
            product = self._products[row]
            self._product_name_label.setText(product["name"])
            pixmap = QPixmap(product["path"])
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self._image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._image_label.setPixmap(scaled)
            else:
                self._image_label.setText("Cannot load image")

    def _prev_product(self) -> None:
        if self._products:
            idx = max(0, self._current_index - 1)
            self._product_list.setCurrentRow(idx)

    def _next_product(self) -> None:
        if self._products:
            idx = min(len(self._products) - 1, self._current_index + 1)
            self._product_list.setCurrentRow(idx)

    def _randomize(self) -> None:
        if len(self._products) > 1:
            random.shuffle(self._products)
            self._product_list.clear()
            for p in self._products:
                self._product_list.addItem(p["name"])
            self._product_list.setCurrentRow(0)

    def _start_experiment(self) -> None:
        if not self._products:
            QMessageBox.warning(self, "No Products", "Load product images first.")
            return
        if self._current_index < 0:
            return

        self._experiment_active = True
        self._experiment_elapsed = 0
        self._experiment_duration = self._duration_spin.value()
        self._start_exp_btn.setEnabled(False)
        self._stop_exp_btn.setEnabled(True)

        # Timer
        self._experiment_timer = QTimer()
        self._experiment_timer.setInterval(1000)
        self._experiment_timer.timeout.connect(self._tick)
        self._experiment_timer.start()

        self.experiment_started.emit(self.current_product_name or "Unknown")

    def _stop_experiment(self) -> None:
        self._experiment_active = False
        if self._experiment_timer:
            self._experiment_timer.stop()
            self._experiment_timer = None

        self._start_exp_btn.setEnabled(True)
        self._stop_exp_btn.setEnabled(False)
        self.experiment_stopped.emit()

    def _tick(self) -> None:
        self._experiment_elapsed += 1
        remaining = max(0, self._experiment_duration - self._experiment_elapsed)
        mins, secs = divmod(remaining, 60)
        self._timer_label.setText(f"{mins:02d}:{secs:02d}")

        if self._experiment_elapsed >= self._experiment_duration:
            self._stop_experiment()

    def _apply_label(self) -> None:
        name = self.current_product_name
        label = self._label_combo.currentText()
        if name:
            self.label_applied.emit(name, label)

    def _clear_rankings(self) -> None:
        self._rankings_table.setRowCount(0)

    # ── Helpers ────────────────────────────────────────────────────────

    def _make_btn(self, text: str, callback, accent: bool = False) -> QPushButton:
        btn = QPushButton(text)
        bg = COLORS['primary'] if accent else COLORS['surface_light']
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {COLORS['primary']};
                color: white;
            }}
            QPushButton:disabled {{
                background: {COLORS['surface_light']};
                color: {COLORS['text_secondary']};
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _metric_display(self, title: str, initial: str):
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border-radius: 6px;
                border: 1px solid {COLORS['border']};
                padding: 6px;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9px; border: none;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v = QLabel(initial)
        v.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: 18px; font-weight: bold; border: none;"
        )
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(t)
        layout.addWidget(v)
        return (container, v)
