"""DataUpdateCoordinator for Aosu Cameras."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AosuApiError, AosuAuthError, AosuCameraData, AsyncAosuClient
from .const import (
    DOMAIN,
    EVENT_DOORBELL_RING,
    EVENT_FACE_RECOGNIZED,
    EVENT_PERSON_DETECTED,
)

_LOGGER = logging.getLogger(__name__)


class AosuCoordinator(DataUpdateCoordinator[dict[str, AosuCameraData]]):
    """Polls Aosu Cloud for camera status, snapshots, and person/ring events."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AsyncAosuClient,
        scan_interval: int = 30,
        compreface_url: str = "",
        compreface_api_key: str = "",
        face_threshold: float = 0.75,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.compreface_url = compreface_url.strip()
        self.compreface_api_key = compreface_api_key.strip()
        self.face_threshold = face_threshold
        self._last_seen_event_ts: dict[str, int] = {}
        self._snapshot_cache: dict[str, tuple[int | None, bytes]] = {}
        self._last_face_cache: dict[str, tuple[str | None, float | None]] = {}

    async def _async_update_data(self) -> dict[str, AosuCameraData]:
        try:
            devices = await self.client.async_get_devices()
        except AosuAuthError:
            try:
                await self.client.async_login()
                devices = await self.client.async_get_devices()
            except Exception as err:
                raise UpdateFailed(f"Re-authentification Aosu échouée : {err}") from err
        except (AosuApiError, Exception) as err:
            raise UpdateFailed(f"Erreur API Aosu : {err}") from err

        by_sn: dict[str, AosuCameraData] = {d.sn: d for d in devices if d.sn}
        online_sns = [d.sn for d in devices if d.online]

        events: list[dict[str, Any]] = []
        card_events: list[dict[str, Any]] = []
        if online_sns:
            try:
                events = await self.client.async_get_image_events(online_sns, count=15)
            except Exception as err:
                _LOGGER.warning("Impossible de récupérer les snapshots Aosu : %s", err)
            try:
                card_events = await self.client.async_get_card_events(online_sns, count=20, hours_back=48)
            except Exception as err:
                _LOGGER.debug("Impossible de récupérer l'historique carte SD Aosu : %s", err)

        # Group latest event and recent history per camera
        latest_event_by_sn: dict[str, dict[str, Any]] = {}
        history_by_sn: dict[str, list[dict[str, Any]]] = {}
        for ev in card_events + events:
            sn = str(ev.get("sn") or "")
            if not sn:
                continue
            ev_ts_item = int(ev.get("eventTime") or 0)
            prev = latest_event_by_sn.get(sn)
            if prev is None or ev_ts_item > int(prev.get("eventTime") or 0):
                latest_event_by_sn[sn] = ev
            hist = history_by_sn.setdefault(sn, [])
            if len(hist) < 10 and not any(h.get("event_time") == ev_ts_item for h in hist):
                hist.append(
                    {
                        "event_time": ev_ts_item,
                        "types": ev.get("uniformType") or [],
                        "event_type": ev.get("eventType") or "",
                        "has_image": bool(ev.get("imageUrl")),
                    }
                )

        for sn, cam in by_sn.items():
            cam.recent_events = sorted(
                history_by_sn.get(sn, []),
                key=lambda x: x["event_time"],
                reverse=True,
            )[:10]
            ev = latest_event_by_sn.get(sn)
            img_url = cam.cover_image_url
            ev_ts = cam.last_event_time
            ev_types: list[str] = []

            if ev:
                ev_ts = int(ev.get("eventTime") or ev_ts or 0) or ev_ts
                raw_types = ev.get("uniformType")
                if isinstance(raw_types, list):
                    ev_types = [str(t) for t in raw_types]
                elif raw_types:
                    ev_types = [str(raw_types)]
                if ev.get("imageUrl"):
                    img_url = str(ev["imageUrl"])

            cam.last_event_time = ev_ts
            cam.last_event_types = ev_types

            # Restore cached face result
            if sn in self._last_face_cache:
                cam.last_face_name, cam.last_face_confidence = self._last_face_cache[sn]

            # Download snapshot only when event timestamp changed (or cache empty)
            cached = self._snapshot_cache.get(sn)
            is_new_event = (
                ev_ts is not None
                and sn in self._last_seen_event_ts
                and ev_ts > self._last_seen_event_ts[sn]
            )
            need_download = img_url and (cached is None or cached[0] != ev_ts)

            if need_download and img_url:
                try:
                    img_bytes = await self.client.async_download_image(img_url)
                    self._snapshot_cache[sn] = (ev_ts, img_bytes)
                    cam.last_snapshot_bytes = img_bytes
                except Exception as err:
                    _LOGGER.debug("Échec téléchargement snapshot %s : %s", sn, err)
                    if cached:
                        cam.last_snapshot_bytes = cached[1]
            elif cached:
                cam.last_snapshot_bytes = cached[1]

            if ev_ts is not None:
                self._last_seen_event_ts.setdefault(sn, ev_ts)

            if is_new_event and ev_ts is not None:
                self._last_seen_event_ts[sn] = ev_ts
                await self._handle_new_event(cam, ev_types)

        return by_sn

    async def _handle_new_event(self, cam: AosuCameraData, ev_types: list[str]) -> None:
        base_payload = {
            "sn": cam.sn,
            "name": cam.name,
            "event_time": cam.last_event_time,
            "event_types": ev_types,
        }
        if "ring" in ev_types:
            self.hass.bus.async_fire(EVENT_DOORBELL_RING, base_payload)
        if "person" in ev_types:
            self.hass.bus.async_fire(EVENT_PERSON_DETECTED, base_payload)

        # Optional local facial recognition via CompreFace on person/ring events
        if (
            self.compreface_url
            and self.compreface_api_key
            and cam.last_snapshot_bytes
            and ("person" in ev_types or "ring" in ev_types or not ev_types)
        ):
            try:
                face_name, confidence = await self.client.async_recognize_face_compreface(
                    cam.last_snapshot_bytes,
                    self.compreface_url,
                    self.compreface_api_key,
                    self.face_threshold,
                )
                if face_name:
                    cam.last_face_name = face_name
                    cam.last_face_confidence = confidence
                    self._last_face_cache[cam.sn] = (face_name, confidence)
                    self.hass.bus.async_fire(
                        EVENT_FACE_RECOGNIZED,
                        {
                            **base_payload,
                            "person": face_name,
                            "confidence": confidence,
                            "is_known": face_name != "Inconnu",
                        },
                    )
            except Exception as err:
                _LOGGER.warning("Erreur reconnaissance faciale locale (%s) : %s", cam.name, err)
