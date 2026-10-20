"""Android clipboard adapter backed by ClipboardManager."""

from __future__ import annotations

import logging

from ...application.ports import ClipboardSnapshot

logger = logging.getLogger("bleconnect.android.clipboard")
_SENSITIVE_KEY = "android.content.extra.IS_SENSITIVE"


class AndroidClipboard:
    def __init__(self, context) -> None:
        from jnius import autoclass

        context_class = autoclass("android.content.Context")
        clip_data = autoclass("android.content.ClipData")
        clip_description = autoclass("android.content.ClipDescription")
        self._clip_data = clip_data
        self._sensitive_key = getattr(
            clip_description, "EXTRA_IS_SENSITIVE", _SENSITIVE_KEY
        )
        self._clipboard = context.getSystemService(context_class.CLIPBOARD_SERVICE)

    async def read_text(self) -> ClipboardSnapshot | None:
        try:
            clip = self._clipboard.getPrimaryClip()
            if clip is None or clip.getItemCount() == 0:
                return None
            text = clip.getItemAt(0).getText()
            if text is None:
                return None
            sensitive = False
            description = clip.getDescription()
            if description is not None:
                extras = description.getExtras()
                if extras is not None:
                    sensitive = bool(extras.getBoolean(self._sensitive_key))
            return ClipboardSnapshot(str(text), sensitive)
        except Exception:
            logger.info("clipboard read is unavailable in this context")
            return None

    async def write_text(self, text: str) -> None:
        clip = self._clip_data.newPlainText("BLEConnect", text)
        self._clipboard.setPrimaryClip(clip)
