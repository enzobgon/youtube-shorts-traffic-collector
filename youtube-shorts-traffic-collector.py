#!/usr/bin/env python3
# YouTube Shorts VPN Traffic Collector (OpenVPN by default)

# Capture encrypted VPN traffic while simulating "human-like" navigation on YouTube Shorts.
# Runs packet capture (Scapy) in a background thread while Selenium watches/skips Shorts.

# Key points:
# - Reliable stop behavior: sniff() may block if traffic is silent, so we loop with timeout.
# - Configurable behavior via CLI flags (watch probability, half/full mode, pauses, shorts per cycle).

from __future__ import annotations

from dataclasses import dataclass  # Used to group "Behavior" configs.
from datetime import datetime
import argparse  # CLI params.
import logging
import os  # mkdir/root user.
import random
import threading
import time
from typing import Tuple, Optional, List

from scapy.all import sniff, wrpcap  # sniff() for capture / wrpcap() to write .pcap files.

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException


# Logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("youtube_shorts_traffic_collector")

# Global flag used to stop capture thread.
stop_capture_flag = threading.Event()


# Aux.
def rand_range(r: Tuple[float, float]) -> float:
    a, b = r
    return random.uniform(a, b)


def randint_range(r: Tuple[int, int]) -> int:
    a, b = r
    return random.randint(a, b)


# Default human-like behavior (adjust via CLI).
@dataclass(frozen=True)
class Behavior:
    # Page load / initial settle time.
    page_load_wait_s: Tuple[float, float] = (2.0, 4.5)

    # Between-actions pause.
    between_actions_s: Tuple[float, float] = (0.8, 2.5)

    # Probability to WATCH vs SKIP a short.
    watch_probability: float = 0.35

    # When watching, probability to watch only half (otherwise full).
    half_watch_probability: float = 0.45

    # If duration is unknown/invalid, fallback watch duration.
    fallback_duration_s: float = 30.0

    # Safety clamp for duration (avoid very long videos).
    max_duration_s: float = 120.0

    # Extra grace time for full-watch loop.
    full_watch_grace_s: float = 10.0

    # Small idle moments.
    idle_probability: float = 0.12
    idle_time_s: Tuple[float, float] = (2.0, 6.0)


# Create the default Selenium driver.
def build_driver(headless: bool, chromedriver_path: Optional[str]) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--mute-audio")
    options.add_argument("--lang=pt-BR")

    service = Service(chromedriver_path) if chromedriver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1280, 720)
    return driver


# Packet capture.
def capture_packets(interface: str, filename: str, bpf_filter: str, poll_timeout_s: float = 1.0) -> None:
    # Capture packets on the given interface using a BPF filter until stop_capture_flag is set.
    # NOTE: sniff(stop_filter=...) only checks stop when packets arrive -> may hang on silence.
    # Looping with timeout makes stopping reliable.

    logger.info("Starting capture on interface=%s | filter='%s'", interface, bpf_filter)
    captured: list = []

    try:
        while not stop_capture_flag.is_set():
            pkts = sniff(iface=interface, filter=bpf_filter, timeout=poll_timeout_s)
            if pkts:
                captured.extend(pkts)

        wrpcap(filename, captured)
        logger.info("Capture finished. Saved %d packets to %s", len(captured), filename)

    except Exception as e:
        logger.exception("Capture error: %s", e)


# Shorts simulation.
def maybe_idle(behavior: Behavior) -> None:
    # Occasionally pause to simulate human idle time.
    if random.random() < behavior.idle_probability:
        t = rand_range(behavior.idle_time_s)
        logger.info("  Idle for %.2fs (human pause)", t)
        time.sleep(t)


def open_shorts(driver: webdriver.Chrome, behavior: Behavior) -> None:
    # Open YouTube Shorts page and wait for a video element.
    logger.info("Opening YouTube Shorts...")
    driver.get("https://www.youtube.com/shorts")

    time.sleep(rand_range(behavior.page_load_wait_s))
    wait = WebDriverWait(driver, 20)

    # Try to accept cookies (PT/EN).
    try:
        cookie_button = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(., 'Aceitar') or contains(., 'Accept')]"
            ))
        )
        cookie_button.click()
        time.sleep(1.5)
    except Exception:
        pass

    # Wait for video to appear.
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "video")))
    logger.info("Shorts loaded.")


def ensure_video_playing(driver: webdriver.Chrome) -> None:
    # Force play (muted).
    driver.execute_script("""
        const v = document.querySelector('video');
        if (v) { v.muted = true; try { v.play(); } catch(e) {} }
    """)


def get_video_duration(driver: webdriver.Chrome) -> float:
    duration = driver.execute_script("""
        const v = document.querySelector('video');
        return v ? v.duration : 0;
    """)
    try:
        return float(duration) if duration else 0.0
    except Exception:
        return 0.0


def get_video_current_time(driver: webdriver.Chrome) -> float:
    current = driver.execute_script("""
        const v = document.querySelector('video');
        return v ? v.currentTime : 0;
    """)
    try:
        return float(current) if current else 0.0
    except Exception:
        return 0.0


def next_short(driver: webdriver.Chrome) -> None:
    # Go to next short.
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)


def watch_short(driver: webdriver.Chrome, behavior: Behavior, mode: str) -> None:
    # Watch a short (half or full).
    ensure_video_playing(driver)

    duration = get_video_duration(driver)
    if duration <= 0 or duration > behavior.max_duration_s:
        duration = behavior.fallback_duration_s

    if mode == "half":
        t = (duration / 2.0) * random.uniform(0.8, 1.2)
        logger.info("  Watch (half) ~%.1fs", t)
        time.sleep(t)
        return

    # Full watch: loop by currentTime.
    logger.info("  Watch (full) ~%.1fs", duration)
    start = time.time()
    max_wait = duration + behavior.full_watch_grace_s

    while True:
        if get_video_current_time(driver) >= duration - 0.5:
            break
        if time.time() - start > max_wait:
            break
        time.sleep(1.0)


def simulate_shorts(cycle_shorts: int, behavior: Behavior, headless: bool, chromedriver_path: Optional[str]) -> None:
    driver = build_driver(headless=headless, chromedriver_path=chromedriver_path)

    try:
        open_shorts(driver, behavior)
        maybe_idle(behavior)

        for i in range(cycle_shorts):
            logger.info("Short %d/%d", i + 1, cycle_shorts)

            # Decide watch vs skip.
            do_watch = (random.random() < behavior.watch_probability)

            if do_watch:
                mode = "half" if (random.random() < behavior.half_watch_probability) else "full"
                watch_short(driver, behavior, mode)
            else:
                logger.info("  Skip")

            # Move to next.
            next_short(driver)
            time.sleep(rand_range(behavior.between_actions_s))
            maybe_idle(behavior)

        logger.info("Shorts simulation finished.")

    finally:
        driver.quit()


# CLI.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture VPN traffic (OpenVPN by default) while simulating YouTube Shorts navigation."
    )

    # Core capture options.
    parser.add_argument("-i", "--interface", default="enp0s8", help="Network interface to sniff (e.g., enp0s8)")
    parser.add_argument("--filter", default="udp port 1194", help="BPF filter (default: 'udp port 1194')")
    parser.add_argument("-c", "--cycles", type=int, default=5, help="Number of capture cycles (default: 5)")
    parser.add_argument("-p", "--shorts", type=int, default=20, help="Number of Shorts per cycle (default: 20)")

    # Output naming.
    parser.add_argument("--outdir", default="capturas", help="Output directory for PCAP files")
    parser.add_argument("--prefix", default="shorts_traffic", help="PCAP filename prefix (default: shorts_traffic)")

    # Selenium options.
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--chromedriver-path", default=None, help="Custom chromedriver path (optional)")

    # Behavior knobs.
    parser.add_argument("--watch-prob", type=float, default=0.35, help="Probability (0..1) of watching a Short (default: 0.35)")
    parser.add_argument("--half-watch-prob", type=float, default=0.45, help="Probability (0..1) of half-watch when watching (default: 0.45)")
    parser.add_argument("--max-duration", type=float, default=120.0, help="Max duration clamp in seconds (default: 120)")
    parser.add_argument("--fallback-duration", type=float, default=30.0, help="Fallback duration if video duration is invalid (default: 30)")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if os.geteuid() != 0:
        logger.error("Run with sudo: sudo python3 youtube_shorts_traffic_collector.py ...")
        raise SystemExit(1)

    os.makedirs(args.outdir, exist_ok=True)

    behavior = Behavior(
        watch_probability=max(0.0, min(1.0, args.watch_prob)),
        half_watch_probability=max(0.0, min(1.0, args.half_watch_prob)),
        max_duration_s=max(5.0, args.max_duration),
        fallback_duration_s=max(5.0, args.fallback_duration),
    )

    try:
        for c in range(args.cycles):
            logger.info("=" * 60)
            logger.info("Cycle %d/%d", c + 1, args.cycles)
            logger.info("=" * 60)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pcap_path = os.path.join(args.outdir, f"{args.prefix}_{timestamp}_c{c+1:03d}.pcap")

            stop_capture_flag.clear()

            capture_thread = threading.Thread(
                target=capture_packets,
                args=(args.interface, pcap_path, args.filter),
                daemon=True,
            )
            capture_thread.start()

            # Ensure capture is active.
            time.sleep(2)

            simulate_shorts(
                cycle_shorts=args.shorts,
                behavior=behavior,
                headless=args.headless,
                chromedriver_path=args.chromedriver_path,
            )

            stop_capture_flag.set()
            logger.info("Waiting capture thread to finish...")
            capture_thread.join()

            logger.info("✓ Cycle %d completed successfully!", c + 1)

            if c < args.cycles - 1:
                time.sleep(3)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C).")
        stop_capture_flag.set()

    except Exception as e:
        logger.exception("Runtime error: %s", e)
        stop_capture_flag.set()

    finally:
        logger.info("Done.")


if __name__ == "__main__":
    main()
