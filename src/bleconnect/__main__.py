"""Command-line entry point for BLEConnect."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from . import __version__

logger = logging.getLogger("bleconnect.cli")


async def _ble_scan(args: argparse.Namespace) -> None:
    from .adapters.linux.ble_central import find_ble_service

    device = await find_ble_service(timeout=args.timeout)
    name = getattr(device, "name", None) or ""
    address = getattr(device, "address", "")
    print(f"{address} {name}".strip())


async def _ble_ping(args: argparse.Namespace) -> None:
    from .adapters.linux.ble_central import connect_ble_service

    link = await connect_ble_service(
        address=args.address,
        timeout=args.timeout,
        pair=args.pair,
        connect_timeout=args.connect_timeout,
        attempts=args.attempts,
    )
    try:
        from .messages import PING, PONG, control_packet

        await link.send(control_packet(PING, {"ts": int(time.time() * 1000)}))
        while True:
            packet = await asyncio.wait_for(
                link.receive(), timeout=args.timeout
            )
            if packet.type == PONG:
                print(packet)
                return
    finally:
        await link.close()


async def _pair_command(args: argparse.Namespace) -> None:
    from .platform.linux import build_linux_pairing_service

    service = build_linux_pairing_service()
    if args.command == "discover":
        devices = await service.discover(args.timeout)
        for device in devices:
            paired = "paired" if device.paired else "new"
            print(f"{device.address}  {device.name}  [{paired}]")
    elif args.command == "pair":
        device = await service.pair_and_trust(args.address)
        print(f"trusted {device.address}  {device.name}")
    elif args.command == "forget":
        await service.forget(args.address)
        print(f"forgot {args.address.upper()}")


async def _rfcomm_server(args: argparse.Namespace) -> None:
    from .adapters.filesystem.file_sink import LocalFileSinkFactory
    from .adapters.linux.rfcomm import BluezRfcommServer
    from .adapters.linux.trusted_devices import JsonTrustedDevicesRepository
    from .application.file_transfer_service import FileTransferService
    from .messages import PING, PONG, control_packet

    trusted = JsonTrustedDevicesRepository()
    if not await trusted.list_trusted():
        logger.warning(
            "no trusted devices; run `bleconnect pair --address ...` first"
        )
    download_dir = Path(args.download_dir) if args.download_dir else (
        Path.home() / "Downloads" / "bleconnect"
    )
    sink_factory = LocalFileSinkFactory(download_dir)

    async def handle_peer(address: str, link) -> None:
        logger.info("RFCOMM connected: %s", address)
        transfers = FileTransferService(
            link,
            sink_factory,
            on_progress=lambda progress: logger.info(
                "transfer %s %s %s/%s",
                progress.name,
                progress.state.value,
                progress.transferred,
                progress.total,
            ),
        )
        try:
            while True:
                packet = await link.receive()
                if packet.type == PING:
                    await link.send(control_packet(PONG))
                else:
                    await transfers.handle_packet(packet)
        except (ConnectionError, asyncio.IncompleteReadError, OSError) as exc:
            logger.info("RFCOMM disconnected (%s): %s", address, exc)
        finally:
            await transfers.close()

    server = BluezRfcommServer(handle_peer, trusted)
    await server.start(channel=args.channel, service_uuid=args.uuid)
    logger.info(
        "RFCOMM service registered; UUID=%s channel=%s downloads=%s",
        args.uuid,
        args.channel,
        download_dir,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await server.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bluetooth sharing companion")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("ble-scan", help="find the BLE peripheral")
    scan.add_argument("--timeout", type=float, default=10.0)

    ping = subparsers.add_parser("ble-ping", help="send a BLE ping")
    ping.add_argument("--address", default=None)
    ping.add_argument("--timeout", type=float, default=10.0)
    ping.add_argument("--connect-timeout", type=float, default=30.0)
    ping.add_argument("--attempts", type=int, default=2)
    ping.add_argument(
        "--pair", action="store_true", help="pair while connecting"
    )

    discover = subparsers.add_parser(
        "discover", help="discover Bluetooth devices via BlueZ"
    )
    discover.add_argument("--timeout", type=float, default=10.0)

    pair = subparsers.add_parser("pair", help="pair and trust a device")
    pair.add_argument("--address", required=True)

    forget = subparsers.add_parser("forget", help="forget a trusted device")
    forget.add_argument("--address", required=True)

    rfcomm = subparsers.add_parser(
        "rfcomm-server", help="accept RFCOMM file transfers"
    )
    rfcomm.add_argument("--channel", type=int, default=24)
    rfcomm.add_argument(
        "--uuid",
        default="d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10",
    )
    rfcomm.add_argument("--download-dir", default=None)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    handlers = {
        "ble-scan": _ble_scan,
        "ble-ping": _ble_ping,
        "discover": _pair_command,
        "pair": _pair_command,
        "forget": _pair_command,
        "rfcomm-server": _rfcomm_server,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
