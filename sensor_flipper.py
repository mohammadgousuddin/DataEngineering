"""
sensor_flipper.py — MicroPython firmware for the Flipper Zero GPIO bridge.

Reads a DHT22 (AM2302) on GPIO A7 and a DS18B20 on GPIO B3, then prints one JSON
line per cycle to USB-CDC (stdout) every 5 seconds. The host `sensor_bridge.py`
reads this stream from /dev/ttyACM0.

Wiring (4.7k pull-up REQUIRED on each data line, to 3.3V):
    DHT22  VCC -> 3.3V   DATA -> A7 (+4.7k to 3.3V)   GND -> GND
    DS18B20 VDD -> 3.3V   DQ  -> B3 (+4.7k to 3.3V)   GND -> GND

Load this onto the Flipper SD card and run it from the MicroPython app.
NOTE: this targets a MicroPython runtime on the Flipper; pin names follow the
Flipper GPIO labels (A7, B3). Adjust to your firmware's machine.Pin mapping.
"""
import json
import time

try:
    import machine
    import dht
    import onewire
    import ds18x20
    HAVE_HW = True
except ImportError:
    # Lets the file be syntax-checked off-device; prints a stub stream instead.
    HAVE_HW = False

DHT_PIN = "A7"
DS_PIN = "B3"
PERIOD_S = 5
DS_CONVERT_MS = 800  # 12-bit conversion settling time


def setup():
    dht_sensor = dht.DHT22(machine.Pin(DHT_PIN))
    ow = onewire.OneWire(machine.Pin(DS_PIN))
    ds_sensor = ds18x20.DS18X20(ow)
    roms = ds_sensor.scan()
    return dht_sensor, ds_sensor, roms


def read_cycle(dht_sensor, ds_sensor, roms):
    # DHT22: air temperature + relative humidity
    dht_sensor.measure()
    temp_dht = dht_sensor.temperature()
    humidity = dht_sensor.humidity()

    # DS18B20: probe temperature (parasitic-powered 1-Wire)
    temp_ds18 = None
    ds_status = "ok"
    try:
        if roms:
            ds_sensor.convert_temp()
            time.sleep_ms(DS_CONVERT_MS)
            temp_ds18 = ds_sensor.read_temp(roms[0])
        else:
            ds_status = "fallback"
    except Exception:
        ds_status = "fallback"

    if temp_ds18 is None:
        temp_ds18 = temp_dht  # fall back to DHT22 temperature
        ds_status = "fallback"

    return {
        "temp_dht": round(temp_dht, 2),
        "temp_ds18": round(temp_ds18, 2),
        "humidity": round(humidity, 2),
        "ds_status": ds_status,
    }


def main():
    if not HAVE_HW:
        print('{"error":"machine/dht/ds18x20 modules unavailable off-device"}')
        return
    dht_sensor, ds_sensor, roms = setup()
    while True:
        try:
            payload = read_cycle(dht_sensor, ds_sensor, roms)
            print(json.dumps(payload))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
        time.sleep(PERIOD_S)


if __name__ == "__main__":
    main()
