"""Loopback and per-session authentication for the local API."""

import os
import secrets

from fastapi import HTTPException, Request


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "testclient"}


def session_token() -> str:
    """Return the configured token or refuse to start an insecure service."""
    expected = os.environ.get("BIOSTAT_SESSION_TOKEN")
    if not expected:
        raise RuntimeError("BIOSTAT_SESSION_TOKEN must be set to a non-empty value")
    return expected


def require_loopback(request: Request) -> None:
    """Reject requests that do not originate from the local machine."""
    host = request.client.host if request.client else ""
    if host not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="loopback_only")


def require_session(request: Request) -> None:
    """Require both a loopback client and the current session bearer token."""
    require_loopback(request)
    expected = session_token()
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid_session")
    supplied = authorization[len("Bearer ") :]
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_session")
