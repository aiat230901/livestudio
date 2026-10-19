"""Pinned-server licensing; only cached signed leases allow temporary offline use."""

import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import requests

from license_server.leases import decode, verify_lease


class LicenseDenied(Exception):
    pass


class ServerUnavailable(Exception):
    pass


def device_identity():
    if sys.platform != "win32":
        raise LicenseDenied("Bản kích hoạt này hỗ trợ Windows.")
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Cryptography",
        0,
        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
    ) as key:
        guid = winreg.QueryValueEx(key, "MachineGuid")[0]
    if not isinstance(guid, str) or len(guid) < 16:
        raise LicenseDenied("Không đọc được mã thiết bị Windows.")
    return hashlib.sha256(("LiveStudio-device-v1:" + guid).encode()).hexdigest()


def protect_data(data, decrypt=False):
    """DPAPI encrypts for this Windows user and machine; never write plain tokens."""
    if sys.platform != "win32":
        raise OSError("Cần Windows DPAPI để lưu giấy phép.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(
        ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def load_config(path=None):
    path = (
        Path(path)
        if path
        else (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2]
        )
        / "license-client.json"
    )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        url = urlsplit(config["server_url"])
        valid_transport = url.scheme == "https" or (
            url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
        )
        if (
            config["version"] != 1
            or not valid_transport
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or len(decode(config["public_key"])) != 32
        ):
            raise ValueError("Invalid server configuration")
        config["server_url"] = config["server_url"].rstrip("/")
        return config
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise LicenseDenied(
            "Thiếu hoặc sai license-client.json. Mở lại máy chủ bằng Mo_Admin.bat để tạo cấu hình bản thử; bản gửi khách cần cấu hình HTTPS của bạn."
        ) from ex


class LicenseClient:
    def __init__(
        self,
        directory,
        config,
        *,
        device=None,
        wall=None,
        monotonic=None,
        seal=None,
        request=None,
    ):
        self.path = Path(directory) / "license.dat"
        self.config = config
        self.device = device or device_identity()
        self.wall = wall or time.time
        self.monotonic = monotonic or time.monotonic
        self.seal = seal or protect_data
        self.request = request or self._request
        self.state = {}
        self.claims = None
        self.message = "Chưa kích hoạt giấy phép."
        self.mode = "denied"
        self.next_attempt = 0
        self.last_save = self.monotonic()
        self.anchor_mono = self.monotonic()
        self.anchor_wall = self.wall()
        self.anchor_utc = 0
        self.clock_suspect = False
        self.fingerprint = hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest()
        try:
            state = json.loads(self.seal(self.path.read_bytes(), decrypt=True))
            if not isinstance(state, dict):
                raise ValueError("Invalid cached state")
            if state.get("config") == self.fingerprint:
                for name in ("wall", "utc"):
                    if type(state.get(name)) not in (int, float) or not math.isfinite(
                        state[name]
                    ):
                        raise ValueError("Invalid cached time")
                if not isinstance(
                    state.get("activation_token", ""), str
                ) or not isinstance(state.get("license_id", ""), str):
                    raise ValueError("Invalid cached identity")
                self.state = state
                self.clock_suspect = self.wall() < state["wall"] - 120
                self.anchor_utc = state["utc"] + max(0, self.wall() - state["wall"])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _request(self, action, payload):
        try:
            response = requests.post(
                self.config["server_url"] + "/api/license/" + action,
                json=payload,
                timeout=(3, 6),
                allow_redirects=False,
            )
        except requests.RequestException as ex:
            raise ServerUnavailable("Không kết nối được máy chủ giấy phép.") from ex
        if response.status_code >= 500 or response.status_code == 429:
            raise ServerUnavailable("Máy chủ giấy phép tạm thời chưa sẵn sàng.")
        try:
            data = response.json()
        except ValueError as ex:
            raise LicenseDenied("Phản hồi máy chủ giấy phép không hợp lệ.") from ex
        if response.status_code != 200:
            messages = {
                "blocked": "Key đã bị khóa. Liên hệ người cung cấp.",
                "archived": "Key đã được lưu trữ và ngừng sử dụng.",
                "expired": "Key đã hết hạn. Liên hệ người cung cấp để gia hạn.",
                "device_mismatch": "Key đang liên kết với một máy tính khác.",
                "activation_revoked": "Liên kết thiết bị đã thay đổi. Hãy kích hoạt lại.",
                "invalid_key": "Key không hợp lệ.",
                "not_found": "Key không còn tồn tại.",
            }
            error = data.get("error", {}) if isinstance(data, dict) else {}
            raise LicenseDenied(
                messages.get(error.get("code"), "Máy chủ từ chối giấy phép.")
            )
        if not isinstance(data, dict):
            raise LicenseDenied("Phản hồi máy chủ giấy phép không hợp lệ.")
        return data

    def now(self):
        return self.anchor_utc + max(
            0, self.monotonic() - self.anchor_mono, self.wall() - self.anchor_wall
        )

    def _save(self):
        self.state.update(config=self.fingerprint, wall=self.wall(), utc=self.now())
        encrypted = self.seal(json.dumps(self.state, allow_nan=False).encode())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        os.replace(temporary, self.path)
        self.last_save = self.monotonic()

    def _accept(self, result, activating=False):
        try:
            # Signature is checked before trusting even the server's time.
            token = result["lease"]
            if not isinstance(token, str) or len(token) > 4096:
                raise ValueError("Invalid lease size")
            payload = json.loads(decode(token.split(".")[1]))
            claims = verify_lease(
                token, self.config["public_key"], self.device, now=payload["issued_at"]
            )
            identity = result["license"]
            if (
                claims["license_id"] != identity["id"]
                or claims["binding_version"] != identity["binding_version"]
            ):
                raise ValueError("Mismatched license")
            if not activating and claims["license_id"] != self.state["license_id"]:
                raise ValueError("Wrong license")
            activation_token = (
                result["activation_token"]
                if activating
                else self.state["activation_token"]
            )
            if (
                not isinstance(activation_token, str)
                or not 32 <= len(activation_token) <= 128
            ):
                raise ValueError("Invalid activation token")
        except (ValueError, KeyError, TypeError, IndexError) as ex:
            raise LicenseDenied("Chữ ký hoặc nội dung giấy phép không hợp lệ.") from ex
        self.anchor_utc, self.anchor_wall, self.anchor_mono = (
            claims["issued_at"],
            self.wall(),
            self.monotonic(),
        )
        self.clock_suspect = False
        self.state = dict(
            license_id=claims["license_id"],
            activation_token=activation_token,
            lease=token,
        )
        self.claims = claims
        self.mode = "online"
        self.message = "Giấy phép đang hoạt động."
        self._save()
        self.next_attempt = self.monotonic() + min(
            900, claims["refresh_after"] - claims["issued_at"]
        )

    def _deny(self, message):
        self.mode, self.message, self.claims = "denied", message, None
        self.state.pop("lease", None)
        self.next_attempt = self.monotonic() + 60
        self._save()

    def activate(self, key):
        try:
            result = self.request(
                "activate", dict(key=key.strip().upper(), device_id=self.device)
            )
            self._accept(result, activating=True)
        except (LicenseDenied, ServerUnavailable, OSError) as ex:
            self._deny(str(ex))
            return False
        return True

    def refresh(self):
        if not self.state.get("activation_token"):
            self.mode, self.message = (
                "denied",
                "Nhập key bạn nhận từ nhà cung cấp để kích hoạt trên máy này.",
            )
            self.next_attempt = self.monotonic() + 60
            return False
        try:
            self._accept(
                self.request(
                    "check",
                    dict(
                        license_id=self.state["license_id"],
                        activation_token=self.state["activation_token"],
                        device_id=self.device,
                    ),
                )
            )
        except ServerUnavailable:
            self.next_attempt = self.monotonic() + 60
            try:
                if self.clock_suspect:
                    raise ValueError("Clock rollback")
                self.claims = verify_lease(
                    self.state.get("lease"),
                    self.config["public_key"],
                    self.device,
                    now=self.now(),
                )
                self.mode, self.message = (
                    "offline",
                    "Mất kết nối máy chủ giấy phép · đang dùng thời gian offline còn lại.",
                )
            except ValueError:
                self._deny(
                    "Cần kết nối máy chủ để xác thực giấy phép. Thời gian offline đã hết hoặc đồng hồ máy bị thay đổi."
                )
        except (LicenseDenied, OSError) as ex:
            self._deny(str(ex))
        return self.allowed()

    def allowed(self):
        if self.mode == "denied" or not self.claims:
            return False
        if self.wall() < self.anchor_wall - 120:
            self.clock_suspect = True
            self.mode, self.message = (
                "denied",
                "Đồng hồ máy đã thay đổi. Cần xác thực lại với máy chủ.",
            )
            self.next_attempt = 0
            return False
        if self.now() >= min(self.claims["offline_until"], self.claims["expires_at"]):
            self.mode, self.message = (
                "denied",
                "Giấy phép đã hết hạn hoặc hết thời gian offline. Cần xác thực lại.",
            )
            return False
        return True

    def checkpoint(self):
        if self.allowed() and self.monotonic() - self.last_save >= 60:
            self._save()
