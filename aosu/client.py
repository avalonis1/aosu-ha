"""Cloud REST API client for Aosu (Glazero) cameras."""

from __future__ import annotations

import json
import random
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import httpx

from .crypto import compute_gz_sign, encrypt_password
from .models import (
    AgoraPlayInfo,
    AosuDevice,
    AosuEvent,
    AosuSession,
    MqttAuthInfo,
)

REGION_HOSTS: dict[str, str] = {
    "eu": "api-eu.aosulife.com",
    "us": "api.aosulife.com",
    "ap": "api-ap.aosulife.com",
    "cn": "api-cn.aosulife.com",
}


class AosuApiError(RuntimeError):
    """Raised when the Aosu Cloud API returns a non-success response."""

    def __init__(self, code: Any, message: str, payload: Any = None) -> None:
        super().__init__(f"Aosu API error (code={code}): {message}")
        self.code = code
        self.api_message = message
        self.payload = payload


class AosuClient:
    """Synchronous HTTP client for Aosu (Glazero) Cloud REST endpoints."""

    def __init__(
        self,
        region: str = "eu",
        session: AosuSession | None = None,
        device_imei: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.region = (session.region if session else region).lower()
        self.session = session
        self.device_imei = device_imei or str(uuid.uuid4()).replace("-", "")[:16]
        self._http = httpx.Client(timeout=timeout)

    @property
    def base_url(self) -> str:
        host = REGION_HOSTS.get(self.region, REGION_HOSTS["us"])
        return f"https://{host}"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AosuClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _build_headers(self, request_uuid: str, timestamp_ms: int) -> dict[str, str]:
        headers = {
            "Gz-Pid": "glazero",
            "Gz-OsType": "android",
            "Gz-OsVer": "34",
            "Gz-OsLang": "fr-FR",
            "Gz-Lang": "fr",
            "Gz-Timezone": "+01:00",
            "Gz-TimezoneID": "Europe/Paris",
            "Gz-Brand": "HomeAssistant",
            "Gz-Model": "aosu-ha-bridge",
            "Gz-Imei": self.device_imei,
            "Gz-AppId": "com.glazero.android",
            "Gz-AppVer": "5.11.20",
            "Gz-BuildType": "release",
            "Gz-Channel": "google",
            "Gz-FontSize": "1.0",
            "Gz-NotifyPermission": "true",
            "Gz-Network": "WIFI",
            "Gz-Uid": self.session.uid if self.session else "",
            "Gz-Sid": self.session.sid if self.session else "",
            "Gz-Sign": compute_gz_sign(request_uuid, timestamp_ms),
        }
        return headers

    def _post_form(
        self,
        path: str,
        data: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> Any:
        req_uuid = str(uuid.uuid4())
        ts_ms = int(time.time() * 1000)
        url = f"{self.base_url}{path}"
        headers = self._build_headers(req_uuid, ts_ms)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        encoded_body = urllib.parse.urlencode(data or {}, doseq=True)
        resp = self._http.post(
            url,
            params={"uuid": req_uuid, "t": str(ts_ms)},
            headers=headers,
            content=encoded_body.encode("utf-8"),
        )
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code")
        if code not in (0, 200, "0", "200", None):
            raise AosuApiError(code, str(body.get("msg") or body.get("message") or ""), body)
        return body.get("data", body)

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        req_uuid = str(uuid.uuid4())
        ts_ms = int(time.time() * 1000)
        url = f"{self.base_url}{path}"
        headers = self._build_headers(req_uuid, ts_ms)
        headers["Content-Type"] = "application/json"
        resp = self._http.post(
            url,
            params={"uuid": req_uuid, "t": str(ts_ms)},
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code")
        if code not in (0, 200, "0", "200", None):
            raise AosuApiError(code, str(body.get("msg") or body.get("message") or ""), body)
        return body.get("data", body)

    def login(
        self,
        email: str,
        password: str,
        region: str | None = None,
        country_code: str = "33",
        country_abbr: str = "FR",
    ) -> AosuSession:
        """Authenticate against /v1/user/login and store the returned session."""
        target_region = (region or self.region).lower()
        self.region = target_region
        enc_pw = encrypt_password(password)
        data = self._post_form(
            "/v1/user/login",
            data={
                "region": target_region,
                "countryCode": country_code,
                "countryAbbr": country_abbr,
                "type": "1",
                "email": email.strip().lower(),
                "password": enc_pw,
                "pwType": "2",
            },
        )
        session = AosuSession.from_dict(data if isinstance(data, dict) else {})
        if not session.uid or not session.sid:
            raise AosuApiError("auth", "Identifiants invalides (uid/sid vide retourné par Aosu)", data)
        if not session.region:
            session.region = target_region
        self.region = session.region
        self.session = session
        return session

    def get_devices(self) -> list[AosuDevice]:
        """Fetch all bound cameras and HomeBase units via /v1/dev/getList."""
        data = self._post_form("/v1/dev/getList")
        if isinstance(data, dict):
            items = data.get("list") or data.get("devices") or data.get("devList") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return [AosuDevice.from_api(item) for item in items if isinstance(item, dict)]

    def get_dp_values(self, sns: list[str]) -> Any:
        """Fetch current DP (telemetry/settings) values via /v1/dp/getValues."""
        form_items = [("sn[]", sn) for sn in sns]
        return self._post_form("/v1/dp/getValues", data=form_items)

    def wakeup_device(self, sn: str) -> Any:
        """Wake a sleeping battery/solar camera via /v1/dev/wakeup."""
        return self._post_form("/v1/dev/wakeup", data={"sn": sn})

    def get_mqtt_auth(self, sns: list[str]) -> list[MqttAuthInfo]:
        """Request temporary AWS IoT STS credentials & topic prefixes via /v1/sts/getMultiMqttInfo."""
        form_items: list[tuple[str, Any]] = [("type", "aws")]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = self._post_form("/v1/sts/getMultiMqttInfo", data=form_items)
        server_time = data.get("serverTime") if isinstance(data, dict) else None
        mqtt_list = (data.get("mqttInfoList") or []) if isinstance(data, dict) else []
        return [MqttAuthInfo.from_api(item, server_time=server_time) for item in mqtt_list]

    def get_play_info(
        self,
        sns: list[str],
        rtm_id: str | None = None,
        rtc_id: int | None = None,
        refresh: bool = True,
    ) -> AgoraPlayInfo:
        """Request Agora RTC/RTM tokens & AES-128-GCM2 encryption params via /v1/sts/getPlayInfo."""
        uid_base = self.session.uid if self.session and self.session.uid else "ha"
        chosen_rtm_id = rtm_id or f"{uid_base}_{uuid.uuid4().hex[:8]}"
        chosen_rtc_id = rtc_id if rtc_id is not None else random.randint(100000, 99999999)
        form_items: list[tuple[str, Any]] = [
            ("type", "agora"),
            ("rtmId", chosen_rtm_id),
            ("rtcId", str(chosen_rtc_id)),
            ("refresh", "true" if refresh else "false"),
        ]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = self._post_form("/v1/sts/getPlayInfo", data=form_items)
        return AgoraPlayInfo.from_api(data)

    def get_image_events(
        self,
        sns: list[str],
        count: int = 10,
    ) -> list[AosuEvent]:
        """Fetch recent motion/person/doorbell snapshot events via /v1/event/getImageList.

        Works without a paid cloud storage subscription for both Tuya and Glazero cameras.
        """
        form_items: list[tuple[str, Any]] = [("count", str(count))]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = self._post_form("/v1/event/getImageList", data=form_items)
        if isinstance(data, dict):
            items = data.get("list") or data.get("events") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return [AosuEvent.from_api(item) for item in items if isinstance(item, dict)]

    def download_image(self, image_url: str) -> bytes:
        """Download a snapshot JPEG from an event or coverInfo imageUrl (follows S3 redirect)."""
        resp = self._http.get(image_url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    def get_recent_events(
        self,
        sns: list[str],
        count: int = 10,
        hours_back: int = 24,
    ) -> list[AosuEvent]:
        """Fetch recent motion/human/doorbell events via /v1/event/getList."""
        now_s = int(time.time())
        start_s = now_s - hours_back * 3600
        form_items: list[tuple[str, Any]] = [
            ("eventTimeGt", str(start_s)),
            ("eventTimeLt", str(now_s)),
            ("count", str(count)),
            ("order", "desc"),
        ]
        form_items.extend(("sn[]", sn) for sn in sns)
        data = self._post_form("/v1/event/getList", data=form_items)
        if isinstance(data, dict):
            items = data.get("list") or data.get("events") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return [AosuEvent.from_api(item) for item in items if isinstance(item, dict)]

    def save_session(self, path: str | Path) -> None:
        if not self.session:
            raise ValueError("No active session to save")
        Path(path).write_text(
            json.dumps(self.session.to_dict(), indent=2), encoding="utf-8"
        )

    @classmethod
    def from_session_file(cls, path: str | Path) -> AosuClient:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        session = AosuSession.from_dict(raw)
        return cls(region=session.region, session=session)
