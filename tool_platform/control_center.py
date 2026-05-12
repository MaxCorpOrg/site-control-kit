from __future__ import annotations

import os
from typing import Sequence

from .telegram_runtime import PRODUCTION_MODE_ENV


def main(argv: Sequence[str] | None = None) -> int:
    os.environ.setdefault(PRODUCTION_MODE_ENV, "production")
    from .gui import main as gui_main

    return int(gui_main(list(argv) if argv is not None else None))


if __name__ == "__main__":
    raise SystemExit(main())
