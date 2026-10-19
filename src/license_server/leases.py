import base64
import hashlib
import hmac
import json
import math
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DOMAIN = b"LIVE-STUDIO-LEASE-V1."


def encode(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode(value):
    return base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )


def device_hash(device):
    return hashlib.sha256(device.encode()).hexdigest()


class LicenseSigner:
    def __init__(self, private_bytes):
        self.key = Ed25519PrivateKey.from_private_bytes(private_bytes)

    @property
    def public_key(self):
        return encode(self.key.public_key().public_bytes_raw())

    def issue(self, license_row, now):
        expires = license_row["expires_at"]
        claims = dict(
            v=1,
            aud="tiktok-live-recorder",
            license_id=license_row["id"],
            device_hash=license_row["device_hash"],
            binding_version=license_row["binding_version"],
            issued_at=now,
            expires_at=expires,
            refresh_after=min(now + 900, expires),
            offline_until=min(now + 86400, expires),
        )
        payload = encode(
            json.dumps(
                claims, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        )
        return "v1." + payload + "." + encode(self.key.sign(DOMAIN + payload.encode()))


def verify_lease(token, public_key, device_id, now=None):
    """Verify a cached lease using a PINNED public key, never a network-supplied replacement."""
    now = time.time() if now is None else now
    try:
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("Invalid current time")
        if not isinstance(device_id, str) or not 32 <= len(device_id) <= 256:
            raise ValueError("Invalid device identity")
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError("Invalid lease size")
        version, payload, signature = token.split(".")
        if version != "v1":
            raise ValueError("Invalid lease version")
        Ed25519PublicKey.from_public_bytes(decode(public_key)).verify(
            decode(signature), DOMAIN + payload.encode()
        )
        claims = json.loads(decode(payload))
        if claims["v"] != 1 or claims["aud"] != "tiktok-live-recorder":
            raise ValueError("Invalid audience")
        if not hmac.compare_digest(claims["device_hash"], device_hash(device_id)):
            raise ValueError("Wrong device")
        times = [
            claims[name]
            for name in ("issued_at", "refresh_after", "offline_until", "expires_at")
        ]
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in times
        ):
            raise ValueError("Invalid time")
        if (
            not times[0] <= times[1] <= times[2] <= times[3]
            or times[2] > times[0] + 86400
        ):
            raise ValueError("Invalid lease bounds")
        if now < times[0] - 120 or now >= min(times[2], times[3]):
            raise ValueError("Lease expired or clock moved backwards")
        return claims
    except (InvalidSignature, ValueError, KeyError, TypeError, UnicodeError) as ex:
        raise ValueError(
            "Giấy phép không hợp lệ, sai thiết bị hoặc đã hết hạn."
        ) from ex
