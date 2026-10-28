"""Local air quality in the Windows tray.

Median PM2.5 from Sensor.community sensors near a chosen location, shown
as a colour-coded US AQI number. No API key needed.
"""
import json
import math
import os
import re
import statistics
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog

import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

APP = "AQI Tray"
UA = "aqi-tray/1.1 (+https://github.com/Satin42/aqi-tray)"
CONFIG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "aqi-tray" / "config.json"
DEFAULTS = {"place": "Belgrade", "lat": 44.8125, "lon": 20.4612, "radius_km": 3}
SEARCH_RADII_KM = (3, 6, 10)  # widen until a new location has enough sensors
MIN_SENSORS = 3  # fewer than this makes the median one sensor's noise
REFRESH_S = 15 * 60
ALERT_AQI = 101  # "Unhealthy for sensitive groups": windows shut, purifier on
ALERT_RESET_AQI = 90  # re-arm the alert only once air drops below this

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


# Serbian Cyrillic -> Latin, for map names that have no English form
_CYR = "АБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ"
_LAT = ["A", "B", "V", "G", "D", "Đ", "E", "Ž", "Z", "I", "J", "K", "L", "Lj", "M", "N",
        "Nj", "O", "P", "R", "S", "T", "Ć", "U", "F", "H", "C", "Č", "Dž", "Š"]
TO_LATIN = str.maketrans(
    {c: l for c, l in zip(_CYR, _LAT)} | {c.lower(): l.lower() for c, l in zip(_CYR, _LAT)}
)


def load_config():
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pm25_to_aqi(c):
    c = math.floor(c * 10) / 10
    for c_lo, c_hi, a_lo, a_hi in BREAKPOINTS:
        if c <= c_hi:
            return round((a_hi - a_lo) / (c_hi - c_lo) * (c - c_lo) + a_lo)
    return 500


def fetch_pm25(lat, lon, radius_km):
    data = get_json(f"https://data.sensor.community/airrohr/v1/filter/area={lat},{lon},{radius_km}")
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


def geocode(query):
    """(short name, lat, lon, full name) for a place or "lat, lon"; None if not found."""
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)\s*", query)
    if m:
        lat, lon = float(m[1]), float(m[2])
        return query.strip(), lat, lon, f"{lat:.4f}, {lon:.4f}"
    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1, "accept-language": "en"})
    hits = get_json(f"https://nominatim.openstreetmap.org/search?{params}")
    if not hits:
        return None
    hit = hits[0]
    full = hit["display_name"].translate(TO_LATIN)
    name = (hit.get("name") or "").translate(TO_LATIN) or full.split(",")[0]
    return name, float(hit["lat"]), float(hit["lon"]), full


def find_sensors(lat, lon):
    """(radius_km, sensor count) for the smallest radius with MIN_SENSORS, else the
    widest radius with any sensors, else None."""
    found = None
    for radius in SEARCH_RADII_KM:
        try:
            found = radius, fetch_pm25(lat, lon, radius)[1]
        except RuntimeError:
            continue
        if found[1] >= MIN_SENSORS:
            break
    return found


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
        self.cfg = load_config()
        self.wake = threading.Event()
        self.stopped = False
        self.alerted = False
        self.dialog_open = False
        self.icon = pystray.Icon(
            "aqi",
            make_icon("…", "#888888", "white"),
            f"{self.cfg['place']} air: loading",
            menu=pystray.Menu(
                pystray.MenuItem("Refresh now", lambda: self.wake.set()),
                pystray.MenuItem("Change location…", self.change_location),
                pystray.MenuItem("Open sensor map", self.open_map, default=True),
                pystray.MenuItem("Quit", self.quit),
            ),
        )

    def update(self):
        cfg = self.cfg
        try:
            pm25, n = fetch_pm25(cfg["lat"], cfg["lon"], cfg["radius_km"])
        except Exception as e:
            self.icon.icon = make_icon("?", "#888888", "white")
            self.icon.title = f"{cfg['place']} air: fetch failed ({e})"[:127]
            return
        aqi = pm25_to_aqi(pm25)
        _, bg, fg, label = level_for(aqi)
        self.icon.icon = make_icon(str(aqi), bg, fg)
        self.icon.title = (
            f"{cfg['place']} AQI {aqi} ({label})\n"
            f"PM2.5 {pm25:.1f} µg/m³, median of {n} sensors\n"
            f"Updated {time.strftime('%H:%M')}"
        )[:127]
        self.check_alert(aqi, pm25, label)

    def check_alert(self, aqi, pm25, label):
        if not self.alerted and aqi >= ALERT_AQI:
            self.alerted = True
            self.icon.notify(
                f"AQI {aqi} ({label}), PM2.5 {pm25:.0f} µg/m³.\n"
                "Close the windows and turn on the air purifier.",
                f"{self.cfg['place']} air quality is getting worse"[:63],
            )
        elif self.alerted and aqi < ALERT_RESET_AQI:
            self.alerted = False

    def open_map(self):
        webbrowser.open(f"https://maps.sensor.community/#13/{self.cfg['lat']}/{self.cfg['lon']}")

    def change_location(self):
        if self.dialog_open:
            return
        self.dialog_open = True
        threading.Thread(target=self.location_dialog, daemon=True).start()

    def location_dialog(self):
        # Tk lives entirely in this thread so the tray keeps responding.
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.iconphoto(True, ImageTk.PhotoImage(self.icon.icon, master=root))
        try:
            while True:
                query = simpledialog.askstring(
                    APP,
                    "Type your neighbourhood, street or town\n"
                    "(e.g. \"Vračar, Belgrade\"), or coordinates like 44.80, 20.47:",
                    initialvalue=self.cfg["place"],
                    parent=root,
                )
                if not query or not query.strip():
                    return
                try:
                    hit = geocode(query)
                    found = hit and find_sensors(hit[1], hit[2])
                except Exception as e:
                    messagebox.showerror(APP, f"Couldn't look that up. Check your internet connection or try again in a minute.\n\n{e}", parent=root)
                    continue
                if not hit:
                    messagebox.showwarning(APP, f"Couldn't find \"{query}\".\nTry adding the city, e.g. \"Zemun, Belgrade\".", parent=root)
                    continue
                name, lat, lon, full = hit
                if not found:
                    messagebox.showwarning(APP, f"{full}\n\nNo air sensors within {SEARCH_RADII_KM[-1]} km. Try a bigger town nearby.", parent=root)
                    continue
                radius, n = found
                if messagebox.askyesno(APP, f"{full}\n\n{n} air sensors within {radius} km.\nUse this location?", parent=root):
                    self.cfg = {"place": name, "lat": round(lat, 4), "lon": round(lon, 4), "radius_km": radius}
                    save_config(self.cfg)
                    self.alerted = False
                    self.wake.set()
                    return
        finally:
            root.destroy()
            self.dialog_open = False

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
