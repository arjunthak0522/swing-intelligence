from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

AUDIENCE = "reentry-supabase"
PAYLOAD_PATH = Path("artifacts/reentry_strategy/supabase_payload.json")


def request_oidc_token() -> str:
    base = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not base or not bearer:
        raise RuntimeError("GitHub Actions OIDC environment is unavailable")
    separator = "&" if "?" in base else "?"
    url = f"{base}{separator}{urllib.parse.urlencode({'audience': AUDIENCE})}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    token = body.get("value")
    if not token:
        raise RuntimeError("GitHub OIDC response did not contain a token")
    return token


def sync() -> dict:
    ingest_url = os.environ.get("REENTRY_INGEST_URL")
    if not ingest_url:
        raise RuntimeError("REENTRY_INGEST_URL is required")
    if not PAYLOAD_PATH.exists():
        raise FileNotFoundError(str(PAYLOAD_PATH))
    token = request_oidc_token()
    payload = PAYLOAD_PATH.read_bytes()
    req = urllib.request.Request(
        ingest_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "re-entry-engine/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase ingest failed HTTP {exc.code}: {detail}") from exc


def main() -> None:
    print(json.dumps(sync(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
