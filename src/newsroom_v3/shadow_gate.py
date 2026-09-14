from __future__ import annotations

import os


def main() -> int:
    engine = str(os.environ.get("NEWSROOM_ENGINE", "v2") or "v2").strip().lower()
    return 1 if engine == "v3" else 0


if __name__ == "__main__":
    raise SystemExit(main())
