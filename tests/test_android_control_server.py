import asyncio
import json

from bleconnect.adapters.android.control import ControlServer


async def _request(port: int, payload: bytes) -> dict:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(payload)
        await writer.drain()
        line = await reader.readline()
        return json.loads(line.decode("utf-8"))
    finally:
        writer.close()
        await writer.wait_closed()


def test_control_server_handles_commands() -> None:
    async def handler(command: dict) -> dict:
        if command.get("command") == "echo":
            return {"ok": True, "value": command.get("value")}
        raise ValueError("unknown command")

    async def scenario() -> None:
        server = ControlServer(handler, port=0)
        await server.start()
        try:
            assert await _request(
                server.port, b'{"command":"echo","value":7}\n'
            ) == {"ok": True, "value": 7}
            error = await _request(server.port, b'{"command":"nope"}\n')
            assert error["ok"] is False
            assert "unknown command" in error["error"]
        finally:
            await server.close()

    asyncio.run(scenario())


def test_control_server_rejects_malformed_json() -> None:
    async def handler(command: dict) -> dict:
        return {"ok": True}

    async def scenario() -> None:
        server = ControlServer(handler, port=0)
        await server.start()
        try:
            response = await _request(server.port, b"not json\n")
            assert response["ok"] is False
        finally:
            await server.close()

    asyncio.run(scenario())
