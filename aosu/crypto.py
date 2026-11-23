"""Cryptographic helpers for Aosu (Glazero) Cloud REST and AWS IoT SigV4."""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import urllib.parse

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Observed in com.glazero.biz.base.http.interceptor.SignInterceptor
GZ_SIGN_SALT = "&sM&GGlUCSXjZqQNxmkdU^scUs**0R@C"

# Observed in libglazero-security.so (SecurityJni.nativeEncryptP)
PASSWORD_AES_KEY = b"PZR1ryiUhJloWoRd"
PASSWORD_AES_IV = b"PZR1ryiUhJloWoRd"


def compute_gz_sign(request_uuid: str, timestamp_ms: int | str) -> str:
    """Compute the Gz-Sign header value (lowercase MD5)."""
    payload = f"uuid:{request_uuid}:t:{timestamp_ms}:{GZ_SIGN_SALT}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest().lower()


def encrypt_password(password: str) -> str:
    """Encrypt a plaintext password using AES-128-CBC (PKCS#7) + Base64 (pwType=2)."""
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(PASSWORD_AES_KEY), modes.CBC(PASSWORD_AES_IV))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def build_aws_iot_sigv4_ws_url(
    endpoint: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str,
    now: datetime.datetime | None = None,
) -> tuple[str, str]:
    """Build a presigned AWS IoT Core MQTT-over-WebSocket path + full wss URL (SigV4).

    Returns (ws_path_with_query, full_wss_url).
    """
    dt = now or datetime.datetime.now(datetime.timezone.utc)
    amz_date = dt.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = dt.strftime("%Y%m%d")
    service = "iotdevicegateway"
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"

    host = endpoint.replace("https://", "").replace("wss://", "").split("/")[0]
    canonical_uri = "/mqtt"

    query_params = [
        ("X-Amz-Algorithm", algorithm),
        ("X-Amz-Credential", f"{access_key}/{credential_scope}"),
        ("X-Amz-Date", amz_date),
        ("X-Amz-SignedHeaders", "host"),
    ]
    canonical_querystring = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in query_params
    )
    canonical_headers = f"host:{host}\n"
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_request = (
        f"GET\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\nhost\n{payload_hash}"
    )

    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    k_date = _hmac_sha256(f"AWS4{secret_key}".encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    k_signing = _hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    signed_query = (
        f"{canonical_querystring}&X-Amz-Signature={signature}"
        f"&X-Amz-Security-Token={urllib.parse.quote(session_token, safe='')}"
    )
    ws_path = f"{canonical_uri}?{signed_query}"
    return ws_path, f"wss://{host}{ws_path}"
