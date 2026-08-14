#!/usr/bin/env python3
"""Build all 20 kits and emit the catalog used by the Strata app."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kits import CATALOG, kit_01, kit_02, kit_03
from kits_04_12 import kit_04, kit_05, kit_06, kit_07, kit_08, kit_09, kit_10, kit_11, kit_12
from kits_13_20 import kit_13, kit_14, kit_15, kit_16, kit_17, kit_18, kit_19, kit_20

KITS = [
    kit_01, kit_02, kit_03, kit_04, kit_05,
    kit_06, kit_07, kit_08, kit_09, kit_10,
    kit_11, kit_12, kit_13, kit_14, kit_15,
    kit_16, kit_17, kit_18, kit_19, kit_20,
]


def main() -> int:
    errors = []
    for fn in KITS:
        try:
            fn()
        except Exception:
            errors.append(fn.__name__)
            traceback.print_exc()
            print(f"FAILED {fn.__name__}", file=sys.stderr)

    out_json = Path("/workspace/public/catalog.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": "Strata",
        "prefix": "bio",
        "description": "Starter data kits for decomposing headline effects in experimental, clinical-population, and omics analysis.",
        "kits": CATALOG,
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    src = Path("/workspace/src/data/catalog.json")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(out_json.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"catalog kits={len(CATALOG)} errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
