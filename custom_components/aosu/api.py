"""Self-contained async API client for the Aosu Home Assistant integration."""

from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

GZ_SIGN_SALT = "&sM&GGlUCSXjZqQNxmkdU^scUs**0R@C"
PASSWORD_AES_KEY = b"PZR1ryiUhJloWoRd"
PASSWORD_AES_IV = b"PZR1ryiUhJloWoRd"

REGION_HOSTS: dict[str, str] = {
    "eu": "api-eu.aosulife.com",
    "us": "api.aosulife.com",
    "ap": "api-ap.aosulife.com",
    "cn": "api-cn.aosulife.com",
}


class AosuAuthError(Exception):
    """Raised when authentication fails."""


class AosuApiError(Exception):
    """Raised when an Aosu Cloud API call fails."""


def compute_gz_sign(request_uuid: str, timestamp_ms: int) -> str:
    payload = f"uuid:{request_uuid}:t:{timestamp_ms}:{GZ_SIGN_SALT}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest().lower()


def encrypt_password(password: str) -> str:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(PASSWORD_AES_KEY), modes.CBC(PASSWORD_AES_IV))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


@dataclass
class AosuCameraData:
    sn: str
    name: str
    model: str
    dev_type: int
    svc_type: str
    sn_coop: str
    online: bool
    battery: int | None
    wifi_signal: int | None
    cover_image_url: str | None
    last_event_time: int | None
    last_event_types: list[str] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    last_snapshot_bytes: bytes | None = None
    last_face_name: str | None = None
    last_face_confidence: float | None = None


class AsyncAosuClient:
    """Async HTTP client for Aosu Cloud REST + optional local CompreFace recognition."""

    def __init__(
        self,
        email: str,
        password: str,
        region: str = "eu",
        timeout: float = 15.0,
    ) -> None:
        self.email = email.strip().lower()
        self.password = password
        self.region = region.lower()
        self.uid: str = ""
        self.sid: str = ""
        self.device_imei = str(uuid.uuid4()).replace("-", "")[:16]
        self._http = httpx.AsyncClient(timeout=timeout)

    @property
    def base_url(self) -> str:
        return f"https://{REGION_HOSTS.get(self.region, REGION_HOSTS['us'])}"

    async def async_close(self) -> None:
        await self._http.aclose()

    def _headers(self, req_uuid: str, ts_ms: int) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Gz-Pid": "glazero",
            "Gz-OsType": "android",
            "Gz-OsVer": "34",
            "Gz-OsLang": "fr-FR",
            "Gz-Lang": "fr",
            "Gz-Timezone": "+01:00",
            "Gz-TimezoneID": "Europe/Paris",
            "Gz-Brand": "HomeAssistant",
            "Gz-Model": "aosu-ha",
            "Gz-Imei": self.device_imei,
            "Gz-AppId": "com.glazero.android",
            "Gz-AppVer": "5.11.20",
            "Gz-BuildType": "release",
            "Gz-Channel": "google",
            "Gz-FontSize": "1.0",
            "Gz-NotifyPermission": "true",
            "Gz-Network": "WIFI",
            "Gz-Uid": self.uid,
            "Gz-Sid": self.sid,
            "Gz-Sign": compute_gz_sign(req_uuid, ts_ms),
        }

    async def _post_form(
        self,
        path: str,
        data: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> Any:
        req_uuid = str(uuid.uuid4())
        ts_ms = int(time.time() * 1000)
        encoded = urllib.parse.urlencode(data or {}, doseq=True).encode("utf-8")
        resp = await self._http.post(
            f"{self.base_url}{path}",
            params={"uuid": req_uuid, "t": str(ts_ms)},
            headers=self._headers(req_uuid, ts_ms),
            content=encoded,
        )
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code")
        if code not in (0, 200, "0", "200", None):
            msg = str(body.get("msg") or body.get("message") or "")
            if str(code) in ("401", "1001", "1002", "1003", "10001"):
                raise AosuAuthError(f"Auth error ({code}): {msg}")
            raise AosuApiError(f"API error ({code}): {msg}")
        return body.get("data", body)

    async def async_login(self, country_code: str = "33", country_abbr: str = "FR") -> None:
        data = await self._post_form(
            "/v1/user/login",
            data={
                "region": self.region,
                "countryCode": country_code,
                "countryAbbr": country_abbr,
                "type": "1",
                "email": self.email,
                "password": encrypt_password(self.password),
                "pwType": "2",
            },
        )
        if not isinstance(data, dict) or not data.get("uid") or not data.get("sid"):
            raise AosuAuthError("Identifiants invalides ou réponse incomplète.")
        self.uid = str(data["uid"])
        self.sid = str(data["sid"])
        if data.get("region"):
            self.region = str(data["region"]).lower()

    async def async_get_devices(self) -> list[AosuCameraData]:
        if not self.sid:
            await self.async_login()
        data = await self._post_form("/v1/dev/getList")
        items = data if isinstance(data, list) else (data.get("list") or data.get("devices") or [])
        cameras: list[AosuCameraData] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
            support = item.get("support") if isinstance(item.get("support"), dict) else {}
            cover = item.get("coverInfo") if isinstance(item.get("coverInfo"), dict) else {}
            bat = extend.get("electricity")
            wifi = extend.get("wifi_signal")
            cameras.append(
                AosuCameraData(
                    sn=str(item.get("sn") or ""),
                    name=str(item.get("name") or item.get("title") or item.get("sn") or "").strip(),
                    model=str(item.get("model") or ""),
                    dev_type=int(item.get("devType") or 0),
                    svc_type=str(support.get("svcType") or ""),
                    sn_coop=str(item.get("snCoop") or ""),
                    online=bool(item.get("online")),
                    battery=int(bat) if isinstance(bat, (int, float)) else None,
                    wifi_signal=int(wifi) if isinstance(wifi, (int, float)) else None,
                    cover_image_url=str(cover["imageUrl"]) if cover.get("imageUrl") else None,
                    last_event_time=int(cover["eventTime"]) if isinstance(cover.get("eventTime"), (int, float)) else None,
                )
            )
        return cameras

    async def async_get_card_events(
        self, sns: list[str], count: int = 20, hours_back: int = 48
    ) -> list[dict[str, Any]]:
        """Fetch SD-card event history via /v1/event/getCardList."""
        if not sns:
            return []
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - hours_back * 3600 * 1000
        form_items: list[tuple[str, Any]] = [
            ("eventTimeGt", str(start_ms)),
            ("eventTimeLt", str(now_ms)),
            ("count", str(count)),
            ("order", "desc"),
        ]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = await self._post_form("/v1/event/getCardList", data=form_items)
        if isinstance(data, dict):
            return list(data.get("list") or [])
        return []

    async def async_wakeup_device(self, sn: str) -> Any:
        """Wake a sleeping battery/solar camera via /v1/dev/wakeup."""
        return await self._post_form("/v1/dev/wakeup", data={"sn": sn})

    async def async_get_image_events(self, sns: list[str], count: int = 10) -> list[dict[str, Any]]:
        if not sns:
            return []
        form_items: list[tuple[str, Any]] = [("count", str(count))]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = await self._post_form("/v1/event/getImageList", data=form_items)
        if isinstance(data, dict):
            return list(data.get("list") or [])
        return []

    async def async_download_image(self, url: str) -> bytes:
        resp = await self._http.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    async def async_recognize_face_compreface(
        self,
        image_bytes: bytes,
        compreface_url: str,
        api_key: str,
        threshold: float = 0.75,
    ) -> tuple[str | None, float | None]:
        """Call a local CompreFace instance to identify a face in the snapshot."""
        url = f"{compreface_url.rstrip('/')}/api/v1/recognition/recognize"
        resp = await self._http.post(
            url,
            headers={"x-api-key": api_key},
            files={"file": ("snapshot.jpg", image_bytes, "image/jpeg")},
            timeout=10.0,
        )
        if resp.status_code == 400:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result") or []
        if not results:
            return None, None
        subjects = results[0].get("subjects") or []
        if subjects and float(subjects[0].get("similarity", 0.0)) >= threshold:
            return str(subjects[0]["subject"]), round(float(subjects[0]["similarity"]), 4)
        score = round(float(subjects[0].get("similarity", 0.0)), 4) if subjects else 0.0
        return "Inconnu", score
