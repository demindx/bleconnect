import asyncio

from bleconnect.application.clipboard_service import ClipboardService
from bleconnect.application.session import ConnectionState
from bleconnect.presentation.app_controller import AppController
from bleconnect.presentation.view_models import AppViewModel
from bleconnect.protocol import Packet
from tests.support import MemoryClipboard, paired_links


def test_controller_exposes_state_and_commands() -> None:
    async def scenario() -> None:
        link, peer = paired_links()
        clipboard = MemoryClipboard("hello")
        controller = AppController(
            link, ClipboardService(clipboard, link)
        )
        states = []
        controller.subscribe(states.append)

        assert await controller.send_clipboard() is True
        assert await asyncio.wait_for(peer.incoming.get(), 1) == Packet(
            "clipboard", {"text": "hello"}
        )

        controller.pause_clipboard()
        assert controller.state.clipboard_paused is True
        assert await controller.send_clipboard() is False

        controller.resume_clipboard()
        controller.set_connection_state(
            ConnectionState.CONNECTED, peer_name="Phone"
        )
        assert controller.state.connection is ConnectionState.CONNECTED
        assert controller.state.peer_name == "Phone"

        await controller.find_phone(duration_s=10, volume=0.5)
        assert await asyncio.wait_for(peer.incoming.get(), 1) == Packet(
            "find_phone", {"duration_s": 10, "volume": 0.5}
        )

        assert states
        await controller.stop()

    asyncio.run(scenario())


def test_view_model_mirrors_controller_state() -> None:
    async def scenario() -> None:
        link, _ = paired_links()
        clipboard = MemoryClipboard("hello")
        controller = AppController(
            link, ClipboardService(clipboard, link)
        )
        view_model = AppViewModel(controller)
        states = []
        view_model.subscribe(states.append)

        controller.pause_clipboard()
        assert view_model.clipboard_paused is True
        assert states[-1].clipboard_paused is True

        view_model.resume_clipboard()
        assert view_model.clipboard_paused is False

        view_model.dispose()
        controller.pause_clipboard()
        assert view_model.clipboard_paused is False

        await controller.stop()

    asyncio.run(scenario())
