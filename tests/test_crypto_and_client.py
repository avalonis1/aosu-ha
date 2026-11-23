"""Unit tests for Aosu crypto, SigV4 signing, and API model parsing."""

import base64
import datetime
import unittest

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from aosu.crypto import (
    PASSWORD_AES_IV,
    PASSWORD_AES_KEY,
    build_aws_iot_sigv4_ws_url,
    compute_gz_sign,
    encrypt_password,
)
from aosu.models import AgoraPlayInfo, AosuDevice, MqttAuthInfo


class TestAosuCryptoAndModels(unittest.TestCase):
    def test_gz_sign_format(self) -> None:
        sign = compute_gz_sign("12345678-1234-1234-1234-1234567890ab", 1700000000000)
        self.assertEqual(len(sign), 32)
        self.assertEqual(sign, sign.lower())

    def test_encrypt_password_roundtrip(self) -> None:
        secret = "MyTestPassword!2026"
        encoded = encrypt_password(secret)
        raw = base64.b64decode(encoded)
        cipher = Cipher(algorithms.AES(PASSWORD_AES_KEY), modes.CBC(PASSWORD_AES_IV))
        decryptor = cipher.decryptor()
        padded = decryptor.update(raw) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
        self.assertEqual(plain, secret)

    def test_aws_iot_sigv4_url(self) -> None:
        fixed_dt = datetime.datetime(2026, 11, 23, 12, 0, 0, tzinfo=datetime.timezone.utc)
        ws_path, full_url = build_aws_iot_sigv4_ws_url(
            endpoint="example-ats.iot.eu-central-1.amazonaws.com",
            region="eu-central-1",
            access_key="ASIATESTKEY",
            secret_key="TESTSECRETKEY",
            session_token="TESTTOKEN+/=",
            now=fixed_dt,
        )
        self.assertTrue(ws_path.startswith("/mqtt?X-Amz-Algorithm=AWS4-HMAC-SHA256"))
        self.assertIn("X-Amz-Signature=", ws_path)
        self.assertIn("X-Amz-Security-Token=TESTTOKEN%2B%2F%3D", ws_path)
        self.assertTrue(full_url.startswith("wss://example-ats.iot.eu-central-1.amazonaws.com/mqtt?"))

    def test_models_parsing(self) -> None:
        dev = AosuDevice.from_api({"sn": "C9E123", "title": "Allée", "model": "C9E", "online": 1, "battery": 88})
        self.assertEqual(dev.sn, "C9E123")
        self.assertEqual(dev.title, "Allée")
        self.assertTrue(dev.online)
        self.assertEqual(dev.battery, 88)

        mqtt = MqttAuthInfo.from_api(
            {
                "endpoint": "abc.iot.eu-central-1.amazonaws.com",
                "region": "eu-central-1",
                "clientId": "client-1",
                "ak": "AK",
                "sk": "SK",
                "token": "TOK",
                "mqttList": [{"deviceId": "C9E123", "topicPrefix": "gz/dev/C9E123"}],
            },
            server_time=1700000000,
        )
        self.assertEqual(len(mqtt.devices), 1)
        self.assertEqual(mqtt.devices[0].topic_prefix, "gz/dev/C9E123")

        play = AgoraPlayInfo.from_api(
            {
                "appId": "agora-app-id",
                "token": "rtm-tok",
                "channelList": [
                    {
                        "deviceId": "C9E123",
                        "devRtcChannel": "ch-1",
                        "devRtmUid": "uid-1",
                        "token": "rtc-tok",
                        "encKey": "secretkey",
                        "encKdfSalt": "salt123",
                    }
                ],
            }
        )
        self.assertEqual(play.app_id, "agora-app-id")
        self.assertEqual(play.channels[0].dev_rtc_channel, "ch-1")


if __name__ == "__main__":
    unittest.main()
