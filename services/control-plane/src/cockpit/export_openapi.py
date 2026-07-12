"""Export the OpenAPI schema for packages/contracts (make contracts)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    from cockpit.main import app

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"OpenAPI schema written to {target}")


if __name__ == "__main__":
    main()
