#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any


DEFAULT_PROFILE = "balanced"
PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "interval_sec": 8.0,
        "env": {
            "CHAT_SCROLL_STEPS": "10",
            "CHAT_DEEP_LIMIT": "24",
            "CHAT_MAX_RUNTIME": "120",
            "TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP": "4",
            "TELEGRAM_CHAT_DEEP_PRIORITY_MIN_RUNTIME": "14",
        },
    },
    "balanced": {
        "interval_sec": 20.0,
        "env": {},
    },
    "deep": {
        "interval_sec": 30.0,
        "env": {
            "CHAT_SCROLL_STEPS": "18",
            "CHAT_DEEP_LIMIT": "60",
            "CHAT_MAX_RUNTIME": "360",
            "TELEGRAM_CHAT_MENTION_DEEP_MAX_PER_STEP": "4",
            "TELEGRAM_CHAT_DEEP_PRIORITY_EXTRA_ROUNDS": "2",
            "TELEGRAM_CHAT_DEEP_PRIORITY_MIN_RUNTIME": "24",
            "TELEGRAM_CHAT_DISCOVERY_SCROLL_BURST": "3",
            "TELEGRAM_CHAT_JUMP_SCROLL_TRIGGER_STALL": "2",
        },
    },
}


def available_profiles() -> list[str]:
    return sorted(PROFILE_PRESETS)


def resolve_profile_name(name: str | None) -> str:
    normalized = str(name or DEFAULT_PROFILE).strip().lower()
    if normalized in PROFILE_PRESETS:
        return normalized
    return DEFAULT_PROFILE


def resolve_profile(name: str | None) -> dict[str, Any]:
    return PROFILE_PRESETS[resolve_profile_name(name)]


def resolve_chain_interval(profile_name: str | None) -> float:
    profile = resolve_profile(profile_name)
    return max(float(profile.get("interval_sec", 20.0) or 20.0), 0.0)


def build_profile_env(profile_name: str | None) -> dict[str, str]:
    profile = resolve_profile(profile_name)
    env = {}
    for key, value in dict(profile.get("env") or {}).items():
        env[str(key)] = str(value)
    return env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram profile presets helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    env_parser = subparsers.add_parser("env", help="Emit profile env overrides.")
    env_parser.add_argument("profile", nargs="?", default=DEFAULT_PROFILE, choices=available_profiles())
    env_parser.add_argument("--format", choices=("tsv", "json"), default="tsv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "env":
        profile_name = resolve_profile_name(args.profile)
        payload = {
            "profile": profile_name,
            "interval_sec": resolve_chain_interval(profile_name),
            "env": build_profile_env(profile_name),
        }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        for key, value in payload["env"].items():
            print(f"{key}\t{value}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
