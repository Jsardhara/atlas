"""Generate Atlas secrets idempotently.

Copies any missing keys into ``.env`` (without clobbering existing values —
broker keys etc. stay put), and fills in random hex values for the four
secrets that must never be human-typed:

- ``POSTGRES_PASSWORD``      (32 bytes)
- ``JWT_SECRET_KEY``         (64 bytes)
- ``API_ADMIN_PASSWORD``     (24 bytes)
- ``ATLAS_BEARER_TOKEN``     (32 bytes)

The bearer token is also written into the Jarvis ``.env`` so the bridge can
authenticate. Re-running is a no-op for any value that is already set.

Prints a masked summary; never prints actual secret values.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Iterable

ATLAS_ROOT = Path(__file__).resolve().parent.parent
JARVIS_ROOT = Path("C:/Users/jyot2/jarvis").resolve()

ENV_EXAMPLE = ATLAS_ROOT / ".env.example"
ENV_FILE = ATLAS_ROOT / ".env"
JARVIS_ENV_FILE = JARVIS_ROOT / ".env"

# key -> byte length for token_hex (output is 2*length hex chars)
GENERATED_SECRETS: dict[str, int] = {
    "POSTGRES_PASSWORD": 32,
    "JWT_SECRET_KEY": 64,
    "API_ADMIN_PASSWORD": 24,
    "ATLAS_BEARER_TOKEN": 32,
}

# Values that should be considered "unset" even if present in the file
SENTINEL_VALUES = {"", "change_me", "change_me_64_random_chars", "auto-generated"}


def _parse_env(text: str) -> dict[str, str]:
    """Parse a dotenv-style file into an ordered mapping (last value wins)."""
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines)
    if not payload.endswith("\n"):
        payload += "\n"
    path.write_text(payload, encoding="utf-8")


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]} (len={len(value)})"


def _is_unset(value: str) -> bool:
    return value.strip() in SENTINEL_VALUES


def _ensure_keys_in_env(
    example: dict[str, str],
    current_lines: list[str],
    current: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Append any keys present in .env.example but missing from .env.

    Existing values are preserved verbatim. Returns the new line list and
    a list of keys that were appended.
    """
    appended: list[str] = []
    new_lines = list(current_lines)
    if new_lines and new_lines[-1].strip() != "":
        new_lines.append("")
    for key, default in example.items():
        if key in current:
            continue
        new_lines.append(f"{key}={default}")
        current[key] = default
        appended.append(key)
    if appended and new_lines[-1].strip() != "":
        new_lines.append("")
    return new_lines, appended


def _replace_or_append(lines: list[str], key: str, value: str) -> list[str]:
    """Set ``key=value`` in lines; replaces the first definition or appends."""
    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if (
            not replaced
            and stripped
            and not stripped.startswith("#")
            and "=" in stripped
            and stripped.split("=", 1)[0].strip() == key
        ):
            out.append(f"{key}={value}")
            replaced = True
            continue
        out.append(line)
    if not replaced:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(f"{key}={value}")
    return out


def _sync_database_url(lines: list[str], password: str) -> list[str]:
    """Update DATABASE_URL to use the active Postgres password.

    Only rewrites if the existing value still references the literal
    ``change_me`` placeholder. Operator-customised URLs are preserved.
    """
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith("DATABASE_URL=")
            and "change_me" in stripped
        ):
            new_lines.append(
                f"DATABASE_URL=postgresql+asyncpg://atlas:{password}@localhost:5432/atlas"
            )
        else:
            new_lines.append(line)
    return new_lines


def main() -> int:
    if not ENV_EXAMPLE.exists():
        print(f"ERROR: {ENV_EXAMPLE} not found", file=sys.stderr)
        return 1

    example = _parse_env(ENV_EXAMPLE.read_text(encoding="utf-8"))

    env_lines = _read_lines(ENV_FILE)
    env_current = _parse_env("\n".join(env_lines)) if env_lines else {}

    # 1) Ensure every key in .env.example is present in .env
    env_lines, appended_keys = _ensure_keys_in_env(example, env_lines, env_current)

    # 2) Generate secrets where missing or sentinel
    generated: list[str] = []
    preserved: list[str] = []
    for key, byte_len in GENERATED_SECRETS.items():
        existing = env_current.get(key, "")
        if _is_unset(existing):
            new_value = secrets.token_hex(byte_len)
            env_lines = _replace_or_append(env_lines, key, new_value)
            env_current[key] = new_value
            generated.append(key)
        else:
            preserved.append(key)

    # 3) Keep DATABASE_URL coherent with POSTGRES_PASSWORD when still placeholder
    env_lines = _sync_database_url(env_lines, env_current["POSTGRES_PASSWORD"])

    _write_lines(ENV_FILE, env_lines)

    # 4) Sync ATLAS_BEARER_TOKEN into Jarvis .env
    bearer = env_current["ATLAS_BEARER_TOKEN"]
    jarvis_lines = _read_lines(JARVIS_ENV_FILE)
    jarvis_current = _parse_env("\n".join(jarvis_lines))
    jarvis_existing = jarvis_current.get("ATLAS_BEARER_TOKEN", "")
    if _is_unset(jarvis_existing) or jarvis_existing != bearer:
        jarvis_lines = _replace_or_append(jarvis_lines, "ATLAS_BEARER_TOKEN", bearer)
        _write_lines(JARVIS_ENV_FILE, jarvis_lines)
        jarvis_status = "updated"
    else:
        jarvis_status = "already in sync"

    # 5) Masked summary
    print("Atlas secret bootstrap")
    print(f"  .env file:        {ENV_FILE}")
    print(f"  example template: {ENV_EXAMPLE}")
    if appended_keys:
        print(f"  appended keys:    {', '.join(appended_keys)}")
    else:
        print("  appended keys:    none (all template keys already present)")
    print()
    print("Secrets:")
    for key in GENERATED_SECRETS:
        status = "GENERATED" if key in generated else "preserved"
        print(f"  {key:<22} {status:<10} {_mask(env_current[key])}")
    print()
    print(f"Jarvis bearer sync: {jarvis_status} ({JARVIS_ENV_FILE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
