import asyncio
from collections.abc import Sequence

import pytest

from bleconnect.application.pairing_service import PairingService
from bleconnect.application.ports import BluetoothDevice, TrustedDevice


class FakePairing:
    def __init__(self) -> None:
        self.discovered: list[BluetoothDevice] = []
        self.paired: list[str] = []

    async def discover(self, timeout: float = 10.0) -> Sequence[BluetoothDevice]:
        return self.discovered

    async def pair(self, address: str) -> BluetoothDevice:
        self.paired.append(address)
        return BluetoothDevice(address, "Phone", True)


class FakeTrustedDevices:
    def __init__(self) -> None:
        self.devices: list[TrustedDevice] = []

    async def list_trusted(self) -> Sequence[TrustedDevice]:
        return self.devices

    async def save_trusted(self, device: TrustedDevice) -> None:
        self.devices.append(device)

    async def remove_trusted(self, address: str) -> None:
        self.devices = [
            device for device in self.devices if device.address != address
        ]


def test_pair_and_trust_normalizes_address() -> None:
    async def scenario() -> None:
        bluetooth = FakePairing()
        repository = FakeTrustedDevices()
        service = PairingService(bluetooth, repository)

        trusted = await service.pair_and_trust("aa:bb:cc:dd:ee:ff")

        assert bluetooth.paired == ["AA:BB:CC:DD:EE:FF"]
        assert trusted == TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone")
        assert repository.devices == [trusted]

    asyncio.run(scenario())


def test_pair_rejects_invalid_address() -> None:
    async def scenario() -> None:
        service = PairingService(FakePairing(), FakeTrustedDevices())
        with pytest.raises(ValueError):
            await service.pair_and_trust("not-an-address")

    asyncio.run(scenario())


def test_discover_rejects_non_positive_timeout() -> None:
    async def scenario() -> None:
        service = PairingService(FakePairing(), FakeTrustedDevices())
        with pytest.raises(ValueError):
            await service.discover(0)

    asyncio.run(scenario())


def test_forget_removes_device() -> None:
    async def scenario() -> None:
        repository = FakeTrustedDevices()
        repository.devices = [TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone")]
        service = PairingService(FakePairing(), repository)

        await service.forget("aa:bb:cc:dd:ee:ff")
        assert repository.devices == []

    asyncio.run(scenario())
