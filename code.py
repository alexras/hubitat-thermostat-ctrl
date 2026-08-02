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
from adafruit_magtag.magtag import MagTag
from adafruit_display_text import label
import terminalio

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
MODE_CYCLE = ["off", "heat", "cool", "auto"]

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------
magtag = MagTag()

print("Connecting to WiFi...")
magtag.network.connect()
print("Connected!")

buttons = magtag.peripherals.buttons  # [A, B, C, D] -- active LOW (pressed = False)

# ---------------------------------------------------------------------------
# Display layout (296 x 128 e-ink)
# ---------------------------------------------------------------------------
magtag.add_text(
    text_position=(10, 8),
    text_scale=1,
    text_anchor_point=(0, 0),
)  # index 0: title / status line

magtag.add_text(
    text_position=(10, 35),
    text_scale=3,
    text_anchor_point=(0, 0),
)  # index 1: current temperature

magtag.add_text(
    text_position=(160, 30),
    text_scale=1,
    text_anchor_point=(0, 0),
)  # index 2: mode + operating state

magtag.add_text(
    text_position=(10, 78),
    text_scale=2,
    text_anchor_point=(0, 0),
)  # index 3: setpoint

magtag.add_text(
    text_position=(10, 116),
    text_scale=1,
    text_anchor_point=(0, 0),
)  # index 4: button legend

magtag.set_text("Connecting to Hubitat...", 0)

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


def safe_refresh():
    """Refresh the e-ink display, respecting a minimum interval between
    full refreshes so we don't over-drive the panel."""
    global last_refresh
    now = time.monotonic()
    if last_refresh != 0 and (now - last_refresh) < MIN_REFRESH_INTERVAL:
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

    if mode == "cool":
        setpoint = state.get("coolingSetpoint", "--")
        setpoint_label = "Cool to"
    else:
        setpoint = state.get("heatingSetpoint", "--")
        setpoint_label = "Heat to"

    magtag.set_text("Hubitat Thermostat - {}".format(status), 0, auto_refresh=False)
    magtag.set_text("{}F".format(temp), 1, auto_refresh=False)
    magtag.set_text("{}\n{}".format(str(mode).upper(), op_state), 2, auto_refresh=False)
    magtag.set_text("{}: {}F".format(setpoint_label, setpoint), 3, auto_refresh=False)
    magtag.set_text("A:+  B:-  C:Mode  D:Refresh", 4, auto_refresh=False)

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


def adjust_setpoint(delta):
    mode = state.get("thermostatMode", "heat")
    if mode == "cool":
        current = float(state.get("coolingSetpoint", 72))
        hubitat_command("setCoolingSetpoint", current + delta)
    else:
        current = float(state.get("heatingSetpoint", 68))
        hubitat_command("setHeatingSetpoint", current + delta)

    time.sleep(1)  # give the hub a moment to process before re-polling
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
        adjust_setpoint(SETPOINT_STEP)
        time.sleep(0.4)

    elif not buttons[1].value:  # B - lower setpoint
        adjust_setpoint(-SETPOINT_STEP)
        time.sleep(0.4)

    elif not buttons[2].value:  # C - cycle mode
        cycle_mode()
        time.sleep(0.4)

    elif not buttons[3].value:  # D - manual refresh
        refresh_from_hub("Manual refresh")
        time.sleep(0.4)

    if now - last_poll > POLL_INTERVAL:
        refresh_from_hub()
        last_poll = now

    time.sleep(0.1)
