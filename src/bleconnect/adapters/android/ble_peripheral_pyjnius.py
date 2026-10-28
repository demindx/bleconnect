"""pyjnius bridge for the Android BLE peripheral."""

from __future__ import annotations

import logging
from collections.abc import Callable

from jnius import PythonJavaClass, autoclass, java_method

logger = logging.getLogger("bleconnect.android.ble")

Bridge = autoclass("org.bleconnect.app.BlePeripheralBridge")


def _to_java_bytes(data: bytes) -> bytes:
    """pyjnius converts Python bytes directly to Java byte[]."""
    return bytes(data)


def _to_python_bytes(value) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    tostring = getattr(value, "tostring", None)
    if callable(tostring):
        return tostring()
    return bytes(int(item) & 0xFF for item in value)


class _Listener(PythonJavaClass):
    __javainterfaces__ = ["org/bleconnect/app/BlePeripheralBridge$Listener"]
    __javacontext__ = "app"

    def __init__(self, transport: "PyjniusBlePeripheralTransport") -> None:
        super().__init__()
        self._transport = transport

    @java_method("(Ljava/lang/String;)V")
    def onLog(self, message: str) -> None:
        self._transport._handle_log(str(message))

    @java_method("([B)V")
    def onControlWrite(self, data) -> None:
        self._transport._handle_write("control", _to_python_bytes(data))

    @java_method("([B)V")
    def onClipboardWrite(self, data) -> None:
        self._transport._handle_write("clipboard", _to_python_bytes(data))

    @java_method("(I)V")
    def onConnectionState(self, state: int) -> None:
        self._transport._handle_connection(int(state) == 2)

    @java_method("(I)V")
    def onMtuChanged(self, mtu: int) -> None:
        self._transport._handle_mtu(int(mtu))


class PyjniusBlePeripheralTransport:
    def __init__(self, context, log: Callable[[str], None] | None = None) -> None:
        self._log = log or (lambda message: logger.info("%s", message))
        self._listener = _Listener(self)
        self._bridge = Bridge(context, self._listener)
        self._mtu = 23
        self._connected = False
        self._write_handler: Callable[[str, bytes], None] | None = None
        self._connection_handler: Callable[[bool], None] | None = None
        self._mtu_handler: Callable[[int], None] | None = None

    @property
    def mtu_size(self) -> int:
        return self._mtu

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._bridge.start()

    async def stop(self) -> None:
        self._bridge.stop()

    async def send_control(self, data: bytes) -> None:
        if not self._connected:
            raise ConnectionError("no BLE central is connected")
        if not self._bridge.sendControl(_to_java_bytes(data)):
            raise ConnectionError("could not queue BLE control indication")

    async def send_clipboard(self, data: bytes) -> None:
        if not self._connected:
            raise ConnectionError("no BLE central is connected")
        if not self._bridge.sendClipboard(_to_java_bytes(data)):
            raise ConnectionError("could not queue BLE clipboard indication")

    def set_write_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._write_handler = handler

    def set_connection_handler(self, handler: Callable[[bool], None]) -> None:
        self._connection_handler = handler

    def set_mtu_handler(self, handler: Callable[[int], None]) -> None:
        self._mtu_handler = handler

    def _handle_log(self, message: str) -> None:
        logger.info("bridge: %s", message)
        self._log(f"bridge: {message}")

    def _handle_write(self, kind: str, data: bytes) -> None:
        if self._write_handler is not None:
            self._write_handler(kind, data)

    def _handle_connection(self, connected: bool) -> None:
        self._connected = connected
        if self._connection_handler is not None:
            self._connection_handler(connected)

    def _handle_mtu(self, mtu: int) -> None:
        self._mtu = max(23, mtu)
        if self._mtu_handler is not None:
            self._mtu_handler(self._mtu)
