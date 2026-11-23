"""Data models for Aosu Cloud REST, AWS IoT MQTT, and Agora RTC/RTM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AosuSession:
    uid: str
    sid: str
    region: str = "eu"
    email: str = ""
    country_code: str = "33"
    country_abbr: str = "FR"
    tuya_uid: str | None = None
    tuya_username: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "sid": self.sid,
            "region": self.region,
            "email": self.email,
            "country_code": self.country_code,
            "country_abbr": self.country_abbr,
            "tuya_uid": self.tuya_uid,
            "tuya_username": self.tuya_username,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AosuSession:
        return cls(
            uid=str(data.get("uid", "")),
            sid=str(data.get("sid", "")),
            region=str(data.get("region", "eu")).lower(),
            email=str(data.get("email", "")),
            country_code=str(data.get("country_code", data.get("countryCode", "33"))),
            country_abbr=str(data.get("country_abbr", data.get("countryAbbr", "FR"))),
            tuya_uid=data.get("tuya_uid") or data.get("tuyaUid"),
            tuya_username=data.get("tuya_username") or data.get("tuyaUserName"),
        )


@dataclass
class AosuDevice:
    sn: str
    title: str
    model: str = ""
    dev_type: str = ""
    svc_type: str = ""
    sn_coop: str = ""
    online: bool | None = None
    battery: int | None = None
    wifi_signal: int | None = None
    cover_image_url: str | None = None
    last_event_time: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> AosuDevice:
        sn = str(item.get("sn") or item.get("deviceId") or item.get("uuid") or "")
        title = str(item.get("title") or item.get("name") or item.get("deviceName") or sn).strip()
        model = str(item.get("model") or item.get("modelCode") or item.get("pid") or "")
        dev_type = str(item.get("devType") or item.get("type") or "")
        support = item.get("support") if isinstance(item.get("support"), dict) else {}
        svc_type = str(support.get("svcType") or "")
        sn_coop = str(item.get("snCoop") or "")
        online = item.get("online")
        if online is None and "status" in item:
            online = bool(item["status"])
        extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
        battery = item.get("battery") or item.get("electricity") or extend.get("electricity")
        wifi_signal = extend.get("wifi_signal")
        cover = item.get("coverInfo") if isinstance(item.get("coverInfo"), dict) else {}
        cover_image_url = cover.get("imageUrl")
        last_event_time = cover.get("eventTime")
        return cls(
            sn=sn,
            title=title,
            model=model,
            dev_type=dev_type,
            svc_type=svc_type,
            sn_coop=sn_coop,
            online=bool(online) if online is not None else None,
            battery=int(battery) if isinstance(battery, (int, float)) else None,
            wifi_signal=int(wifi_signal) if isinstance(wifi_signal, (int, float)) else None,
            cover_image_url=str(cover_image_url) if cover_image_url else None,
            last_event_time=int(last_event_time) if isinstance(last_event_time, (int, float)) else None,
            raw=item,
        )


@dataclass
class MqttDeviceTopic:
    device_id: str
    topic_prefix: str


@dataclass
class MqttAuthInfo:
    endpoint: str
    region: str
    client_id: str
    ak: str
    sk: str
    token: str
    expiration: int | None = None
    server_time: int | None = None
    devices: list[MqttDeviceTopic] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict[str, Any], server_time: int | None = None) -> MqttAuthInfo:
        devices = [
            MqttDeviceTopic(
                device_id=str(d.get("deviceId", "")),
                topic_prefix=str(d.get("topicPrefix", "")),
            )
            for d in (item.get("mqttList") or [])
        ]
        return cls(
            endpoint=str(item.get("endpoint", "")),
            region=str(item.get("region", "")),
            client_id=str(item.get("clientId", "")),
            ak=str(item.get("ak", "")),
            sk=str(item.get("sk", "")),
            token=str(item.get("token", "")),
            expiration=item.get("expiration"),
            server_time=server_time,
            devices=devices,
            raw=item,
        )


@dataclass
class AgoraChannelInfo:
    device_id: str
    dev_rtc_channel: str
    dev_rtm_uid: str
    rtc_token: str
    enc_key: str = ""
    enc_kdf_salt: str = ""


@dataclass
class AgoraPlayInfo:
    app_id: str
    rtm_token: str
    expiration: int | None = None
    server_time: int | None = None
    channels: list[AgoraChannelInfo] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AgoraPlayInfo:
        channels = [
            AgoraChannelInfo(
                device_id=str(c.get("deviceId") or c.get("sn") or ""),
                dev_rtc_channel=str(c.get("devRtcChannel") or c.get("channel") or ""),
                dev_rtm_uid=str(c.get("devRtmUid") or c.get("devChannelIdRtm") or ""),
                rtc_token=str(c.get("token") or ""),
                enc_key=str(c.get("encKey") or c.get("devEncKey") or ""),
                enc_kdf_salt=str(c.get("encKdfSalt") or c.get("devEncKdfSalt") or ""),
            )
            for c in (data.get("channelList") or [])
        ]
        return cls(
            app_id=str(data.get("appId") or data.get("appid") or ""),
            rtm_token=str(data.get("token") or data.get("tokenRtm") or ""),
            expiration=data.get("expiration") or data.get("expireTimeRtm"),
            server_time=data.get("serverTime"),
            channels=channels,
            raw=data,
        )


@dataclass
class AosuEvent:
    event_id: str
    sn: str
    event_time: int | None
    event_type: str
    image_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> AosuEvent:
        return cls(
            event_id=str(item.get("eid") or item.get("eventId") or item.get("id") or ""),
            sn=str(item.get("sn") or item.get("deviceId") or ""),
            event_time=item.get("eventTime") or item.get("timestamp"),
            event_type=str(item.get("uniformType") or item.get("eventType") or item.get("type") or ""),
            image_url=item.get("imageUrl") or item.get("picUrl") or item.get("thumbnail"),
            raw=item,
        )
