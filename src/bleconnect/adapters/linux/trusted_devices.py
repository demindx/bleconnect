"""JSON repository for trusted Bluetooth peer metadata on Linux."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path

from ...application.ports import TrustedDevice, TrustedDevicesRepository


class JsonTrustedDevicesRepository:
    """Persist non-secret device names and addresses in the user config dir."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            config_home = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )
            path = config_home / "bleconnect" / "trusted_devices.json"
        self._path = Path(path).expanduser()
        self._lock = asyncio.Lock()

    async def list_trusted(self) -> Sequence[TrustedDevice]:
        async with self._lock:
            return await asyncio.to_thread(self._load)

    async def save_trusted(self, device: TrustedDevice) -> None:
        async with self._lock:
            devices = {
                item.address.upper(): TrustedDevice(item.address.upper(), item.name)
                for item in await asyncio.to_thread(self._load)
            }
            devices[device.address.upper()] = TrustedDevice(
                address=device.address.upper(), name=device.name
            )
            await asyncio.to_thread(
                self._save, sorted(devices.values(), key=lambda item: item.address)
            )

    async def remove_trusted(self, address: str) -> None:
        async with self._lock:
            devices = {
                item.address: item
                for item in await asyncio.to_thread(self._load)
                if item.address.casefold() != address.casefold()
            }
            await asyncio.to_thread(
                self._save, sorted(devices.values(), key=lambda item: item.address)
            )

    def _load(self) -> list[TrustedDevice]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read trusted devices from {self._path}") from exc
        if not isinstance(raw, list):
            raise ValueError("trusted device data must be a JSON array")

        devices: list[TrustedDevice] = []
        for item in raw:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("address"), str)
                or not isinstance(item.get("name"), str)
            ):
                raise ValueError("trusted device entry has an invalid shape")
            devices.append(TrustedDevice(item["address"], item["name"]))
        return devices

    def _save(self, devices: list[TrustedDevice]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = [device.__dict__ for device in devices]
        try:
            with temp_path.open("w", encoding="utf-8") as target:
                json.dump(payload, target, ensure_ascii=False, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self._path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


async def is_trusted(
    repository: TrustedDevicesRepository, address: str
) -> bool:
    """Return True when the address is present in the trusted repository."""
    target = address.upper()
    return any(
        device.address.upper() == target
        for device in await repository.list_trusted()
    )
