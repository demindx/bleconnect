"""BlueZ system-bus adapter for device discovery and pairing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from ...application.ports import BluetoothDevice

BLUEZ_SERVICE = "org.bluez"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"


def _value(value: Any) -> Any:
    """Unwrap a dbus-next Variant while remaining testable without dbus-next."""
    return getattr(value, "value", value)


def _devices_from_objects(objects: Mapping[str, Any]) -> list[BluetoothDevice]:
    devices: list[BluetoothDevice] = []
    for interfaces in objects.values():
        properties = interfaces.get(DEVICE_INTERFACE)
        if properties is None:
            continue
        address = _value(properties.get("Address", ""))
        if not isinstance(address, str) or not address:
            continue
        name = _value(properties.get("Alias", properties.get("Name", address)))
        paired = _value(properties.get("Paired", False))
        devices.append(
            BluetoothDevice(
                address=address.upper(),
                name=name if isinstance(name, str) else address,
                paired=bool(paired),
            )
        )
    return sorted(devices, key=lambda device: (device.name.casefold(), device.address))


class BluezPairingAdapter:
    """Use BlueZ D-Bus and the desktop's default agent for pairing prompts.

    `dbus-next` is an optional Linux dependency. Pairing confirmation is handled
    by the registered desktop agent, so this adapter never accepts a passkey
    without user confirmation.
    """

    def __init__(self, bus_factory=None, sleep=asyncio.sleep) -> None:
        self._bus_factory = bus_factory
        self._sleep = sleep

    async def _connect_bus(self):
        if self._bus_factory is not None:
            return await self._bus_factory()
        try:
            from dbus_next import BusType
            from dbus_next.aio import MessageBus
        except ImportError as exc:
            raise RuntimeError(
                "BlueZ support needs the optional dependency: uv sync --extra linux"
            ) from exc
        return await MessageBus(bus_type=BusType.SYSTEM).connect()

    async def _interface(self, bus, path: str, interface: str):
        introspection = await bus.introspect(BLUEZ_SERVICE, path)
        proxy = bus.get_proxy_object(BLUEZ_SERVICE, path, introspection)
        return proxy.get_interface(interface)

    async def _managed_objects(self, bus) -> Mapping[str, Any]:
        manager = await self._interface(bus, "/", OBJECT_MANAGER)
        return await manager.call_get_managed_objects()

    async def discover(self, timeout: float = 10.0) -> Sequence[BluetoothDevice]:
        if timeout <= 0:
            raise ValueError("discovery timeout must be positive")
        bus = await self._connect_bus()
        started: list[tuple[str, Any]] = []
        try:
            objects = await self._managed_objects(bus)
            for path, interfaces in objects.items():
                if ADAPTER_INTERFACE not in interfaces:
                    continue
                adapter = await self._interface(bus, path, ADAPTER_INTERFACE)
                await adapter.call_start_discovery()
                started.append((path, adapter))
            if not started:
                raise RuntimeError("no BlueZ Bluetooth adapter is available")
            await self._sleep(timeout)
            return _devices_from_objects(await self._managed_objects(bus))
        finally:
            for _, adapter in reversed(started):
                try:
                    await adapter.call_stop_discovery()
                except Exception:
                    pass
            bus.disconnect()

    async def pair(self, address: str) -> BluetoothDevice:
        address = address.upper()
        bus = await self._connect_bus()
        try:
            objects = await self._managed_objects(bus)
            target = next(
                (
                    (path, interfaces)
                    for path, interfaces in objects.items()
                    if DEVICE_INTERFACE in interfaces
                    and _value(interfaces[DEVICE_INTERFACE].get("Address", "")).upper()
                    == address
                ),
                None,
            )
            if target is None:
                raise LookupError(f"Bluetooth device {address} was not discovered")
            path, _ = target
            device = await self._interface(bus, path, DEVICE_INTERFACE)
            await device.call_pair()
            try:
                from dbus_next import Variant
            except ImportError as exc:
                raise RuntimeError(
                    "BlueZ support needs the optional dependency: uv sync --extra linux"
                ) from exc
            properties = await self._interface(
                bus, path, "org.freedesktop.DBus.Properties"
            )
            await properties.call_set(DEVICE_INTERFACE, "Trusted", Variant("b", True))
            refreshed = await self._managed_objects(bus)
            return next(
                device_info
                for device_info in _devices_from_objects(refreshed)
                if device_info.address == address
            )
        finally:
            bus.disconnect()
