"""Generate a PBKDF2 password hash for the `user.password` column.

Usage:
    uv run python scripts/hash_password.py
    uv run python scripts/hash_password.py --password admin
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
from getpass import getpass


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def hash_password(password: str, iterations: int = 260_000) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${_b64url_encode(digest)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PetroChat password hash")
    parser.add_argument("--password", default="", help="Plain password. Omit to input securely.")
    args = parser.parse_args()

    password = args.password or getpass("Password: ")
    print(hash_password(password))


if __name__ == "__main__":
    main()
