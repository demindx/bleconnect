import asyncio

import pytest

from bleconnect.application.pairing_service import PairingService
from bleconnect.application.ports import BluetoothDevice, TrustedDevice
from bleconnect.adapters.linux.trusted_devices import JsonTrustedDevicesRepository


class FakeBluetooth:
    def __init__(self) -> None:
        self.paired: list[str] = []

    async def discover(self, timeout: float = 10.0):
        return [BluetoothDevice("AA:BB:CC:DD:EE:FF", "Fedora laptop")]

    async def pair(self, address: str) -> BluetoothDevice:
        self.paired.append(address)
        return BluetoothDevice(address, "Fedora laptop", paired=True)


def test_pairing_only_saves_peer_after_platform_pair_succeeds(tmp_path) -> None:
    bluetooth = FakeBluetooth()
    repository = JsonTrustedDevicesRepository(tmp_path / "trusted.json")
    service = PairingService(bluetooth, repository)

    async def scenario() -> None:
        trusted = await service.pair_and_trust("aa:bb:cc:dd:ee:ff")
        assert trusted == TrustedDevice("AA:BB:CC:DD:EE:FF", "Fedora laptop")
        assert await service.list_trusted() == [trusted]
        await service.forget(trusted.address)
        assert await service.list_trusted() == []

    asyncio.run(scenario())
    assert bluetooth.paired == ["AA:BB:CC:DD:EE:FF"]


def test_pairing_rejects_malformed_address_before_calling_platform(tmp_path) -> None:
    bluetooth = FakeBluetooth()
    service = PairingService(
        bluetooth, JsonTrustedDevicesRepository(tmp_path / "trusted.json")
    )

    with pytest.raises(ValueError, match="invalid Bluetooth address"):
        asyncio.run(service.pair_and_trust("not-a-device"))
    assert bluetooth.paired == []


def test_trusted_repository_atomically_persists_entries_with_private_mode(tmp_path) -> None:
    path = tmp_path / "config" / "trusted.json"
    repository = JsonTrustedDevicesRepository(path)
    device = TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone")

    async def scenario() -> None:
        await repository.save_trusted(device)
        await repository.save_trusted(device)
        assert await repository.list_trusted() == [device]

    asyncio.run(scenario())
    assert path.stat().st_mode & 0o777 == 0o600
