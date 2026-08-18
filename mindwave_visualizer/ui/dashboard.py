"""
MindWave Visualizer — Main Dashboard Window
=============================================
Three-panel dockable layout with mode switching between
EEG Monitor and Neuromarketing modes.
"""

from __future__ import annotations

import os
import shutil
import time
from functools import partial

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QAction, QFont, QColor, QPalette, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QDockWidget, QTabWidget,
    QStatusBar, QMenuBar, QMenu, QToolBar, QMessageBox,
    QApplication, QSplitter, QScrollArea, QSizePolicy,
)

from config import COLORS, SETTINGS_ORG, SETTINGS_APP, UPDATE_INTERVAL_MS
from eeg_reader import EEGReader
from simulator import EEGSimulator
from recorder import Recorder
from eeg_processor import EngagementEngine
from logger import setup_logger

from ui.widgets import (
    GaugeWidget, StatusIndicator, SignalQualityBar,
    BlinkCounter, BandPowerPanel, CardFrame,
)
from ui.visualizer import VisualizerPanel
from ui.packet_inspector import PacketInspector
from ui.product_panel import ProductPanel
from ui.dialogs import AboutDialog, ErrorDialog, export_csv_dialog

log = setup_logger("dashboard")


class Dashboard(QMainWindow):
    """
    Main application window.

    Layout
    ------
    ┌──────────┬─────────────────────────┬──────────┐
    │  LEFT    │  CENTER                 │  RIGHT   │
    │  Status  │  Tab: EEG Monitor       │  Gauges  │
    │  Controls│  Tab: Neuromarketing    │  Bands   │
    │  Record  │                         │  Blinks  │
    └──────────┴─────────────────────────┴──────────┘
    │                 STATUS BAR                     │
    └────────────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("🧠  MindWave EEG Visualizer")
        self.setMinimumSize(1200, 750)

        # ── Core components ───────────────────────────────────────────
        self._reader: EEGReader | EEGSimulator | None = None
        self._recorder = Recorder()
        self._engine = EngagementEngine()
        self._simulation_mode = False
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # ── Build UI ──────────────────────────────────────────────────
        self._apply_theme()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()
        self._build_status_bar()

        # ── Refresh timer (20 FPS) ────────────────────────────────────
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(UPDATE_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_ui)

        # ── Inspector refresh (slower — 4 Hz) ────────────────────────
        self._inspector_timer = QTimer()
        self._inspector_timer.setInterval(250)
        self._inspector_timer.timeout.connect(self._refresh_inspector)

        # ── Start recorder thread ─────────────────────────────────────
        self._recorder.start()
        self._recorder.rows_written.connect(self._on_rows_written)
        self._recorder.duration_updated.connect(self._on_duration_updated)
        self._recorder.recording_started.connect(
            lambda p: self._status_msg(f"Recording → {os.path.basename(p)}")
        )
        self._recorder.recording_stopped.connect(
            lambda p: self._status_msg(f"Recording saved → {p}")
        )

        # ── Restore window state ──────────────────────────────────────
        self._restore_state()

        # ── Populate COM ports ────────────────────────────────────────
        self._refresh_ports()

        log.info("Dashboard initialised")

    # ═══════════════════════════════════════════════════════════════════
    #  Theme
    # ═══════════════════════════════════════════════════════════════════

    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {COLORS['background']};
            }}
            QDockWidget {{
                color: {COLORS['text']};
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }}
            QDockWidget::title {{
                background: {COLORS['surface']};
                padding: 6px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QToolBar {{
                background: {COLORS['surface']};
                border-bottom: 1px solid {COLORS['border']};
                spacing: 4px;
                padding: 2px;
            }}
            QMenuBar {{
                background: {COLORS['surface']};
                color: {COLORS['text']};
                border-bottom: 1px solid {COLORS['border']};
            }}
            QMenuBar::item:selected {{
                background: {COLORS['primary']};
            }}
            QMenu {{
                background: {COLORS['surface']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
            }}
            QMenu::item:selected {{
                background: {COLORS['primary']};
            }}
            QStatusBar {{
                background: {COLORS['surface']};
                color: {COLORS['text_secondary']};
                border-top: 1px solid {COLORS['border']};
            }}
            QScrollArea {{
                border: none;
            }}
        """)

    # ═══════════════════════════════════════════════════════════════════
    #  Menu Bar
    # ═══════════════════════════════════════════════════════════════════

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        file_menu.addAction("Export CSV…", self._export_csv)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # View
        view_menu = mb.addMenu("&View")
        self._inspector_action = QAction("Packet Inspector", self, checkable=True)
        self._inspector_action.setChecked(False)
        self._inspector_action.toggled.connect(self._toggle_inspector)
        view_menu.addAction(self._inspector_action)

        # Mode
        mode_menu = mb.addMenu("&Mode")
        self._sim_action = QAction("Simulation Mode", self, checkable=True)
        self._sim_action.toggled.connect(self._toggle_simulation)
        mode_menu.addAction(self._sim_action)

        # Help
        help_menu = mb.addMenu("&Help")
        help_menu.addAction("About", lambda: AboutDialog(self).exec())

    # ═══════════════════════════════════════════════════════════════════
    #  Toolbar
    # ═══════════════════════════════════════════════════════════════════

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._connect_btn = self._tool_btn("⚡ Connect", self._connect)
        self._disconnect_btn = self._tool_btn("⏏ Disconnect", self._disconnect)
        self._disconnect_btn.setEnabled(False)

        tb.addWidget(self._connect_btn)
        tb.addWidget(self._disconnect_btn)
        tb.addSeparator()

        self._rec_start_btn = self._tool_btn("⏺ Record", self._start_recording)
        self._rec_stop_btn = self._tool_btn("⏹ Stop", self._stop_recording)
        self._rec_stop_btn.setEnabled(False)
        self._save_btn = self._tool_btn("💾 Save", self._export_csv)

        tb.addWidget(self._rec_start_btn)
        tb.addWidget(self._rec_stop_btn)
        tb.addWidget(self._save_btn)

    # ═══════════════════════════════════════════════════════════════════
    #  Left Panel (Connection / Controls / Recording)
    # ═══════════════════════════════════════════════════════════════════

    def _build_left_panel(self) -> None:
        dock = QDockWidget("Controls", self)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Connection section ────────────────────────────────────────
        conn_card = CardFrame("CONNECTION")
        cl = conn_card.content_layout

        # Status row
        status_row = QHBoxLayout()
        self._status_indicator = StatusIndicator()
        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet(f"color: {COLORS['error']}; font-size: 11px;")
        status_row.addWidget(self._status_indicator)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        cl.addLayout(status_row)

        # COM port
        port_row = QHBoxLayout()
        port_lbl = QLabel("Port:")
        port_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(80)
        self._port_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 3px;
                font-size: 11px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLORS['surface']};
                color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
            }}
        """)
        self._refresh_port_btn = QPushButton("↻")
        self._refresh_port_btn.setFixedSize(28, 28)
        self._refresh_port_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface_light']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {COLORS['primary']}; }}
        """)
        self._refresh_port_btn.clicked.connect(self._refresh_ports)
        port_row.addWidget(port_lbl)
        port_row.addWidget(self._port_combo, stretch=1)
        port_row.addWidget(self._refresh_port_btn)
        cl.addLayout(port_row)

        # Signal quality
        sq_lbl = QLabel("Signal Quality")
        sq_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        cl.addWidget(sq_lbl)
        self._signal_bar = SignalQualityBar()
        cl.addWidget(self._signal_bar)

        # Mode label
        self._mode_label = QLabel("Mode: Live")
        self._mode_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        cl.addWidget(self._mode_label)

        layout.addWidget(conn_card)

        # ── Recording section ─────────────────────────────────────────
        rec_card = CardFrame("RECORDING")
        rl = rec_card.content_layout

        self._rec_status_label = QLabel("Not recording")
        self._rec_status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        rl.addWidget(self._rec_status_label)

        self._rec_timer_label = QLabel("00:00")
        self._rec_timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rec_timer_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 20px; font-weight: bold;"
        )
        rl.addWidget(self._rec_timer_label)

        self._rec_rows_label = QLabel("Rows: 0")
        self._rec_rows_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        rl.addWidget(self._rec_rows_label)

        layout.addWidget(rec_card)

        # ── Statistics section ────────────────────────────────────────
        stats_card = CardFrame("PACKET STATISTICS")
        sl = stats_card.content_layout

        self._pkt_total_label = QLabel("Total: 0")
        self._pkt_valid_label = QLabel("Valid: 0")
        self._pkt_invalid_label = QLabel("Invalid: 0")
        for lbl in (self._pkt_total_label, self._pkt_valid_label, self._pkt_invalid_label):
            lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
            sl.addWidget(lbl)

        layout.addWidget(stats_card)

        layout.addStretch()

        scroll.setWidget(container)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    # ═══════════════════════════════════════════════════════════════════
    #  Center Panel (Tabs: EEG Monitor | Neuromarketing)
    # ═══════════════════════════════════════════════════════════════════

    def _build_center_panel(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                background: {COLORS['background']};
            }}
            QTabBar::tab {{
                background: {COLORS['surface']};
                color: {COLORS['text_secondary']};
                padding: 8px 20px;
                border: 1px solid {COLORS['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-size: 11px;
            }}
            QTabBar::tab:selected {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                font-weight: bold;
            }}
        """)

        # Tab 1: EEG Monitor
        self._visualizer = VisualizerPanel()
        self._tabs.addTab(self._visualizer, "📊  EEG Monitor")

        # Tab 2: Neuromarketing
        self._product_panel = ProductPanel()
        self._product_panel.experiment_started.connect(self._on_experiment_started)
        self._product_panel.experiment_stopped.connect(self._on_experiment_stopped)
        self._product_panel.label_applied.connect(self._on_label_applied)
        self._tabs.addTab(self._product_panel, "🛍  Neuromarketing")

        # Tab 3: Packet Inspector (hidden by default)
        self._packet_inspector = PacketInspector()

        self.setCentralWidget(self._tabs)

    # ═══════════════════════════════════════════════════════════════════
    #  Right Panel (Gauges / Bands / Blinks)
    # ═══════════════════════════════════════════════════════════════════

    def _build_right_panel(self) -> None:
        dock = QDockWidget("Metrics", self)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Gauges
        self._attention_gauge = GaugeWidget("Attention", COLORS["attention"])
        self._meditation_gauge = GaugeWidget("Meditation", COLORS["meditation"])
        layout.addWidget(self._attention_gauge)
        layout.addWidget(self._meditation_gauge)

        # Blink counter
        self._blink_counter = BlinkCounter()
        layout.addWidget(self._blink_counter)

        # Band powers
        self._band_panel = BandPowerPanel()
        layout.addWidget(self._band_panel)

        # Engagement (shown in neuromarketing mode)
        self._engagement_card = CardFrame("ENGAGEMENT")
        el = self._engagement_card.content_layout
        self._engagement_value_label = QLabel("—")
        self._engagement_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._engagement_value_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: 28px; font-weight: bold;"
        )
        el.addWidget(self._engagement_value_label)
        layout.addWidget(self._engagement_card)

        layout.addStretch()

        scroll.setWidget(container)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # ═══════════════════════════════════════════════════════════════════
    #  Status Bar
    # ═══════════════════════════════════════════════════════════════════

    def _build_status_bar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready — connect to MindWave or enable Simulation Mode")

    # ═══════════════════════════════════════════════════════════════════
    #  Connection Logic
    # ═══════════════════════════════════════════════════════════════════

    def _refresh_ports(self) -> None:
        self._port_combo.clear()
        ports = EEGReader.available_ports()
        self._port_combo.addItems(ports if ports else ["No ports found"])
        # Try to select COM4 by default
        idx = self._port_combo.findText("COM4")
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)

    def _connect(self) -> None:
        if self._reader is not None:
            return

        if self._simulation_mode:
            self._reader = EEGSimulator()
        else:
            port = self._port_combo.currentText()
            if not port or port == "No ports found":
                QMessageBox.warning(self, "No Port", "Select a valid COM port.")
                return
            self._reader = EEGReader()
            self._reader.change_port(port)

        # Wire signals
        self._reader.data_received.connect(self._on_data)
        self._reader.raw_packet_received.connect(self._on_raw_packet)
        self._reader.connection_changed.connect(self._on_connection_changed)
        self._reader.error_occurred.connect(self._on_error)
        self._reader.stats_updated.connect(self._on_stats)

        self._reader.start()
        self._reader.connect_device()

        self._refresh_timer.start()
        self._inspector_timer.start()

        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        log.info("Connect requested")

    def _disconnect(self) -> None:
        if self._reader is None:
            return

        self._refresh_timer.stop()
        self._inspector_timer.stop()

        self._reader.disconnect_device()
        self._reader.stop()
        self._reader = None

        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._status_indicator.set_status("disconnected")
        self._status_label.setText("Disconnected")
        self._status_label.setStyleSheet(f"color: {COLORS['error']}; font-size: 11px;")
        self._status_msg("Disconnected")
        log.info("Disconnected")

    def _toggle_simulation(self, enabled: bool) -> None:
        was_connected = self._reader is not None
        if was_connected:
            self._disconnect()

        self._simulation_mode = enabled
        self._mode_label.setText(f"Mode: {'Simulation' if enabled else 'Live'}")
        self._status_msg(f"Switched to {'Simulation' if enabled else 'Live'} mode")

    # ═══════════════════════════════════════════════════════════════════
    #  Data Handlers (called from reader thread via signals)
    # ═══════════════════════════════════════════════════════════════════

    def _on_data(self, data: dict) -> None:
        """Handle a decoded EEG packet."""
        # Raw EEG → waveform buffer
        raw = data.get("raw_eeg", 0)
        if raw != 0 or "raw_eeg" in data:
            self._visualizer.raw_eeg_plot.append(raw)

        # eSense metrics (only when non-zero — they come ~1/sec)
        att = data.get("attention", 0)
        med = data.get("meditation", 0)
        blink = data.get("blink_strength", 0)

        if att > 0 or med > 0:
            self._visualizer.attention_plot.append(att)
            self._visualizer.meditation_plot.append(med)
            self._attention_gauge.set_value(att)
            self._meditation_gauge.set_value(med)

        if blink > 0:
            self._visualizer.blink_plot.append(blink)
            self._blink_counter.register_blink(blink)
        else:
            # Still append 0 so the blink plot scrolls
            if att > 0 or med > 0:
                self._visualizer.blink_plot.append(0)

        # Signal quality
        sq = data.get("signal_quality", 200)
        self._signal_bar.set_quality(sq)
        self._visualizer.raw_eeg_plot.set_signal_quality(sq)

        # Band powers
        if data.get("delta", 0) > 0:
            self._band_panel.update_values(data)

        # Engagement
        if att > 0:
            engagement = self._engine.calculate(data)
            self._engagement_value_label.setText(f"{engagement:.1f}")

            # Update product panel if experiment active
            if self._product_panel.is_experiment_active:
                session = self._engine.current_session
                stats = session.summary() if session else None
                self._product_panel.update_engagement(engagement, stats)

                # Enrich data for neuro CSV
                data["engagement_score"] = engagement
                data["product_name"] = self._product_panel.current_product_name or ""
                data["label"] = self._product_panel.current_label

        # Recording
        self._recorder.enqueue(data)

    def _on_raw_packet(self, raw_bytes: bytes, decoded: dict) -> None:
        self._packet_inspector.update_packet(raw_bytes, decoded)

    def _on_connection_changed(self, connected: bool, port: str) -> None:
        if connected:
            status = "simulation" if self._simulation_mode else "connected"
            self._status_indicator.set_status(status)
            self._status_label.setText(f"Connected ({port})")
            self._status_label.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px;")
            self._status_msg(f"Connected to {port}")
        else:
            self._status_indicator.set_status("disconnected")
            self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet(f"color: {COLORS['error']}; font-size: 11px;")

    def _on_error(self, msg: str) -> None:
        self._status_msg(msg)
        log.warning("Error: %s", msg)

    def _on_stats(self, stats: dict) -> None:
        self._pkt_valid_label.setText(f"Valid: {stats.get('valid', 0):,}")
        self._pkt_invalid_label.setText(f"Invalid: {stats.get('invalid', 0):,}")
        self._pkt_total_label.setText(f"Bytes: {stats.get('total_bytes', 0):,}")
        self._packet_inspector.update_stats(stats)

    # ═══════════════════════════════════════════════════════════════════
    #  UI Refresh (20 FPS timer)
    # ═══════════════════════════════════════════════════════════════════

    def _refresh_ui(self) -> None:
        self._visualizer.refresh_all()

    def _refresh_inspector(self) -> None:
        self._packet_inspector.refresh_log()

    # ═══════════════════════════════════════════════════════════════════
    #  Recording
    # ═══════════════════════════════════════════════════════════════════

    def _start_recording(self) -> None:
        neuro = self._tabs.currentIndex() == 1  # Neuromarketing tab
        self._recorder.start_recording(neuro_mode=neuro)
        self._rec_start_btn.setEnabled(False)
        self._rec_stop_btn.setEnabled(True)
        self._rec_status_label.setText("● Recording…")
        self._rec_status_label.setStyleSheet(f"color: {COLORS['error']}; font-size: 11px;")

    def _stop_recording(self) -> None:
        path = self._recorder.stop_recording()
        self._rec_start_btn.setEnabled(True)
        self._rec_stop_btn.setEnabled(False)
        self._rec_status_label.setText("Not recording")
        self._rec_status_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        self._rec_timer_label.setText("00:00")

        if path:
            QMessageBox.information(self, "Recording Saved", f"Saved to:\n{path}")

    def _on_rows_written(self, count: int) -> None:
        self._rec_rows_label.setText(f"Rows: {count:,}")

    def _on_duration_updated(self, seconds: float) -> None:
        mins, secs = divmod(int(seconds), 60)
        self._rec_timer_label.setText(f"{mins:02d}:{secs:02d}")

    def _export_csv(self) -> None:
        if self._recorder.filepath and os.path.exists(self._recorder.filepath):
            dest = export_csv_dialog(self)
            if dest:
                shutil.copy2(self._recorder.filepath, dest)
                self._status_msg(f"Exported → {dest}")
        else:
            QMessageBox.information(self, "No Data", "No recording available to export.")

    # ═══════════════════════════════════════════════════════════════════
    #  Neuromarketing Experiment
    # ═══════════════════════════════════════════════════════════════════

    def _on_experiment_started(self, product_name: str) -> None:
        self._engine.start_session(product_name)
        if not self._recorder.is_recording:
            self._start_recording()
        self._status_msg(f"Experiment started: {product_name}")

    def _on_experiment_stopped(self) -> None:
        session = self._engine.end_session()
        rankings = self._engine.get_rankings()
        self._product_panel.update_rankings(rankings)
        self._status_msg("Experiment stopped")

    def _on_label_applied(self, product_name: str, label: str) -> None:
        self._status_msg(f"Label '{label}' applied to '{product_name}'")

    # ═══════════════════════════════════════════════════════════════════
    #  Packet Inspector Toggle
    # ═══════════════════════════════════════════════════════════════════

    def _toggle_inspector(self, visible: bool) -> None:
        if visible:
            self._tabs.addTab(self._packet_inspector, "🔍  Packet Inspector")
        else:
            idx = self._tabs.indexOf(self._packet_inspector)
            if idx >= 0:
                self._tabs.removeTab(idx)

    # ═══════════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════════

    def _status_msg(self, msg: str) -> None:
        self._statusbar.showMessage(msg, 5000)

    def _tool_btn(self, text: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface_light']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {COLORS['primary']};
                color: white;
            }}
            QPushButton:disabled {{
                color: {COLORS['text_secondary']};
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    # ═══════════════════════════════════════════════════════════════════
    #  Window State Persistence
    # ═══════════════════════════════════════════════════════════════════

    def _restore_state(self) -> None:
        geom = self._settings.value("geometry")
        state = self._settings.value("windowState")
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Save window state
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())

        # Cleanup
        if self._reader:
            self._reader.disconnect_device()
            self._reader.stop()
        if self._recorder.is_recording:
            self._recorder.stop_recording()
        self._recorder.stop()

        self._refresh_timer.stop()
        self._inspector_timer.stop()

        log.info("Dashboard closed")
        event.accept()
