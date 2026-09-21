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
    QApplication, QSplitter, QScrollArea, QSizePolicy, QLineEdit,
)

from config import (
    COLORS, SETTINGS_ORG, SETTINGS_APP, UPDATE_INTERVAL_MS,
    DEFAULT_PARTICIPANT_ID,
)
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
        # True when the CURRENT trial owns its own dedicated recording
        # file (named "<ParticipantID>_<ProductName>.csv"), as opposed to
        # a manual/general recording session already being in progress
        # when the trial started (in which case the trial's rows flush
        # into that existing file instead). Determines whether trial-end
        # should also stop the recorder.
        self._trial_uses_own_file = False
        # Rows recorded during the CURRENT trial, held back from the
        # recorder until the participant confirms a label at trial end.
        # Live-streaming rows to the recorder while a trial is active
        # can't work here: the label isn't known until the trial is over,
        # and by the time it IS known the "is experiment active" window
        # has already closed, so no row would ever receive it. Buffering
        # and stamping every row with the final label before flushing
        # avoids that race entirely, at the cost of a short delay (one
        # trial's worth of rows) before they hit disk.
        self._trial_buffer: list[dict] = []

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

        # ── Participant section ──────────────────────────────────────
        participant_card = CardFrame("PARTICIPANT")
        pl = participant_card.content_layout

        pid_row = QHBoxLayout()
        pid_lbl = QLabel("ID:")
        pid_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        self._participant_input = QLineEdit()
        self._participant_input.setPlaceholderText("e.g. P001")
        self._participant_input.setText(
            self._settings.value("participant_id", DEFAULT_PARTICIPANT_ID)
        )
        self._participant_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                padding: 4px;
                font-size: 11px;
            }}
        """)
        self._participant_input.editingFinished.connect(self._on_participant_id_changed)
        pid_row.addWidget(pid_lbl)
        pid_row.addWidget(self._participant_input, stretch=1)
        pl.addLayout(pid_row)

        layout.addWidget(participant_card)

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
    #  Participant
    # ═══════════════════════════════════════════════════════════════════

    @property
    def participant_id(self) -> str:
        """Current participant ID, falling back to the default if blank."""
        pid = self._participant_input.text().strip()
        return pid if pid else DEFAULT_PARTICIPANT_ID

    def _on_participant_id_changed(self) -> None:
        """Persist the participant ID as soon as the field loses focus."""
        pid = self.participant_id
        self._settings.setValue("participant_id", pid)
        self._status_msg(f"Participant set to '{pid}'")
        log.info("Participant ID set to '%s'", pid)

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
        # Stamp participant_id on every row, unconditionally — unlike
        # product_name/label/engagement_score (added later, only while an
        # experiment is active), participant_id applies to the whole
        # session regardless of whether a product trial is running.
        data["participant_id"] = self.participant_id

        # Raw EEG → waveform buffer
        raw = data.get("raw_eeg", 0)
        if raw != 0 or "raw_eeg" in data:
            self._visualizer.raw_eeg_plot.append(raw)

        # eSense metrics (only when non-zero — they come ~1/sec)
        # NOTE: these fields always exist in the dict now, but hold None
        # until the first ASIC/eSense packet arrives (see packet_decoder's
        # forward-fill fix) — `.get(key, 0)` does NOT catch that, since the
        # key is present. `or 0` correctly treats None the same as missing.
        att = data.get("attention") or 0
        med = data.get("meditation") or 0
        blink = data.get("blink_strength") or 0

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
        if (data.get("delta") or 0) > 0:
            self._band_panel.update_values(data)

        # Engagement — only computable once real eSense data is present
        if att > 0 and self._product_panel.is_experiment_active:
            engagement = self._engine.calculate(data)
            self._engagement_value_label.setText(f"{engagement:.1f}")
            session = self._engine.current_session
            stats = session.summary() if session else None
            self._product_panel.update_engagement(engagement, stats)
            data["engagement_score"] = engagement
        elif att > 0:
            engagement = self._engine.calculate(data)
            self._engagement_value_label.setText(f"{engagement:.1f}")

        # Recording
        if self._product_panel.is_experiment_active:
            # product_name is known now; label is NOT — it's only
            # confirmed when the trial ends (see _on_experiment_stopped).
            # Every row for this trial is buffered here rather than
            # enqueued immediately, then flushed all at once, stamped
            # with the real label, once the participant answers.
            # Stamping a blank/guessed label live is exactly the bug
            # this buffering replaces.
            data["product_name"] = self._product_panel.current_product_name or ""
            self._trial_buffer.append(data)
        else:
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
        if self.participant_id == DEFAULT_PARTICIPANT_ID:
            reply = QMessageBox.question(
                self, "No Participant ID",
                "Participant ID is still set to the default "
                f"('{DEFAULT_PARTICIPANT_ID}'). Recording without a real "
                "participant ID makes this session hard to identify later.\n\n"
                "Start recording anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                log.info("Recording NOT started — participant ID warning declined")
                return

        neuro = self._tabs.currentIndex() == 1  # Neuromarketing tab
        log.info("Starting recording: tab_index=%d neuro_mode=%s",
                  self._tabs.currentIndex(), neuro)
        self._recorder.start_recording(neuro_mode=neuro)
        log.info("Recorder.is_recording after start_recording(): %s, filepath=%s",
                  self._recorder.is_recording, self._recorder.filepath)
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
        self._trial_buffer = []  # start this trial with a clean buffer

        # Every trial gets its OWN dedicated recording, named
        # "<ParticipantID>_<ProductName>.csv" and always both started and
        # stopped by the trial itself — this is a separate concern from
        # the manual ⏺ Record button, which is for longer, free-form
        # sessions. If manual recording also happens to be running (e.g.
        # to capture a continuous multi-product baseline), that keeps
        # running untouched; the trial's rows still go to their own file
        # via the buffer-and-flush mechanism below, not to the manual one.
        if self._recorder.is_recording:
            # A manual/general recording is already active. Recorder only
            # supports one open file at a time, so let that session keep
            # owning the file — the trial's rows are still captured via
            # the buffer below and will be labeled and flushed into it
            # under the SAME manual file rather than a new per-trial one.
            self._trial_uses_own_file = False
            log.info("Experiment started for '%s'; manual recording already "
                      "active, trial rows will flush into that file",
                      product_name)
        else:
            filename = f"{self.participant_id}_{product_name}"
            neuro = True  # trials always need product_name/label/engagement columns
            log.info("Starting per-trial recording: filename=%s", filename)
            self._recorder.start_recording(neuro_mode=neuro, filename_override=filename)
            self._trial_uses_own_file = True
            if not self._recorder.is_recording:
                log.warning("Per-trial recording failed to start for '%s'", filename)

        self._status_msg(f"Experiment started: {product_name}")

    def _on_experiment_stopped(self, product_name: str, label: str) -> None:
        session = self._engine.end_session()
        rankings = self._engine.get_rankings()
        self._product_panel.update_rankings(rankings)

        # Stamp every buffered row from this trial with the participant's
        # actual, now-confirmed answer, then flush them to the recorder
        # in order. This is the step that fixes the "label always blank"
        # bug: rows are held exactly until this point, when the real
        # label is finally known, rather than being written earlier with
        # nothing (or a stale/guessed value) in the label column.
        for row in self._trial_buffer:
            row["product_name"] = row.get("product_name") or product_name
            row["label"] = label
            self._recorder.enqueue(row)
        n_rows = len(self._trial_buffer)
        self._trial_buffer = []

        log.info("Trial '%s' ended -> label='%s', flushing %d buffered row(s), "
                  "recorder.is_recording=%s",
                  product_name, label or "(unlabeled)", n_rows, self._recorder.is_recording)

        if self._trial_uses_own_file and self._recorder.is_recording:
            path = self._recorder.stop_recording()
            self._rec_start_btn.setEnabled(True)
            self._rec_stop_btn.setEnabled(False)
            self._rec_status_label.setText("Not recording")
            self._rec_status_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 11px;"
            )
            self._rec_timer_label.setText("00:00")
            self._status_msg(f"Trial saved: {os.path.basename(path) if path else ''}")
        else:
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