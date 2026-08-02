# MagTag Thermostat Controller

## Secrets

Create a file named `secrets.py` in the same directory as `code.py`. It should look like the following:

```python
secrets = {
    "ssid": "your SSID here",
    "password": "your SSID password here",

    # IP address of your Hubitat hub on your local network
    "hubitat_ip": "192.168.1.42",

    # The number in the URL of your Maker API app instance in Hubitat,
    # e.g. from ".../apps/api/12/..." this would be "12"
    "hubitat_app_id": "12",

    # The access_token shown on the Maker API app's config page in Hubitat
    "hubitat_token": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",

    # The device ID of the virtual thermostat, also visible on the
    # Maker API app's config page (or in the device's own URL in Hubitat)
    "thermostat_device_id": "11",
}
```