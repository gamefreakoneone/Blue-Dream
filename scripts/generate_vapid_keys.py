"""Generate browser-compatible VAPID keys for Project Memoria.

By default the two environment lines are printed for manual use. Passing
``--write-env .env`` updates that untracked file without echoing either secret.
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def generate_keys() -> tuple[str, str]:
    vapid = Vapid()
    vapid.generate_keys()
    private_value = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public_value = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(private_value), _b64url(public_value)


def _update_env(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    output: list[str] = []
    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in pending:
            output.append(f"{key}={pending.pop(key)}")
        else:
            output.append(line)
    if pending and output and output[-1].strip():
        output.append("")
    output.extend(f"{key}={value}" for key, value in pending.items())
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-env",
        type=Path,
        help="Update an env file without printing the generated values.",
    )
    args = parser.parse_args()
    private_key, public_key = generate_keys()
    values = {
        "VAPID_PRIVATE_KEY": private_key,
        "VAPID_PUBLIC_KEY": public_key,
    }
    if args.write_env:
        _update_env(args.write_env, values)
        print(f"VAPID keys written to {args.write_env}; values were not displayed.")
        return
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
