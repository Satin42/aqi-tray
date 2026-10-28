"""Local air quality in the Windows tray.

Median PM2.5 from Sensor.community sensors near LAT/LON, shown as a
colour-coded US AQI number. No API key needed.
"""
import json
import math
import statistics
import threading
import time
import urllib.request
import webbrowser

import pystray
from PIL import Image, ImageDraw, ImageFont

PLACE = "Belgrade"
LAT, LON = 44.8125, 20.4612  # set to your street for local readings
RADIUS_KM = 3
REFRESH_S = 15 * 60

API = f"https://data.sensor.community/airrohr/v1/filter/area={LAT},{LON},{RADIUS_KM}"
MAP = f"https://maps.sensor.community/#13/{LAT}/{LON}"

# US EPA PM2.5 breakpoints (2024 revision): (c_lo, c_hi, aqi_lo, aqi_hi)
BREAKPOINTS = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]
# (max AQI, background, text, label)
LEVELS = [
    (50, "#00e400", "black", "Good"),
    (100, "#ffff00", "black", "Moderate"),
    (150, "#ff7e00", "black", "Unhealthy for sensitive"),
    (200, "#ff0000", "white", "Unhealthy"),
    (300, "#8f3f97", "white", "Very unhealthy"),
    (10_000, "#7e0023", "white", "Hazardous"),
]


def pm25_to_aqi(c):
    c = math.floor(c * 10) / 10
    for c_lo, c_hi, a_lo, a_hi in BREAKPOINTS:
        if c <= c_hi:
            return round((a_hi - a_lo) / (c_hi - c_lo) * (c - c_lo) + a_lo)
    return 500


def fetch_pm25():
    req = urllib.request.Request(API, headers={"User-Agent": "aqi-tray/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    values = [
        float(v["value"])
        for entry in data
        for v in entry["sensordatavalues"]
        if v["value_type"] == "P2"
    ]
    values = [v for v in values if 0 <= v < 500]  # drop broken sensors
    if not values:
        raise RuntimeError("no PM2.5 sensors in range")
    return statistics.median(values), len(values)


def make_icon(text, bg, fg):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 63, 63), radius=12, fill=bg)
    font = ImageFont.truetype("arialbd.ttf", 44 if len(text) <= 2 else 32)
    d.text((32, 33), text, font=font, fill=fg, anchor="mm")
    return img


def level_for(aqi):
    return next(lvl for lvl in LEVELS if aqi <= lvl[0])


class AqiTray:
    def __init__(self):
        self.wake = threading.Event()
        self.stopped = False
        self.icon = pystray.Icon(
            "aqi",
            make_icon("…", "#888888", "white"),
            f"{PLACE} air: loading",
            menu=pystray.Menu(
                pystray.MenuItem("Refresh now", lambda: self.wake.set()),
                pystray.MenuItem("Open sensor map", lambda: webbrowser.open(MAP), default=True),
                pystray.MenuItem("Quit", self.quit),
            ),
        )

    def update(self):
        try:
            pm25, n = fetch_pm25()
        except Exception as e:
            self.icon.icon = make_icon("?", "#888888", "white")
            self.icon.title = f"{PLACE} air: fetch failed ({e})"[:127]
            return
        aqi = pm25_to_aqi(pm25)
        _, bg, fg, label = level_for(aqi)
        self.icon.icon = make_icon(str(aqi), bg, fg)
        self.icon.title = (
            f"{PLACE} AQI {aqi} ({label})\n"
            f"PM2.5 {pm25:.1f} µg/m³, median of {n} sensors\n"
            f"Updated {time.strftime('%H:%M')}"
        )[:127]

    def loop(self, icon):
        icon.visible = True
        while True:
            self.update()
            self.wake.wait(REFRESH_S)
            if self.stopped:
                return
            self.wake.clear()

    def quit(self):
        self.stopped = True
        self.wake.set()
        self.icon.stop()

    def run(self):
        self.icon.run(setup=self.loop)


if __name__ == "__main__":
    AqiTray().run()
