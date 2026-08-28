"""Windows Wi-Fi proximity scanner.

Reads the Wi-Fi scan cache via `netsh` and estimates how far away each access
point is from its signal strength. Distances are model output, not measurements.
"""

import ctypes
import math
import os
import re
import subprocess
import sys
import time

# --- Tuning -----------------------------------------------------------------

REFRESH_SECONDS = 0.5


RSSI_AT_1M_2400MHZ = -40.0


PATH_LOSS_EXPONENT = 1.5


SHADOWING_DB = 6.0

# Exponential moving average weight for new samples. Lower = smoother.
EMA_ALPHA = 0.4


MAX_RSSI_DBM = -50.0


FORGET_AFTER_SECONDS = 30.0



BSSID_RE = re.compile(r"BSSID\s+\d+\s*:\s*(\S+)")
SSID_RE = re.compile(r"SSID\s+\d+\s*:\s*(.*)")
SIGNAL_RE = re.compile(r"Signal\s*:\s*(\d+)\s*%")
CHANNEL_RE = re.compile(r"Channel\s*:\s*(\d+)")
BAND_RE = re.compile(r"Band\s*:\s*([\d.]+)\s*GHz")


def _decode(raw):
    """netsh writes in the console codepage, not UTF-8."""
    for codec in ("oem", "utf-8"):
        try:
            return raw.decode(codec, errors="replace")
        except LookupError:
            continue
    return raw.decode("latin-1", errors="replace")


def run_netsh():
    proc = subprocess.run(
        ["netsh", "wlan", "show", "networks", "mode=bssid"],
        capture_output=True,
    )
    out = _decode(proc.stdout)
    if proc.returncode != 0:
        raise RuntimeError((_decode(proc.stderr) or out).strip())
    return out


def parse_networks(text):
    """Return one record per BSSID (radio), not per SSID."""
    networks = []
    ssid = None
    current = None

    def flush():
        nonlocal current
        if current is not None:
            networks.append(current)
            current = None

    for line in text.splitlines():
        line = line.strip()

        match = BSSID_RE.match(line)
        if match:
            flush()
            current = {
                "ssid": ssid,
                "bssid": match.group(1).lower(),
                "signal": None,
                "channel": None,
                "band": None,
            }
            continue

        match = SSID_RE.match(line)
        if match:
            # Flush first: the previous SSID's last BSSID is still open here.
            flush()
            ssid = match.group(1).strip()
            continue

        if current is None:
            continue

        match = SIGNAL_RE.match(line)
        if match:
            current["signal"] = int(match.group(1))
            continue

        match = BAND_RE.match(line)
        if match:
            current["band"] = float(match.group(1))
            continue

        match = CHANNEL_RE.match(line)
        if match:
            current["channel"] = int(match.group(1))

    flush()
    return [n for n in networks if n["signal"] is not None]





def rssi_from_percent(percent):
    """Microsoft maps signal quality 0-100 linearly onto -100..-50 dBm."""
    return percent / 2.0 - 100.0


def frequency_mhz(channel, band_ghz):
    if channel is None:
        return None
    if band_ghz is None:
        band = 2.4 if channel <= 14 else 5.0
    elif band_ghz < 3.0:
        band = 2.4
    elif band_ghz < 6.0:
        band = 5.0
    else:
        band = 6.0

    if band == 2.4:
        return 2484 if channel == 14 else 2412 + 5 * (channel - 1)
    if band == 5.0:
        return 5000 + 5 * channel
    return 5935 if channel == 2 else 5950 + 5 * channel


def reference_rssi(freq_mhz):
    """Free-space loss scales with frequency, so 5 GHz reads ~7 dB weaker."""
    if freq_mhz is None:
        return RSSI_AT_1M_2400MHZ
    return RSSI_AT_1M_2400MHZ - 20.0 * math.log10(freq_mhz / 2437.0)


def estimate_distance(rssi, freq_mhz):
    exponent = (reference_rssi(freq_mhz) - rssi) / (10.0 * PATH_LOSS_EXPONENT)
    return 10.0**exponent


def range_factor():
    return 10.0 ** (SHADOWING_DB / (10.0 * PATH_LOSS_EXPONENT))




WIDTH = 96


def enable_ansi():
    if os.name != "nt":
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def format_metres(value):
    if value < 10:
        return f"{value:.1f}"
    return f"{value:.0f}"


def format_distance(rssi, freq_mhz, saturated):
    distance = estimate_distance(rssi, freq_mhz)
    if saturated:
        return f"< {format_metres(distance)} m"
    factor = range_factor()
    return f"{format_metres(distance / factor)}-{format_metres(distance * factor)} m"


def band_label(freq_mhz):
    if freq_mhz is None:
        return "?"
    if freq_mhz < 3000:
        return "2.4"
    if freq_mhz < 5925:
        return "5"
    return "6"


def render(rows, unchanged_for):
    lines = [
        "WI-FI PROXIMITY SCANNER",
        "=" * WIDTH,
        "",
        f"{'SSID':<26}{'BSSID':<19}{'Signal':>7}{'RSSI':>9}"
        f"{'Est. distance':>18}{'Band':>7}{'Ch':>5}",
        "-" * WIDTH,
    ]

    if not rows:
        lines.append("No networks in the scan cache.")
    for row in rows:
        name = row["ssid"] or "<hidden>"
        if len(name) > 25:
            name = name[:24] + "\u2026"
        lines.append(
            f"{name:<26}"
            f"{row['bssid']:<19}"
            f"{row['signal']:>6}%"
            f"{row['rssi']:>8.0f}dBm"
            f"{row['distance']:>18}"
            f"{row['band']:>7}"
            f"{row['channel']:>5}"
        )

    stale = ""
    if unchanged_for >= REFRESH_SECONDS * 2:
        stale = f"  (cache unchanged for {unchanged_for:.0f}s)"

    lines += [
        "",
        f"Refreshing every {REFRESH_SECONDS}s. Ctrl+C to stop.{stale}",
        "",
        "Distances are estimated from signal strength, not measured. Walls,",
        "bodies and antenna orientation move them by a factor of two or more.",
        f"A '<' row sits at 100% signal (above {MAX_RSSI_DBM:.0f} dBm): "
        f"upper bound only.",
    ]
    return "\n".join(lines)





def build_rows(networks, smoothed, now):
    rows = []
    for network in networks:
        bssid = network["bssid"]
        freq = frequency_mhz(network["channel"], network["band"])
        sample = rssi_from_percent(network["signal"])

        previous = smoothed.get(bssid)
        rssi = sample if previous is None else previous[0] + EMA_ALPHA * (sample - previous[0])
        smoothed[bssid] = (rssi, now)

        rows.append(
            {
                "ssid": network["ssid"],
                "bssid": bssid,
                "signal": network["signal"],
                "rssi": rssi,
                "distance": format_distance(rssi, freq, network["signal"] >= 100),
                "band": band_label(freq),
                "channel": network["channel"] if network["channel"] is not None else "?",
            }
        )

    for bssid, (_, seen) in list(smoothed.items()):
        if now - seen > FORGET_AFTER_SECONDS:
            del smoothed[bssid]

    rows.sort(key=lambda row: (-row["rssi"], row["bssid"]))
    return rows


def main():
    if os.name != "nt":
        sys.exit("This script needs Windows: it reads `netsh wlan`.")

    enable_ansi()
    smoothed = {}
    last_fingerprint = None
    last_change = time.monotonic()

    while True:
        now = time.monotonic()
        try:
            networks = parse_networks(run_netsh())
        except FileNotFoundError:
            sys.exit("netsh not found on PATH.")
        except RuntimeError as error:
            sys.stdout.write("\033[H\033[J" + f"netsh failed: {error}\n")
            sys.stdout.flush()
            time.sleep(REFRESH_SECONDS)
            continue

        fingerprint = tuple(sorted((n["bssid"], n["signal"]) for n in networks))
        if fingerprint != last_fingerprint:
            last_fingerprint = fingerprint
            last_change = now

        rows = build_rows(networks, smoothed, now)
        sys.stdout.write("\033[H\033[J" + render(rows, now - last_change) + "\n")
        sys.stdout.flush()
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
