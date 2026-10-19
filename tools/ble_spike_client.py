#!/usr/bin/env python3
"""Write a clipboard sample to the BLEConnect M0 Android spike."""

from __future__ import annotations

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

SERVICE_UUID = "d37b4a31-8e74-4f36-9a01-7d3a8f7c2b10"
INFO_UUID = "d37b4a32-8e74-4f36-9a01-7d3a8f7c2b10"
CONTROL_UUID = "d37b4a33-8e74-4f36-9a01-7d3a8f7c2b10"
CLIPBOARD_UUID = "d37b4a34-8e74-4f36-9a01-7d3a8f7c2b10"


def _has_service(device, advertisement) -> bool:
    service_uuids = advertisement.service_uuids or []
    return SERVICE_UUID.lower() in {str(uuid).lower() for uuid in service_uuids}


async def _find(timeout: float):
    return await BleakScanner.find_device_by_filter(_has_service, timeout=timeout)


def _print_notification(label: str):
    def handler(_sender, data: bytearray) -> None:
        print(f"{label}: {bytes(data).decode('utf-8', errors='replace')}")

    return handler


async def _run(args) -> int:
    device = args.address or await _find(args.timeout)
    if device is None:
        print("Android spike was not found. Is the service running and advertising?")
        return 1

    print(f"Connecting to {device}")
    async with BleakClient(device) as client:
        info = await client.read_gatt_char(INFO_UUID)
        print("info:", bytes(info).decode("utf-8", errors="replace"))

        await client.start_notify(CONTROL_UUID, _print_notification("control"))
        await client.start_notify(CLIPBOARD_UUID, _print_notification("clipboard"))

        ping = b'{"type":"ping","body":{}}'
        await client.write_gatt_char(CONTROL_UUID, ping, response=True)
        print("sent ping")

        await client.write_gatt_char(
            CLIPBOARD_UUID, args.text.encode("utf-8"), response=True
        )
        print("sent clipboard text")

        await asyncio.sleep(args.wait)

    print("done")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "text",
        nargs="?",
        default="BLEConnect M0 spike from Linux",
        help="clipboard text to write",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--wait", type=float, default=1.5)
    parser.add_argument("--address", default=None, help="skip scan and connect directly")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
