"""
MagTag Hubitat Thermostat Controller
-------------------------------------
Turns an Adafruit MagTag into a simple wall-mounted controller for a
Hubitat "Virtual Thermostat" (or any thermostat device), talked to
through Hubitat's Maker API app.

Buttons:
  A (far left)   -> raise setpoint
  B              -> lower setpoint
  C              -> cycle mode (off -> heat -> cool -> auto)
  D (far right)  -> manual refresh

Requires a secrets.py on the board with WiFi + Hubitat details.
See secrets.py.example for the format.
"""

import time
import terminalio
from adafruit_display_text import label
from adafruit_magtag.magtag import MagTag
from font_raleway_regular_14 import FONT as RALEWAY_REGULAR_14
from font_raleway_regular_30 import FONT as RALEWAY_REGULAR_30

TITLE_FONT = RALEWAY_REGULAR_14
TEMP_LABEL_FONT = RALEWAY_REGULAR_30
MODE_FONT = RALEWAY_REGULAR_14
SETPOINT_FONT = RALEWAY_REGULAR_14
LEGEND_FONT = RALEWAY_REGULAR_14

try:
    from secrets import secrets
except ImportError:
    print("WiFi and Hubitat secrets are kept in secrets.py, please add them there!")
    raise


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HUBITAT_IP = secrets["hubitat_ip"]
MAKER_APP_ID = secrets["hubitat_app_id"]
MAKER_TOKEN = secrets["hubitat_token"]
THERMOSTAT_ID = secrets["thermostat_device_id"]

BASE_URL = "http://{}/apps/api/{}/devices/{}".format(
    HUBITAT_IP, MAKER_APP_ID, THERMOSTAT_ID
)

SETPOINT_STEP = 1.0          # degrees per button press
POLL_INTERVAL = 300          # seconds between automatic background refreshes
MIN_REFRESH_INTERVAL = 180   # seconds; keeps us from hammering the e-ink panel
BUTTON_PRESS_REFRESH_INTERVAL = 5 # seconds: keeps up from refreshing a bunch when you press a bunch of buttons
MODE_CYCLE = ["off", "heat", "cool", "auto"]

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------
magtag = MagTag()

print("Connecting to WiFi...")
magtag.network.connect()
print("Connected!")

last_button_time = time.monotonic()
pending_refresh = False

buttons = magtag.peripherals.buttons  # [A, B, C, D] -- active LOW (pressed = False)

# ---------------------------------------------------------------------------
# Display layout (296 x 128 e-ink)
# ---------------------------------------------------------------------------
title_label = label.Label(TITLE_FONT, text="Connecting...", color=0x000000)
title_label.anchor_point = (0.5, 0)
title_label.anchored_position = (148, 8)

temp_label = label.Label(TEMP_LABEL_FONT, text="--F", color=0x000000)
temp_label.anchor_point = (0.5, 0)
temp_label.anchored_position = (148, 40)

mode_label = label.Label(MODE_FONT, text="?\n?", color=0x000000)
mode_label.anchor_point = (0, 0.5)
mode_label.anchored_position = (220, 64)

setpoint_label = label.Label(SETPOINT_FONT, text="--F", color=0x000000)
setpoint_label.anchor_point = (0.5, 0)
setpoint_label.anchored_position = (148, 70)

LABEL_START = 30
LABEL_SEP = 72

heat_down_label = label.Label(LEGEND_FONT, text="H-", color=0x000000)
heat_down_label.anchor_point = (0.5, 0)
heat_down_label.anchored_position = (LABEL_START, 110)

heat_up_label = label.Label(LEGEND_FONT, text="H+", color=0x000000)
heat_up_label.anchor_point = (0.5, 0)
heat_up_label.anchored_position = (LABEL_START + LABEL_SEP, 110)

cool_down_label = label.Label(LEGEND_FONT, text="C-", color=0x000000)
cool_down_label.anchor_point = (0.5, 0)
cool_down_label.anchored_position = (LABEL_START + 2 * LABEL_SEP, 110)

cool_up_label = label.Label(LEGEND_FONT, text="C+", color=0x000000)
cool_up_label.anchor_point = (0.5, 0)
cool_up_label.anchored_position = (LABEL_START + 3 * LABEL_SEP, 110)

magtag.splash.append(title_label)
magtag.splash.append(temp_label)
magtag.splash.append(mode_label)
magtag.splash.append(setpoint_label)
magtag.splash.append(heat_down_label)
magtag.splash.append(heat_up_label)
magtag.splash.append(cool_down_label)
magtag.splash.append(cool_up_label)

# ---------------------------------------------------------------------------
# Hubitat Maker API helpers
# ---------------------------------------------------------------------------
def hubitat_get(path=""):
    """GET a Maker API path and return parsed JSON."""
    url = "{}{}?access_token={}".format(BASE_URL, path, MAKER_TOKEN)
    response = magtag.network.requests.get(url)
    try:
        data = response.json()
    finally:
        response.close()
    return data


def hubitat_command(command, value=None):
    """Send a Maker API command to the thermostat device."""
    path = "/{}".format(command)
    if value is not None:
        path += "/{}".format(value)
    return hubitat_get(path)


def get_thermostat_state():
    """Fetch the device detail and flatten its attributes into a dict."""
    data = hubitat_get()
    attrs = {}
    for attr in data.get("attributes", []):
        attrs[attr["name"]] = attr["currentValue"]
    return attrs


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
last_refresh = 0


def safe_refresh(refresh_interval=MIN_REFRESH_INTERVAL):
    """Refresh the e-ink display, respecting a minimum interval between
    full refreshes so we don't over-drive the panel."""
    global last_refresh
    now = time.monotonic()
    if last_refresh != 0 and (now - last_refresh) < refresh_interval:
        return
    try:
        magtag.refresh()
        last_refresh = now
    except RuntimeError as e:
        print("Refresh skipped:", e)


def update_display(state, status="OK"):
    temp = state.get("temperature", "--")
    mode = state.get("thermostatMode", "?")
    op_state = state.get("thermostatOperatingState", "?")
    heat_setpoint = state.get("heatingSetpoint", "--")
    cool_setpoint = state.get("coolingSetpoint", "--")

    title_label.text = "Hubitat Thermostat Controls"
    temp_label.text = "{}".format(temp)
    mode_label.text = "{}\n{}".format(str(mode).upper(), op_state)
    setpoint_label.text = "H: {} C: {}".format(heat_setpoint, cool_setpoint)
    # legend_label never changes, so it's set once at layout time

    safe_refresh()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
state = {}


def refresh_from_hub(status="OK"):
    global state
    try:
        state = get_thermostat_state()
        update_display(state, status)
    except Exception as e:  # network hiccups, hub offline, etc.
        print("Error refreshing from Hubitat:", e)
        update_display(state, status="ERROR")


def adjust_setpoint(setpoint, delta):
    global last_button_time, pending_refresh
    last_button_time = time.monotonic()
    pending_refresh = True

    state = get_thermostat_state()

    if setpoint == "cool":
        current = float(state.get("coolingSetpoint", 72))
        hubitat_command("setCoolingSetpoint", current + delta)
    else:
        current = float(state.get("heatingSetpoint", 68))
        hubitat_command("setHeatingSetpoint", current + delta)

    refresh_from_hub()


def cycle_mode():
    mode = state.get("thermostatMode", "off")
    idx = MODE_CYCLE.index(mode) if mode in MODE_CYCLE else 0
    next_mode = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]
    hubitat_command("setThermostatMode", next_mode)
    time.sleep(1)
    refresh_from_hub()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
refresh_from_hub("Startup")
last_poll = time.monotonic()

while True:
    now = time.monotonic()

    if not buttons[0].value:  # A - raise setpoint
        adjust_setpoint("heat", -SETPOINT_STEP)
        time.sleep(0.4)

    elif not buttons[1].value:  # B - lower setpoint
        adjust_setpoint("heat", SETPOINT_STEP)
        time.sleep(0.4)

    elif not buttons[2].value:  # C - cycle mode
        adjust_setpoint("cool", -SETPOINT_STEP)
        time.sleep(0.4)

    elif not buttons[3].value:  # D - manual refresh
        adjust_setpoint("cool", +SETPOINT_STEP)
        time.sleep(0.4)

    if now - last_poll > POLL_INTERVAL:
        refresh_from_hub()
        last_poll = now

    if pending_refresh and (now - last_button_time) >= BUTTON_PRESS_REFRESH_INTERVAL:
        refresh_from_hub()
        magtag.refresh()
        pending_refresh = False

    time.sleep(0.1)