"""RFCOMM packet link and BlueZ profile server for Linux."""

from __future__ import annotations

import asyncio
import inspect
import logging
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from ...application.ports import PacketLink, TrustedDevicesRepository
from ...protocol import Packet, encode_packet, read_packet
from .trusted_devices import is_trusted

SERVICE_UUID = "d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10"
PROFILE_PATH = "/org/bleconnect/Profile"
DEFAULT_CHANNEL = 24

logger = logging.getLogger("bleconnect.rfcomm")


class RfcommDeviceLink:
    """PacketLink over one connected RFCOMM socket."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._send_lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def connect(
        cls, address: str, channel: int = DEFAULT_CHANNEL
    ) -> RfcommDeviceLink:
        if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(
            socket, "BTPROTO_RFCOMM"
        ):
            raise OSError("RFCOMM is available only on supported Linux systems")
        if not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be between 1 and 30")

        bluetooth_socket = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        bluetooth_socket.setblocking(False)
        try:
            await asyncio.get_running_loop().sock_connect(
                bluetooth_socket, (address, channel)
            )
            reader, writer = await asyncio.open_connection(sock=bluetooth_socket)
        except BaseException:
            bluetooth_socket.close()
            raise
        return cls(reader, writer)

    async def send(self, packet: Packet) -> None:
        if self._closed:
            raise ConnectionError("RFCOMM link is closed")
        frame = encode_packet(packet)
        async with self._send_lock:
            self._writer.write(frame)
            await self._writer.drain()

    async def receive(self) -> Packet:
        if self._closed:
            raise ConnectionError("RFCOMM link is closed")
        return await read_packet(self._reader)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except OSError:
            pass


def _make_profile(server: "BluezRfcommServer") -> Any:
    from dbus_next.service import ServiceInterface, method

    class Profile(ServiceInterface):
        def __init__(self) -> None:
            super().__init__("org.bluez.Profile1")

        @method()
        def Release(self) -> "":
            server._released()

        @method()
        def NewConnection(
            self,
            device: "o",
            fd: "h",
            properties: "a{sv}",
        ) -> "":
            server._accept_fd(device, fd)

        @method()
        def RequestDisconnection(self, device: "o") -> "":
            server._drop_link(device)

    return Profile()


class BluezRfcommServer:
    """Publish the RFCOMM profile and hand trusted links to a callback."""

    def __init__(
        self,
        on_link: Callable[[str, RfcommDeviceLink], Awaitable[None] | None],
        trusted_devices: TrustedDevicesRepository,
    ) -> None:
        self._on_link = on_link
        self._trusted_devices = trusted_devices
        self._bus = None
        self._profile = None
        self._links: dict[str, RfcommDeviceLink] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    async def start(
        self,
        channel: int = DEFAULT_CHANNEL,
        service_uuid: str = SERVICE_UUID,
    ) -> None:
        if not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be between 1 and 30")
        try:
            from dbus_next import BusType, Variant
            from dbus_next.aio import MessageBus
        except ImportError as exc:
            raise RuntimeError(
                "BlueZ RFCOMM support needs the optional dependency: "
                "uv sync --extra linux"
            ) from exc

        self._bus = await MessageBus(
            bus_type=BusType.SYSTEM, negotiate_unix_fd=True
        ).connect()
        self._profile = _make_profile(self)
        self._bus.export(PROFILE_PATH, self._profile)
        try:
            introspection = await self._bus.introspect("org.bluez", "/org/bluez")
            proxy = self._bus.get_proxy_object(
                "org.bluez", "/org/bluez", introspection
            )
            manager = proxy.get_interface("org.bluez.ProfileManager1")
            await manager.call_register_profile(
                PROFILE_PATH,
                service_uuid,
                {
                    "Name": Variant("s", "BLEConnect"),
                    "Role": Variant("s", "server"),
                    "Channel": Variant("q", channel),
                    "RequireAuthentication": Variant("b", True),
                },
            )
        except BaseException:
            self._bus.unexport(PROFILE_PATH, self._profile)
            self._bus.disconnect()
            self._bus = None
            self._profile = None
            raise

    async def _device_address(self, device_path: str) -> str | None:
        if self._bus is None:
            return None
        try:
            introspection = await self._bus.introspect(
                "org.bluez", device_path
            )
            proxy = self._bus.get_proxy_object(
                "org.bluez", device_path, introspection
            )
            properties = proxy.get_interface("org.freedesktop.DBus.Properties")
            value = await properties.call_get("org.bluez.Device1", "Address")
        except Exception:
            logger.warning("could not resolve BlueZ device %s", device_path)
            return None
        address = getattr(value, "value", value)
        return address if isinstance(address, str) and address else None

    def _accept_fd(self, device_path: str, fd: int) -> None:
        try:
            accepted = socket.fromfd(
                fd, socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            accepted.setblocking(False)
        except OSError:
            logger.warning("could not accept RFCOMM fd for %s", device_path)
            return
        task = asyncio.create_task(self._open_link(device_path, accepted))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _open_link(self, device_path: str, accepted: socket.socket) -> None:
        try:
            reader, writer = await asyncio.open_connection(sock=accepted)
        except OSError:
            accepted.close()
            return

        address = await self._device_address(device_path)
        if address is None or not await is_trusted(self._trusted_devices, address):
            logger.warning("rejected RFCOMM peer %s", device_path)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            return

        link = RfcommDeviceLink(reader, writer)
        old_link = self._links.pop(device_path, None)
        if old_link is not None:
            await old_link.close()
        self._links[device_path] = link

        try:
            result = self._on_link(address, link)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("RFCOMM link handler failed for %s", address)
            await link.close()
            self._links.pop(device_path, None)

    def _drop_link(self, device_path: str) -> None:
        link = self._links.pop(device_path, None)
        if link is not None:
            task = asyncio.create_task(link.close())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _released(self) -> None:
        for device_path in tuple(self._links):
            self._drop_link(device_path)

    async def close(self) -> None:
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        if self._bus is None:
            return
        bus = self._bus
        profile = self._profile
        self._bus = None
        self._profile = None
        try:
            introspection = await bus.introspect("org.bluez", "/org/bluez")
            proxy = bus.get_proxy_object(
                "org.bluez", "/org/bluez", introspection
            )
            manager = proxy.get_interface("org.bluez.ProfileManager1")
            await manager.call_unregister_profile(PROFILE_PATH)
        finally:
            if profile is not None:
                bus.unexport(PROFILE_PATH, profile)
            for link in self._links.values():
                await link.close()
            self._links.clear()
            bus.disconnect()
