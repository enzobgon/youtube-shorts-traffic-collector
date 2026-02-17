# YouTube Shorts VPN Traffic Capture

This project is part of a research workflow focused on **encrypted traffic classification using Machine Learning**.

The objective is to capture VPN-encrypted traffic (OpenVPN by default) while generating reproducible and configurable browsing behavior on YouTube Shorts.  

---

## Overview

This script:

- Starts a packet capture thread using Scapy.
- Applies a BPF filter (default: `udp port 1194`).
- Automates YouTube Shorts navigation using Selenium.
- Simulates human-like watch/skip behavior.
- Generates timestamped PCAP files per cycle.

The design ensures reproducibility and structured dataset generation for ML experiments.

---

## Features

- Reliable capture stop mechanism (works even during traffic silence).
- Configurable Shorts behavior:
  - Watch probability
  - Half-watch vs full-watch mode
  - Fallback duration handling
  - Maximum duration clamp
- Multi-cycle execution with automatic PCAP separation.
- Clean, organized logging output.

---

## Requirements

### System

- Linux (recommended)
- Root privileges to capture packets

### Python Packages

Install dependencies:

```bash
pip install scapy selenium
```

### Chrome + ChromeDriver

You must have:

- Google Chrome (or Chromium)
- ChromeDriver available in PATH

Verify:

```bash
chromedriver --version
google-chrome --version
```

---

## How to Run

The script is executed via CLI (Command Line Interface).

General syntax:

```bash
sudo python3 youtube_shorts_traffic_collector.py [OPTIONS]
```


### Core Parameters

| Flag | Description |
|------|------------|
| `-i`, `--interface` | Network interface to sniff (e.g., enp0s8) |
| `-c`, `--cycles` | Number of capture cycles |
| `-p`, `--shorts` | Number of Shorts per cycle |
| `--filter` | BPF filter (default: `udp port 1194`) |
| `--headless` | Run browser without GUI |
| `--outdir` | Output directory for PCAP files |
| `--prefix` | Prefix for generated PCAP filenames |


### Behavior Parameters (Human-like Control)

| Flag | Description |
|------|------------|
| `--watch-prob` | Probability (0.0–1.0) of watching a Short |
| `--half-watch-prob` | Probability (0.0–1.0) of half-watch when watching |
| `--max-duration` | Maximum duration clamp in seconds |
| `--fallback-duration` | Duration used if video duration is unavailable |

---

### Example

Run a single cycle with 15 Shorts:

```bash
sudo python3 youtube_shorts_traffic_collector.py -i enp0s8 -c 1 -p 15
```

This configuration:

- Captures traffic on interface `enp0s8`
- Executes 1 capture cycle
- Watches/skips 15 Shorts
- Saves one PCAP file

---

### Complete Example

```bash
sudo python3 youtube_shorts_traffic_collector.py \
    -i enp0s8 \
    -c 3 \
    -p 20 \
    --watch-prob 0.6 \
    --half-watch-prob 0.4 \
    --max-duration 120 \
    --fallback-duration 30 \
    --headless
```

This configuration:

- Runs 3 capture cycles
- Processes 20 Shorts per cycle
- Watches approximately 60% of Shorts
- Among watched Shorts, ~40% are half-watched

## Experimental Recommendation

For reproducible datasets:

- Keep behavior parameters constant across runs.
- Vary only one parameter at a time when conducting controlled experiments.
- Document CLI parameters used for each dataset.
- Separate datasets by service (e.g., WEB vs Streaming).

---

## Disclaimer

This tool is intended for academic and authorized research purposes only.  
Only capture traffic on networks and systems where you have explicit permission.
