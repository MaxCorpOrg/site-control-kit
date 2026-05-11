from __future__ import annotations


def main() -> int:
    from .app import main as _main

    return int(_main())


__all__ = ["main"]
