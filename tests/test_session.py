import asyncio

from bleconnect.application.session import (
    PacketDispatcher,
    Session,
)
from bleconnect.protocol import Packet
from tests.support import paired_links


def test_dispatcher_routes_by_type() -> None:
    async def scenario() -> None:
        dispatcher = PacketDispatcher()
        received: list[Packet] = []

        async def handle(packet: Packet) -> None:
            received.append(packet)

        dispatcher.register("ping", handle)
        assert await dispatcher.dispatch(Packet("ping", {"ts": 1})) is True
        assert await dispatcher.dispatch(Packet("pong", {})) is False
        assert received == [Packet("ping", {"ts": 1})]

    asyncio.run(scenario())


def test_dispatcher_rejects_duplicate_registration() -> None:
    dispatcher = PacketDispatcher()
    dispatcher.register("ping", lambda packet: None)
    try:
        dispatcher.register("ping", lambda packet: None)
    except ValueError:
        return
    raise AssertionError("duplicate registration was accepted")


def test_session_dispatches_received_packet_and_stops() -> None:
    async def scenario() -> None:
        link, peer = paired_links()
        dispatcher = PacketDispatcher()
        received = asyncio.Event()
        packets: list[Packet] = []

        async def handle(packet: Packet) -> None:
            packets.append(packet)
            received.set()

        dispatcher.register("ping", handle)
        stop = asyncio.Event()
        session = Session(link, dispatcher)
        task = asyncio.create_task(session.run(stop))

        await peer.send(Packet("ping", {"ts": 7}))
        await asyncio.wait_for(received.wait(), 1)
        stop.set()
        await asyncio.wait_for(task, 1)

        assert packets == [Packet("ping", {"ts": 7})]

    asyncio.run(scenario())
