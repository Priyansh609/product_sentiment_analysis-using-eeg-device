# MindWave EEG Visualizer & Neuromarketing Dashboard

Real-time EEG visualization and product sentiment analysis dashboard for the **NeuroSky MindWave Mobile** headset.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Features

- **Live EEG Monitoring** — 10-second scrolling raw waveform at 512 Hz
- **eSense Metrics** — Real-time attention, meditation, and blink tracking
- **EEG Band Powers** — Delta, theta, alpha, beta, gamma visualization
- **Neuromarketing Mode** — Product engagement scoring and ranking
- **CSV Recording** — Timestamped data export with ML labels
- **Simulation Mode** — Full dashboard testing without hardware
- **Packet Inspector** — Developer tool for raw ThinkGear packet analysis

---

## Hardware Requirements

| Item | Details |
|------|---------|
| Headset | NeuroSky MindWave Mobile (Original) |
| Connection | Bluetooth SPP |
| OS | Windows 10 / 11 |
| Default Port | COM4 (configurable) |
| Baud Rate | 57600 |

---

## Installation

### 1. Clone the repository

```bash
cd capstone_project
```

### 2. Create virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r mindwave_visualizer/requirements.txt
```

---

## Usage

### Launch the application

```bash
python mindwave_visualizer/main.py
```

### Quick Start

1. **Pair** your MindWave Mobile via Windows Bluetooth settings
2. **Select** the COM port from the dropdown (usually COM4)
3. Click **⚡ Connect**
4. Observe real-time EEG data on the dashboard

### Simulation Mode

To test without hardware:
- Menu → **Mode** → check **Simulation Mode**
- Click **⚡ Connect**

### Recording Data

1. Click **⏺ Record** to start CSV recording
2. Click **⏹ Stop** to save
3. Files are saved to `data/recordings/` with timestamped filenames

### Neuromarketing Experiment

1. Switch to the **🛍 Neuromarketing** tab
2. Click **📁 Load Images** to add product images
3. Set experiment duration
4. Click **▶ Start Experiment** to begin recording engagement
5. After testing all products, view **rankings** on the right panel
6. Apply ML labels: *Interested*, *Neutral*, or *Not Interested*

---

## Architecture

```
MindWave Mobile → Bluetooth SPP → Serial Reader Thread
                                        ↓
                                  ThinkGear Decoder
                                        ↓
                                  Decoded Data Queue
                                        ↓
                          ┌─────────────┼─────────────┐
                          ↓             ↓             ↓
                    UI Dashboard   CSV Recorder   Engagement Engine
```

### Producer-Consumer Model

| Thread | Role |
|--------|------|
| `EEGReader` (QThread) | Reads serial bytes, feeds ThinkGear parser |
| `Recorder` (QThread) | Writes decoded packets to CSV |
| Main Thread | Updates UI at 20 FPS via QTimer |

---

## Project Structure

```
mindwave_visualizer/
├── main.py                 # Entry point
├── config.py               # Central configuration
├── eeg_reader.py           # Serial communication (QThread)
├── packet_decoder.py       # ThinkGear protocol parser
├── eeg_processor.py        # Engagement engine
├── recorder.py             # CSV writer (QThread)
├── simulator.py            # Synthetic EEG generator
├── logger.py               # Rotating file logger
├── requirements.txt
│
├── ui/
│   ├── dashboard.py        # Main window layout
│   ├── widgets.py          # Custom gauges & indicators
│   ├── visualizer.py       # PyQtGraph plots
│   ├── packet_inspector.py # Developer hex viewer
│   ├── product_panel.py    # Neuromarketing panel
│   └── dialogs.py          # About / error dialogs
│
├── data/
│   └── recordings/         # CSV output directory
│
├── tests/
│   ├── test_decoder.py     # Packet decoder tests
│   ├── test_reader.py      # Serial reader tests
│   └── test_recorder.py    # CSV recorder tests
│
└── logs/                   # Rotating log files
```

---

## ThinkGear Protocol

The parser handles these packet codes:

| Code | Type | Description |
|------|------|-------------|
| `0x02` | Poor Signal | 0 = good, 200 = no contact |
| `0x04` | Attention | eSense 0–100 |
| `0x05` | Meditation | eSense 0–100 |
| `0x16` | Blink | Strength 1–255 |
| `0x80` | Raw Wave | Signed 16-bit @ 512 Hz |
| `0x83` | ASIC Power | 8 × 3-byte band values |

---

## Engagement Score

```
engagement = 0.5 × attention + 0.3 × beta_ratio + 0.2 × blink_score

beta_ratio  = (low_beta + high_beta) / (low_alpha + high_alpha) × 100
blink_score = max(0, 100 − blink_rate_per_min × 10)
```

---

## Running Tests

```bash
cd mindwave_visualizer
python -m pytest tests/ -v
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| COM port not found | Check Bluetooth pairing; try a different COM port |
| No signal (quality = 200) | Ensure ear clip and forehead sensor have skin contact |
| UI freezing | Should not happen — file a bug if it does |
| Import errors | Ensure virtual environment is activated and dependencies installed |
| Permission denied on COM port | Close other apps using the port; run as administrator |

---

## CSV Output Format

### Standard Mode

```csv
timestamp,raw_eeg,attention,meditation,signal_quality,blink_strength,delta,theta,low_alpha,high_alpha,low_beta,high_beta,low_gamma,high_gamma
```

### Neuromarketing Mode

```csv
timestamp,raw_eeg,attention,meditation,signal_quality,blink_strength,delta,theta,low_alpha,high_alpha,low_beta,high_beta,low_gamma,high_gamma,product_name,engagement_score,label
```

---

## License

MIT License — free for academic and research use.
