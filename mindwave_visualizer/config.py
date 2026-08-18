"""
MindWave Visualizer — Central Configuration
=============================================
All tuneable constants live here so every other module imports from one place.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Serial Communication ───────────────────────────────────────────────────
DEFAULT_PORT = "COM4"
DEFAULT_BAUD = 57600
SERIAL_TIMEOUT = 1  # seconds

# ── ThinkGear Serial Stream Protocol ──────────────────────────────────────
SYNC_BYTE = 0xAA
MAX_PAYLOAD_LENGTH = 169  # must be < SYNC_BYTE

# Data-row codes (single-byte value)
CODE_POOR_SIGNAL    = 0x02
CODE_ATTENTION      = 0x04
CODE_MEDITATION     = 0x05
CODE_BLINK          = 0x16

# Data-row codes (multi-byte value — high bit set)
CODE_RAW_WAVE       = 0x80
CODE_ASIC_EEG_POWER = 0x83

# ── Sampling ──────────────────────────────────────────────────────────────
RAW_EEG_RATE = 512   # raw wave packets per second
METRIC_RATE  = 1     # attention / meditation packets per second

# ── Visualization ─────────────────────────────────────────────────────────
TARGET_FPS           = 20
UPDATE_INTERVAL_MS   = 1000 // TARGET_FPS          # ≈50 ms
RAW_EEG_WINDOW_SEC   = 10
METRIC_WINDOW_SEC    = 60
RAW_BUFFER_SIZE      = RAW_EEG_RATE * RAW_EEG_WINDOW_SEC   # 5 120
METRIC_BUFFER_SIZE   = METRIC_WINDOW_SEC                    # 60

# ── Auto-Reconnect ────────────────────────────────────────────────────────
MAX_RECONNECT_ATTEMPTS   = 10
INITIAL_RECONNECT_DELAY  = 1    # seconds
MAX_RECONNECT_DELAY      = 30   # seconds

# ── Recording ─────────────────────────────────────────────────────────────
RECORDING_DIR            = os.path.join(BASE_DIR, "data", "recordings")
RECORDING_FLUSH_INTERVAL = 1.0  # seconds

# ── Logging ───────────────────────────────────────────────────────────────
LOG_DIR          = os.path.join(BASE_DIR, "logs")
LOG_MAX_BYTES    = 5 * 1024 * 1024   # 5 MB per file
LOG_BACKUP_COUNT = 5

# ── Qt Settings persistence ──────────────────────────────────────────────
SETTINGS_ORG = "NeuroSkyVisualizer"
SETTINGS_APP = "MindWaveVisualizer"

# ── Engagement Engine ─────────────────────────────────────────────────────
ENGAGEMENT_WEIGHT_ATTENTION = 0.5
ENGAGEMENT_WEIGHT_BETA      = 0.3
ENGAGEMENT_WEIGHT_BLINK     = 0.2

# ── CSV Columns ───────────────────────────────────────────────────────────
CSV_COLUMNS = [
    "timestamp", "raw_eeg", "attention", "meditation",
    "signal_quality", "blink_strength",
    "delta", "theta", "low_alpha", "high_alpha",
    "low_beta", "high_beta", "low_gamma", "high_gamma",
]

NEURO_CSV_COLUMNS = CSV_COLUMNS + ["product_name", "engagement_score", "label"]

LABELS = ["Interested", "Neutral", "Not Interested"]

# ── EEG Band Names (ordered) ─────────────────────────────────────────────
BAND_NAMES = [
    "delta", "theta", "low_alpha", "high_alpha",
    "low_beta", "high_beta", "low_gamma", "high_gamma",
]

# ── Theme Colours ─────────────────────────────────────────────────────────
COLORS = {
    # Surfaces
    "background":      "#0d1117",
    "surface":         "#161b22",
    "surface_light":   "#21262d",
    "border":          "#30363d",
    "panel_bg":        "#0d1117",

    # Accent
    "primary":         "#58a6ff",
    "accent":          "#f78166",

    # Text
    "text":            "#e6edf3",
    "text_secondary":  "#8b949e",

    # Semantic
    "success":         "#3fb950",
    "warning":         "#d29922",
    "error":           "#f85149",

    # Metrics
    "attention":       "#58a6ff",
    "meditation":      "#bc8cff",
    "raw_eeg":         "#7ee787",
    "blink":           "#ffa657",

    # Signal quality
    "signal_good":     "#3fb950",
    "signal_ok":       "#d29922",
    "signal_bad":      "#f85149",

    # EEG bands
    "delta":           "#f85149",
    "theta":           "#ffa657",
    "low_alpha":       "#e3b341",
    "high_alpha":      "#7ee787",
    "low_beta":        "#58a6ff",
    "high_beta":       "#79c0ff",
    "low_gamma":       "#bc8cff",
    "high_gamma":      "#f778ba",
}
