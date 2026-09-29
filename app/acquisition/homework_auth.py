"""Minimal login helper for the homework administration system.

Credentials are passed by the caller; this module never prompts for or stores
the password. A successful login stores only the session ID and account name.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE_URL = "http://124.221.200.10"
TIMEOUT = 30
DEFAULT_SESSION_FILE = Path(__file__).resolve().with_name("sessionid.txt")
_SECRET = "44sk7qzkveFEVDZd1XHGDArX6CYrAckp593mPW_I0HI"


def encrypt_password(password: str) -> str:
    """Encode the raw password using the login endpoint's AES-256-CBC format."""
    digest = hashlib.sha256(_SECRET.encode("utf-8")).digest()
    iv = hashlib.sha256(_SECRET.encode("utf-8")).hexdigest()[:32]
    cipher = AES.new(digest, AES.MODE_CBC, bytes.fromhex(iv))
    encrypted = cipher.encrypt(pad(password.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("ascii")


def _headers(csrf_token: str = "") -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": BASE_URL + "/",
        "X-CSRFToken": csrf_token,
    }


def fetch_csrf_token(timeout: int = TIMEOUT) -> str:
    """Try the optional CSRF endpoint; return empty when unavailable."""
    try:
        response = requests.get(BASE_URL + "/api/csrf", timeout=timeout)
        try:
            response.raise_for_status()
            return response.cookies.get("csrftoken", "")
        finally:
            response.close()
    except requests.RequestException:
        return ""


def _atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(value)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def login(
    admin_id: str,
    password: str,
    csrf_token: str = "",
    session_file: str | Path = DEFAULT_SESSION_FILE,
    timeout: int = TIMEOUT,
) -> str:
    """Log in and return the sessionid; persist sessionid and its account label.

    First uses the supplied/saved CSRF value. If that attempt fails, it tries
    once more with a freshly fetched CSRF token. The password is never written.
    """
    if not admin_id.strip() or not password:
        raise ValueError("admin_id and password are required")
    session_path = Path(session_file)
    csrf = csrf_token.strip()
    last_error: Exception | None = None

    for attempt in range(2):
        if attempt:
            csrf = fetch_csrf_token(timeout)
            if not csrf:
                raise RuntimeError("Login failed and no fresh CSRF token was returned") from last_error
        response = None
        try:
            response = requests.post(
                BASE_URL + "/api/auth/login",
                headers=_headers(csrf),
                cookies={"csrftoken": csrf} if csrf else None,
                json={
                    "role": "admin",
                    "admin_id": admin_id.strip(),
                    "password": encrypt_password(password),
                },
                timeout=timeout,
            )
            response.raise_for_status()
            sessionid = response.cookies.get("sessionid")
            if not sessionid:
                raise RuntimeError("Login response did not set a sessionid cookie")
            _atomic_write(session_path, sessionid)
            _atomic_write(session_path.with_name("session_account.txt"), admin_id.strip())
            return sessionid
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt:
                raise
        finally:
            if response is not None:
                response.close()
    raise RuntimeError("Login failed") from last_error


def auth_kwargs(sessionid: str, csrf_token: str = "") -> dict[str, Any]:
    """Return requests kwargs for authenticated admin API calls."""
    return {
        "headers": _headers(csrf_token),
        "cookies": {"sessionid": sessionid, **({"csrftoken": csrf_token} if csrf_token else {})},
    }


def load_sessionid(
    admin_id: str,
    password: str,
    csrf_token: str = "",
    session_file: str | Path = DEFAULT_SESSION_FILE,
) -> str:
    """Reuse a locally saved session for the same account, otherwise log in."""
    session_path = Path(session_file)
    account_path = session_path.with_name("session_account.txt")
    try:
        saved_account = account_path.read_text(encoding="utf-8").strip()
        saved_session = session_path.read_text(encoding="utf-8").strip()
    except OSError:
        saved_account, saved_session = "", ""
    if saved_account == admin_id.strip() and saved_session:
        return saved_session
    return login(admin_id, password, csrf_token, session_path)


if __name__ == "__main__":
    # Example only: set credentials in the environment before running.
    username = os.environ.get("HOMEWORK_ADMIN_ID", "")
    raw_password = os.environ.get("HOMEWORK_ADMIN_PASSWORD", "")
    token = os.environ.get("HOMEWORK_CSRF_TOKEN", "")
    result = login(username, raw_password, token)
    print(f"Login succeeded; session saved to {DEFAULT_SESSION_FILE}")
