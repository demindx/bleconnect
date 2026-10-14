"""RFCOMM server registered with BlueZ's ProfileManager."""

import asyncio
import inspect
import socket
from collections.abc import Callable
from typing import Any

from ...application.ports import DeviceLink
from .bluetooth_rfcomm import RfcommDeviceLink

SERVICE_UUID = "d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10"
PROFILE_PATH = "/org/bleconnect/Profile"
DEFAULT_RFCOMM_CHANNEL = 24


def _make_profile(server):
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
    """Publish a private RFCOMM service and hand accepted links to a callback."""

    def __init__(self, on_link: Callable[[str, DeviceLink], Any]) -> None:
        self._on_link = on_link
        self._bus = None
        self._profile = None
        self._links: dict[str, RfcommDeviceLink] = {}

    async def start(
        self,
        channel: int = DEFAULT_RFCOMM_CHANNEL,
        service_uuid: str = SERVICE_UUID,
    ) -> None:
        if not 1 <= channel <= 30:
            raise ValueError("RFCOMM channel must be between 1 and 30")
        try:
            from dbus_next import BusType, Variant
            from dbus_next.aio import MessageBus
        except ImportError as exc:
            raise RuntimeError(
                "BlueZ RFCOMM server needs the optional dependency: uv sync --extra linux"
            ) from exc

        self._bus = await MessageBus(
            bus_type=BusType.SYSTEM, negotiate_unix_fd=True
        ).connect()
        self._profile = _make_profile(self)
        self._bus.export(PROFILE_PATH, self._profile)
        try:
            introspection = await self._bus.introspect("org.bluez", "/org/bluez")
            proxy = self._bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
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

    def _accept_fd(self, device_path: str, fd: int) -> None:
        try:
            accepted = socket.fromfd(
                fd, socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            accepted.setblocking(False)
        except OSError:
            return
        asyncio.create_task(self._open_link(device_path, accepted))

    async def _open_link(self, device_path: str, accepted: socket.socket) -> None:
        try:
            reader, writer = await asyncio.open_connection(sock=accepted)
        except OSError:
            accepted.close()
            return
        link = RfcommDeviceLink(reader, writer)
        old_link = self._links.pop(device_path, None)
        if old_link is not None:
            await old_link.close()
        self._links[device_path] = link
        result = self._on_link(device_path, link)
        if inspect.isawaitable(result):
            await result

    def _drop_link(self, device_path: str) -> None:
        link = self._links.pop(device_path, None)
        if link is not None:
            asyncio.create_task(link.close())

    def _released(self) -> None:
        for device_path in tuple(self._links):
            self._drop_link(device_path)

    async def close(self) -> None:
        if self._bus is None:
            return
        bus = self._bus
        profile = self._profile
        self._bus = None
        self._profile = None
        try:
            introspection = await bus.introspect("org.bluez", "/org/bluez")
            proxy = bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
            manager = proxy.get_interface("org.bluez.ProfileManager1")
            await manager.call_unregister_profile(PROFILE_PATH)
        finally:
            if profile is not None:
                bus.unexport(PROFILE_PATH, profile)
            for link in self._links.values():
                await link.close()
            self._links.clear()
            bus.disconnect()
