"""AWS IoT Core MQTT-over-WebSocket (SigV4) listener for Aosu real-time events."""

from __future__ import annotations

import json
import ssl
from typing import Callable

from .crypto import build_aws_iot_sigv4_ws_url
from .models import MqttAuthInfo

MessageCallback = Callable[[str, dict | str], None]


class AosuMqttListener:
    """Subscribes to Aosu AWS IoT Core device topics using temporary STS credentials."""

    def __init__(
        self,
        auth: MqttAuthInfo,
        on_message: MessageCallback,
        subscribe_wildcards: bool = True,
    ) -> None:
        self.auth = auth
        self.on_message = on_message
        self.subscribe_wildcards = subscribe_wildcards
        self._client = None

    def _topics(self) -> list[str]:
        topics: list[str] = []
        for dev in self.auth.devices:
            prefix = dev.topic_prefix.rstrip("/")
            if not prefix:
                continue
            if self.subscribe_wildcards:
                topics.append(f"{prefix}/#")
            else:
                topics.append(prefix)
        return topics

    def run_forever(self) -> None:
        import paho.mqtt.client as mqtt

        host = self.auth.endpoint.replace("https://", "").replace("wss://", "").split("/")[0]
        ws_path, _ = build_aws_iot_sigv4_ws_url(
            endpoint=host,
            region=self.auth.region,
            access_key=self.auth.ak,
            secret_key=self.auth.sk,
            session_token=self.auth.token,
        )

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.auth.client_id,
            transport="websockets",
        )
        client.ws_set_options(path=ws_path, headers={"Host": host})
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        def _on_connect(c, userdata, flags, reason_code, properties):
            print(f"[MQTT] Connected to {host} (reason={reason_code})")
            for topic in self._topics():
                print(f"[MQTT] Subscribing to: {topic}")
                c.subscribe(topic, qos=0)

        def _on_message(c, userdata, msg):
            raw_text = msg.payload.decode("utf-8", errors="replace")
            try:
                parsed: dict | str = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = raw_text
            self.on_message(msg.topic, parsed)

        client.on_connect = _on_connect
        client.on_message = _on_message
        self._client = client

        client.connect(host, 443, keepalive=60)
        client.loop_forever()
