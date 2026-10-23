"""Linux BLE central adapter and a transport-neutral GATT link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from ...ble_protocol import (
    BLE_CLIPBOARD_CHARACTERISTIC_UUID,
    BLE_CONTROL_CHARACTERISTIC_UUID,
    BLE_SERVICE_UUID,
    DEFAULT_MTU,
    MessageAssembler,
    decode_frame,
    encode_frame,
    encode_packet_chunks,
)
from ...messages import CLIPBOARD, CONTROL_TYPES
from ...protocol import Packet, ProtocolError


class BleUnavailableError(RuntimeError):
    """Raised when BLE discovery or connection cannot be started."""


class BleTransport(Protocol):
    @property
    def mtu_size(self) -> int:
        """Negotiated ATT MTU, or the BLE minimum when unknown."""

    async def connect(self) -> None:
        """Open the GATT connection."""

    async def disconnect(self) -> None:
        """Close the GATT connection."""

    async def write(self, characteristic: str, data: bytes) -> None:
        """Write one characteristic value with a response."""

    async def start_notify(
        self, characteristic: str, callback: Callable[[bytes], None]
    ) -> None:
        """Subscribe to characteristic notifications or indications."""

    def set_disconnect_handler(self, handler: Callable[[], None]) -> None:
        """Register a callback invoked when the transport disconnects."""


class BleakTransport:
    """Bleak-backed GATT transport. Bleak is imported only when used."""

    def __init__(
        self,
        device: object,
        *,
        pair: bool = False,
        connect_timeout: float = 30.0,
    ) -> None:
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        self._device = device
        self._pair = pair
        self._connect_timeout = connect_timeout
        self._client = None
        self._disconnect_handler: Callable[[], None] | None = None

    def set_disconnect_handler(self, handler: Callable[[], None]) -> None:
        self._disconnect_handler = handler

    async def connect(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as exc:
            raise BleUnavailableError(
                "BLE support needs the optional dependency: uv sync --extra linux"
            ) from exc
        self._client = BleakClient(
            self._device,
            disconnected_callback=self._on_disconnected,
            pair=self._pair,
            timeout=self._connect_timeout,
        )
        await self._client.connect()

    @property
    def mtu_size(self) -> int:
        if self._client is None:
            return DEFAULT_MTU
        try:
            return int(self._client.mtu_size)
        except Exception:
            return DEFAULT_MTU

    async def write(self, characteristic: str, data: bytes) -> None:
        if self._client is None:
            raise ConnectionError("BLE transport is not connected")
        await self._client.write_gatt_char(characteristic, data, response=True)

    async def start_notify(
        self, characteristic: str, callback: Callable[[bytes], None]
    ) -> None:
        if self._client is None:
            raise ConnectionError("BLE transport is not connected")
        await self._client.start_notify(
            characteristic, lambda _characteristic, data: callback(bytes(data))
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            client = self._client
            self._client = None
            await client.disconnect()

    def _on_disconnected(self, _client: object) -> None:
        if self._disconnect_handler is not None:
            self._disconnect_handler()


class BleCentralLink:
    """PacketLink over BLE control and clipboard characteristics."""

    def __init__(
        self, transport: BleTransport, *, mtu: int | None = None
    ) -> None:
        self._transport = transport
        self._mtu = mtu or DEFAULT_MTU
        self._assembler = MessageAssembler()
        self._incoming: asyncio.Queue[Packet | None] = asyncio.Queue()
        self._message_id = 0
        self._closed = False
        transport.set_disconnect_handler(self._on_disconnect)

    @property
    def mtu_size(self) -> int:
        return self._mtu

    async def connect(self) -> None:
        await self._transport.connect()
        self._mtu = max(DEFAULT_MTU, self._transport.mtu_size)
        await self._transport.start_notify(
            BLE_CONTROL_CHARACTERISTIC_UUID, self._on_frame
        )
        await self._transport.start_notify(
            BLE_CLIPBOARD_CHARACTERISTIC_UUID, self._on_frame
        )

    async def send(self, packet: Packet) -> None:
        if self._closed:
            raise ConnectionError("BLE link is closed")
        if packet.type == CLIPBOARD:
            characteristic = BLE_CLIPBOARD_CHARACTERISTIC_UUID
        elif packet.type in CONTROL_TYPES:
            characteristic = BLE_CONTROL_CHARACTERISTIC_UUID
        else:
            raise ProtocolError("BLE link only carries control and clipboard packets")

        for frame in encode_packet_chunks(
            packet, self._next_message_id(), self._mtu
        ):
            await self._transport.write(characteristic, encode_frame(frame))

    async def receive(self) -> Packet:
        if self._closed and self._incoming.empty():
            raise ConnectionError("BLE link is closed")
        packet = await self._incoming.get()
        if packet is None:
            raise ConnectionError("BLE link disconnected")
        return packet

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._transport.disconnect()
        finally:
            self._incoming.put_nowait(None)

    def _next_message_id(self) -> int:
        message_id = self._message_id
        self._message_id = (self._message_id + 1) & 0xFFFFFFFF
        return message_id

    def _on_frame(self, data: bytes) -> None:
        try:
            packet = self._assembler.add(decode_frame(data))
        except ProtocolError:
            return
        if packet is not None:
            self._incoming.put_nowait(packet)

    def _on_disconnect(self) -> None:
        self._closed = True
        self._incoming.put_nowait(None)


async def find_ble_service(
    service_uuid: str = BLE_SERVICE_UUID, timeout: float = 10.0
) -> object:
    """Find a device advertising the given service UUID."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    try:
        from bleak import BleakScanner
    except ImportError as exc:
        raise BleUnavailableError(
            "BLE support needs the optional dependency: uv sync --extra linux"
        ) from exc

    def matches(_device: object, advertisement: object) -> bool:
        service_uuids = getattr(advertisement, "service_uuids", None) or []
        return service_uuid.lower() in {
            str(uuid).lower() for uuid in service_uuids
        }

    device = await BleakScanner.find_device_by_filter(matches, timeout=timeout)
    if device is None:
        raise BleUnavailableError(
            f"BLE service {service_uuid} was not found within {timeout} seconds"
        )
    return device


async def connect_ble_service(
    service_uuid: str = BLE_SERVICE_UUID,
    *,
    address: str | None = None,
    timeout: float = 10.0,
    pair: bool = False,
    connect_timeout: float = 30.0,
    attempts: int = 2,
) -> BleCentralLink:
    """Connect to the BLE peripheral, retrying a dropped or stale link."""
    if attempts <= 0:
        raise ValueError("attempts must be positive")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            device = address if address is not None else await find_ble_service(
                service_uuid, timeout
            )
            link = BleCentralLink(
                BleakTransport(
                    device,
                    pair=pair,
                    connect_timeout=connect_timeout,
                )
            )
            try:
                await link.connect()
            except Exception:
                await link.close()
                raise
            return link
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            if address is None:
                await asyncio.sleep(1.0)

    raise BleUnavailableError(
        f"could not connect to the BLE service: {last_error}"
    ) from last_error
