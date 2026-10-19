import asyncio

from bleconnect.platform.android import build_android_app
from bleconnect.platform.linux import build_linux_app
from bleconnect.presentation.app_controller import AppController
from tests.support import MemoryClipboard, paired_links


def test_linux_builder_returns_controller() -> None:
    async def scenario() -> None:
        link, _ = paired_links()
        controller = build_linux_app(
            control_link=link, clipboard=MemoryClipboard("hello")
        )
        assert isinstance(controller, AppController)
        await controller.stop()

    asyncio.run(scenario())


def test_android_builder_returns_controller() -> None:
    async def scenario() -> None:
        link, _ = paired_links()
        controller = build_android_app(
            control_link=link, clipboard=MemoryClipboard("hello")
        )
        assert isinstance(controller, AppController)
        await controller.stop()

    asyncio.run(scenario())
