"""Pairing workflow and trusted-device persistence boundary."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .ports import (
    BluetoothDevice,
    BluetoothPairingPort,
    TrustedDevice,
    TrustedDevicesRepository,
)

_BLUETOOTH_ADDRESS = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class PairingService:
    """Coordinate discovery, OS pairing, and persistence of trusted peers."""

    def __init__(
        self,
        bluetooth: BluetoothPairingPort,
        trusted_devices: TrustedDevicesRepository,
    ) -> None:
        self._bluetooth = bluetooth
        self._trusted_devices = trusted_devices

    async def discover(self, timeout: float = 10.0) -> Sequence[BluetoothDevice]:
        if timeout <= 0:
            raise ValueError("discovery timeout must be positive")
        return await self._bluetooth.discover(timeout)

    async def pair_and_trust(self, address: str) -> TrustedDevice:
        if not _BLUETOOTH_ADDRESS.fullmatch(address):
            raise ValueError("invalid Bluetooth address")
        paired = await self._bluetooth.pair(address.upper())
        trusted = TrustedDevice(address=paired.address.upper(), name=paired.name)
        await self._trusted_devices.save_trusted(trusted)
        return trusted

    async def list_trusted(self) -> Sequence[TrustedDevice]:
        return await self._trusted_devices.list_trusted()

    async def forget(self, address: str) -> None:
        if not _BLUETOOTH_ADDRESS.fullmatch(address):
            raise ValueError("invalid Bluetooth address")
        await self._trusted_devices.remove_trusted(address.upper())
