"""Command-line entry point for the Linux companion service."""

import asyncio
import argparse
import logging

from . import __version__
from .protocol import packet

logger = logging.getLogger("bleconnect.rfcomm")


async def _serve_rfcomm(channel: int, service_uuid: str) -> None:
    from .adapters.linux.bluez_rfcomm_server import BluezRfcommServer

    async def handle_peer(device_path, link) -> None:
        logger.info("RFCOMM connected: %s", device_path)
        try:
            while True:
                message = await link.receive()
                if message.get("type") == "ping":
                    await link.send(
                        packet("pong", {"name": "BLEConnect Linux", "device": device_path})
                    )
                else:
                    await link.send(
                        packet("error", {"message": "unsupported test packet"})
                    )
        except (ConnectionError, asyncio.IncompleteReadError, OSError) as exc:
            logger.info("RFCOMM disconnected (%s): %s", device_path, exc)

    server = BluezRfcommServer(handle_peer)
    await server.start(channel=channel, service_uuid=service_uuid)
    logger.info("RFCOMM service registered; UUID=%s channel=%s", service_uuid, channel)
    try:
        await asyncio.Event().wait()
    finally:
        await server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bluetooth sharing companion")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    rfcomm = subparsers.add_parser(
        "rfcomm-server", help="register a test RFCOMM service with BlueZ"
    )
    rfcomm.add_argument("--channel", type=int, default=24)
    rfcomm.add_argument(
        "--uuid",
        default="d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10",
        help="service UUID clients use to discover the RFCOMM endpoint",
    )
    args = parser.parse_args()
    if args.command == "rfcomm-server":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        try:
            asyncio.run(_serve_rfcomm(args.channel, args.uuid))
        except KeyboardInterrupt:
            pass
        return
    parser.error("choose a command; the application UI is not implemented yet")


if __name__ == "__main__":
    main()
