# WiFi Distance Estimator

A lightweight Windows utility that estimates the approximate distance to nearby WiFi access points using signal strength, frequency, and a path-loss model.

> **Note:** Distance estimates are approximate. WiFi signal strength is affected by walls, interference, antenna orientation, transmit power, and many other environmental factors.

## Features

* Detect nearby WiFi access points
* Display SSID and BSSID
* Display signal strength and estimated RSSI
* Detect WiFi frequency bands
* Estimate approximate access-point distance
* Smooth noisy readings with an exponential moving average
* Automatically remove networks that disappear
* No external Python dependencies

## Requirements

* Windows
* Python 3.x
* A WiFi adapter

The project uses the Windows `netsh` utility and therefore currently supports Windows only.

## Installation

Clone the repository:

```bash
git clone https://github.com/lllons/WIFI-Distance-Estimator.git
cd WIFI-Distance-Estimator
```

Run the scanner:

```bash
python Start.py
```

Alternatively:

```bash
py Start.py
```

Press `Ctrl+C` to stop the program.

## How It Works

The program repeatedly runs:

```text
netsh wlan show networks mode=bssid
```

The output is parsed to obtain information about nearby access points.

### Signal to RSSI

Windows reports WiFi signal quality as a percentage. The project approximates RSSI using:

```text
RSSI ≈ (Signal / 2) - 100
```

For example:

| Signal | Estimated RSSI |
| -----: | -------------: |
|    80% |        -60 dBm |
|    60% |        -70 dBm |
|    40% |        -80 dBm |

This conversion is an approximation and should not be interpreted as a direct RSSI measurement.

### Distance Estimation

Distance is estimated using a logarithmic path-loss model:

```text
d = 10 ^ ((RSSI₁m - RSSI) / (10 × n))
```

Where:

* `d` is the estimated distance
* `RSSI₁m` is the assumed RSSI at one metre
* `RSSI` is the current estimated RSSI
* `n` is the path-loss exponent

The default configuration includes:

```python
RSSI_AT_1M_2400MHZ = -40.0
PATH_LOSS_EXPONENT = 1.5
SHADOWING_DB = 6.0
EMA_ALPHA = 0.4
```

## Configuration

The main configuration values are located near the top of `Start.py`.

| Setting                | Default | Description                              |
| ---------------------- | ------: | ---------------------------------------- |
| `REFRESH_SECONDS`      |   `0.5` | Scan interval                            |
| `RSSI_AT_1M_2400MHZ`   | `-40.0` | Reference RSSI at one metre              |
| `PATH_LOSS_EXPONENT`   |   `1.5` | Signal propagation model                 |
| `SHADOWING_DB`         |   `6.0` | Estimated environmental variation        |
| `EMA_ALPHA`            |   `0.4` | Signal smoothing factor                  |
| `FORGET_AFTER_SECONDS` |  `30.0` | Time before an unseen network is removed |

Changing the path-loss parameters can have a significant effect on the resulting distance estimates.

## Accuracy

This project is intended for **rough proximity estimation**, not precise positioning.

WiFi propagation varies significantly between environments. Factors include:

* Walls and floors
* Furniture
* People
* Antenna orientation
* Access-point transmit power
* WiFi adapter characteristics
* Interference
* Multipath propagation
* Building materials
* Frequency band

For this reason, the program provides an estimated range rather than treating the calculated distance as an exact measurement.

For better results, the model can be calibrated against known distances in the environment where it will be used.

## Signal Saturation

When Windows reports a signal strength of `100%`, the measurement has reached the upper end of its reported range.

The estimator therefore treats extremely strong signals as an upper-bound estimate rather than assuming an exact distance.

## Example Output

```text
WI-FI PROXIMITY SCANNER
========================================================================================

SSID                          BSSID             Signal     RSSI     Est. distance   Band   Ch
----------------------------------------------------------------------------------------
MyNetwork                     aa:bb:cc:dd:ee:ff    82%     -59dBm           2-8 m    5.0  36
NeighbourWiFi                 11:22:33:44:55:66    61%     -69dBm          6-24 m    2.4   6
CoffeeShop                    12:34:56:78:90:ab    43%     -78dBm         15-60 m    5.0  44

Refreshing every 0.5s. Ctrl+C to stop.
```

Actual output depends on the networks visible to your WiFi adapter.

## Troubleshooting

### No networks are detected

Check whether Windows can detect networks directly:

```bash
netsh wlan show networks mode=bssid
```

If Windows does not report any networks, the estimator cannot produce results.

### `netsh` cannot be found

`netsh` is included with Windows. Verify that you are running the project in a standard Windows environment and that your system PATH has not been modified.


## Project Structure

```text
WIFI-Distance-Estimator/
├── Start.py
├── README.md
└── LICENSE
```

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for details.

## Disclaimer

This software provides estimates based on WiFi signal characteristics. It should not be used for navigation, safety-critical applications, or precise location tracking.
