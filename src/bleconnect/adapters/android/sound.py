"""Android find-phone sound adapter."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("bleconnect.android.sound")


class AndroidSoundPlayer:
    def __init__(self, context) -> None:
        from jnius import autoclass

        context_class = autoclass("android.content.Context")
        self._audio_manager_class = autoclass("android.media.AudioManager")
        self._ringtone_manager = autoclass("android.media.RingtoneManager")
        self._context = context
        self._audio = context.getSystemService(context_class.AUDIO_SERVICE)
        self._ringtone = None
        self._previous_volume: int | None = None

    async def play_find_phone(self, duration_s: float, volume: float) -> None:
        if duration_s <= 0:
            raise ValueError("duration must be positive")
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between 0 and 1")
        self._start(volume)
        try:
            await asyncio.sleep(duration_s)
        finally:
            self._stop()

    async def stop(self) -> None:
        self._stop()

    def _start(self, volume: float) -> None:
        self._stop()
        stream = self._audio_manager_class.STREAM_MUSIC
        try:
            self._previous_volume = self._audio.getStreamVolume(stream)
            maximum = self._audio.getStreamMaxVolume(stream)
            target = max(1, min(maximum, int(round(maximum * volume))))
            self._audio.setStreamVolume(stream, target, 0)
        except Exception:
            logger.warning("could not raise media volume; playing at current level")

        uri = self._ringtone_manager.getDefaultUri(
            self._ringtone_manager.TYPE_ALARM
        )
        ringtone = self._ringtone_manager.getRingtone(self._context, uri)
        self._ringtone = ringtone
        ringtone.play()

    def _stop(self) -> None:
        if self._ringtone is not None:
            try:
                self._ringtone.stop()
            except Exception:
                logger.warning("could not stop the find-phone sound")
            self._ringtone = None

        if self._previous_volume is not None:
            try:
                self._audio.setStreamVolume(
                    self._audio_manager_class.STREAM_MUSIC,
                    self._previous_volume,
                    0,
                )
            except Exception:
                logger.warning("could not restore media volume")
            self._previous_volume = None
