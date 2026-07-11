#!/usr/bin/env bash
#
# diagnose_flipper.sh — serial-port and permission diagnostics for the Flipper Zero bridge.
#
echo "=== MAD Flipper diagnostics ==="

echo
echo "[1] Serial devices:"
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/flipper* 2>/dev/null || echo "    none found (/dev/ttyACM* /dev/ttyUSB* /dev/flipper*)"

echo
echo "[2] USB devices (lsusb):"
if command -v lsusb >/dev/null 2>&1; then
  lsusb | grep -i -E "flipper|stm|0483" || lsusb
else
  echo "    lsusb not installed (sudo apt install usbutils)"
fi

echo
echo "[3] Kernel messages (last serial events):"
( dmesg 2>/dev/null | grep -i -E "ttyACM|cdc_acm|usb" | tail -n 8 ) || echo "    dmesg needs root: sudo dmesg | grep ttyACM"

echo
echo "[4] Permissions:"
echo "    current user : $(whoami)"
echo "    groups       : $(groups)"
if groups | grep -qw dialout; then
  echo "    dialout      : OK"
else
  echo "    dialout      : MISSING -> sudo usermod -aG dialout $USER && newgrp dialout"
fi

echo
echo "[5] Quick read test (3s) — expects JSON lines from sensor_flipper.py:"
PORT="$(ls /dev/ttyACM* 2>/dev/null | head -n1)"
if [ -n "${PORT:-}" ]; then
  echo "    reading $PORT ..."
  timeout 3 cat "$PORT" 2>/dev/null || echo "    (no data / permission denied — check dialout group)"
else
  echo "    no /dev/ttyACM* device to read"
fi

echo
echo "=== done ==="
