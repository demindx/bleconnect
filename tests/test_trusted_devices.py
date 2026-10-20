import asyncio

import pytest

from bleconnect.adapters.linux.trusted_devices import (
    JsonTrustedDevicesRepository,
    is_trusted,
)
from bleconnect.application.ports import TrustedDevice


def test_trusted_devices_round_trip(tmp_path) -> None:
    path = tmp_path / "trusted.json"

    async def scenario() -> None:
        repository = JsonTrustedDevicesRepository(path)
        await repository.save_trusted(TrustedDevice("aa:bb:cc:dd:ee:ff", "Phone"))
        await repository.save_trusted(TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone 2"))
        await repository.save_trusted(TrustedDevice("11:22:33:44:55:66", "Laptop"))

        assert await repository.list_trusted() == [
            TrustedDevice("11:22:33:44:55:66", "Laptop"),
            TrustedDevice("AA:BB:CC:DD:EE:FF", "Phone 2"),
        ]
        assert await is_trusted(repository, "aa:bb:cc:dd:ee:ff") is True
        assert await is_trusted(repository, "00:00:00:00:00:00") is False

        await repository.remove_trusted("aa:bb:cc:dd:ee:ff")
        assert await repository.list_trusted() == [
            TrustedDevice("11:22:33:44:55:66", "Laptop")
        ]

    asyncio.run(scenario())
    assert path.stat().st_mode & 0o777 == 0o600


def test_trusted_devices_reject_malformed_json(tmp_path) -> None:
    path = tmp_path / "trusted.json"
    path.write_text("{not json", encoding="utf-8")

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await JsonTrustedDevicesRepository(path).list_trusted()

    asyncio.run(scenario())


def test_trusted_devices_reject_invalid_entries(tmp_path) -> None:
    path = tmp_path / "trusted.json"
    path.write_text('[{"address": "aa", "name": 1}]', encoding="utf-8")

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await JsonTrustedDevicesRepository(path).list_trusted()

    asyncio.run(scenario())
