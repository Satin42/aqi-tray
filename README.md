<p align="center"><img src="assets/icon.png" width="128" alt="aqi-tray icon"></p>

# aqi-tray

Live air quality as a colour-coded number in the Windows system tray, next to the clock.

It takes the median PM2.5 reading from [Sensor.community](https://sensor.community) citizen sensors around a point you choose, converts it to the US EPA AQI (2024 breakpoints) and refreshes every 15 minutes. No API key, no account.

| AQI | Colour | Level |
|---|---|---|
| 0–50 | green | Good |
| 51–100 | yellow | Moderate |
| 101–150 | orange | Unhealthy for sensitive groups |
| 151–200 | red | Unhealthy |
| 201–300 | purple | Very unhealthy |
| 301+ | maroon | Hazardous |

Hover for PM2.5 in µg/m³, sensor count and update time. Double-click opens the sensor map; right-click for **Refresh now** and **Quit**.

## Install

Requires Python 3.10+ on Windows.

```
pip install -r requirements.txt
pythonw aqi_tray.py
```

Windows may park the icon in the overflow menu (^) at first; drag it onto the taskbar to keep it visible.

## Configure

Edit the constants at the top of `aqi_tray.py`:

| Constant | Default | Meaning |
|---|---|---|
| `PLACE` | `Belgrade` | Name shown in the tooltip |
| `LAT`, `LON` | `44.8125, 20.4612` | Centre of the sensor search |
| `RADIUS_KM` | `3` | Search radius |
| `REFRESH_S` | `900` | Refresh interval in seconds |

Find sensors near you on the [Sensor.community map](https://maps.sensor.community). If the icon shows `?`, there are no sensors in range: widen `RADIUS_KM`.

## Start with Windows

In PowerShell, from the repo folder:

```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Startup'))\AQI Tray.lnk")
$s.TargetPath = (Get-Command pythonw).Source
$s.Arguments = "`"$PWD\aqi_tray.py`""
$s.WorkingDirectory = "$PWD"
$s.IconLocation = "$PWD\assets\icon.ico"
$s.Save()
```

## Caveats

Sensor.community nodes are low-cost optical sensors (mostly SDS011). They read high in fog and humidity above ~80%, so treat spikes on foggy days with suspicion. The median across many sensors filters out single broken nodes but not weather-wide bias.

## License

MIT
