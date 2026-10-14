import asyncio

from bleconnect.adapters.linux.bluetooth_rfcomm import RfcommDeviceLink
from bleconnect.protocol import encode_packet, packet, read_packet


def test_link_sends_and_receives_framed_packets() -> None:
    async def scenario() -> None:
        received: list[dict[str, object]] = []

        async def peer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received.append(await read_packet(reader))
            writer.write(encode_packet(packet("pong")))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(peer, "127.0.0.1", 0)
        address = server.sockets[0].getsockname()
        reader, writer = await asyncio.open_connection("127.0.0.1", address[1])
        link = RfcommDeviceLink(reader, writer)
        try:
            await link.send(packet("ping"))
            assert await link.receive() == packet("pong")
            assert received == [packet("ping")]
        finally:
            await link.close()
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
