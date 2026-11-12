"""Random identifiers and one-way hashes.

* Board IDs are public (they appear in links).
* Invite codes (~50 bits) and owner keys (~99 bits) are secrets. Only their SHA-256
  hashes are stored, so nobody — not even whoever runs the database — can read a code
  back out of it, and the app can never show "which code voted".
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

# No 0/O, 1/I/L — easy to read aloud and type on a phone.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

BOARD_ID_LEN = 8
CODE_LEN = 10
OWNER_KEY_LEN = 20

_STRIP = re.compile(r"[^0-9A-Z]")


def _rand(n: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def _group(s: str, size: int = 5) -> str:
    return "-".join(s[i : i + size] for i in range(0, len(s), size))


def new_board_id() -> str:
    return _rand(BOARD_ID_LEN)


def new_code() -> str:
    return _group(_rand(CODE_LEN))


def new_owner_key() -> str:
    return _group(_rand(OWNER_KEY_LEN))


def normalize(token: str | None) -> str:
    """Uppercase and drop dashes/spaces so 'abcde-fghjk ' == 'ABCDEFGHJK'."""
    if not token:
        return ""
    return _STRIP.sub("", str(token).upper())[:64]


def normalize_board_id(board_id: str | None) -> str:
    bid = normalize(board_id)
    return bid if len(bid) == BOARD_ID_LEN and set(bid) <= set(ALPHABET) else ""


def looks_like_code(token: str | None) -> bool:
    t = normalize(token)
    return len(t) == CODE_LEN and set(t) <= set(ALPHABET)


def hash_code(board_id: str, code: str) -> str:
    return hashlib.sha256(f"mw:code:v1:{board_id}:{normalize(code)}".encode()).hexdigest()


def hash_owner_key(board_id: str, key: str) -> str:
    return hashlib.sha256(f"mw:owner:v1:{board_id}:{normalize(key)}".encode()).hexdigest()


def check_owner_key(board_id: str, key: str, stored_hash: str) -> bool:
    if not key or not stored_hash:
        return False
    return hmac.compare_digest(hash_owner_key(board_id, key), stored_hash)
