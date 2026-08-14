"""Shared helpers for star-schema starter kits."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook

ROOT = Path("/workspace")
SCRATCH = ROOT / "scratch"
PACKAGES = ROOT / "PACKAGES"
PUBLIC_PACKAGES = ROOT / "public" / "packages"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def infer_type(series: pd.Series, force_string: bool = False) -> str:
    if force_string:
        return "string"
    s = series.dropna()
    if s.empty:
        return "string"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        # integer-like floats (SEQN stored as 93703.0)
        if s.apply(lambda x: float(x).is_integer()).all():
            return "integer"
        return "float"
    sample = s.astype(str).head(20).tolist()
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v or "") for v in sample):
        return "date"
    return "string"


def example_value(series: pd.Series) -> Any:
    s = series.dropna()
    if s.empty:
        return None
    val = s.iloc[0]
    if isinstance(val, float) and val.is_integer():
        return int(val)
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            pass
    if isinstance(val, (pd.Timestamp,)):
        return str(val.date())
    return val if isinstance(val, (str, int, float, bool)) or val is None else str(val)


def write_csv(path: Path, df: pd.DataFrame) -> int:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].where(out[col].notna(), None)
    out.to_csv(path, index=False, encoding="utf-8")
    return len(out)


def write_overview(
    path: Path,
    *,
    package: str,
    framing: str,
    files: list[tuple[str, int, str]],
    join_keys: str,
    source: str,
    license_text: str,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Overview"
    ws.append(["Field", "Value", ""])
    ws.append(["Package", package, ""])
    ws.append(["Business framing", framing, ""])
    ws.append(["", "", ""])
    ws.append(["File", "Rows", "Grain"])
    for name, rows, grain in files:
        ws.append([name, int(rows), grain])
    ws.append(["", "", ""])
    ws.append(["Join keys", join_keys, ""])
    ws.append(["Source & license", source, license_text])
    wb.save(path)


def write_dictionary(path: Path, meta: dict[str, Any], files: dict[str, Any]) -> None:
    payload = {"meta": meta, "files": files}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def field(
    name: str,
    typ: str,
    description: str,
    example: Any,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": typ,
        "description": description,
        "example": example,
    }


def fields_from_df(
    df: pd.DataFrame,
    descriptions: dict[str, str],
    string_cols: set[str] | None = None,
) -> list[dict[str, Any]]:
    string_cols = string_cols or set()
    out = []
    for col in df.columns:
        typ = infer_type(df[col], force_string=col in string_cols)
        out.append(
            field(
                col,
                typ,
                descriptions.get(col, col.replace("_", " ")),
                example_value(df[col]),
            )
        )
    return out


def qa_no_orphans(fact: pd.DataFrame, dim: pd.DataFrame, fk: str, pk: str, label: str) -> int:
    left = set(fact[fk].dropna().astype(str))
    right = set(dim[pk].dropna().astype(str))
    missing = left - right
    if missing:
        raise SystemExit(f"QA orphan keys in {label}: {list(missing)[:8]} ({len(missing)} total)")
    return 0


def finalize_kit(
    slug: str,
    *,
    tables: dict[str, pd.DataFrame],
    grains: dict[str, str],
    descriptions: dict[str, dict[str, str]],
    table_docs: dict[str, str],
    meta: dict[str, Any],
    package_title: str,
    framing: str,
    join_keys: str,
    string_cols: dict[str, set[str]] | None = None,
    extra_files: list[str] | None = None,
) -> Path:
    """Write CSVs + dictionary + overview, copy to public/, return kit dir."""
    string_cols = string_cols or {}
    out = ensure_dir(PACKAGES / slug)
    file_rows: list[tuple[str, int, str]] = []
    files_spec: dict[str, Any] = {}

    for fname, df in tables.items():
        if not fname.endswith(".csv"):
            raise ValueError(fname)
        n = write_csv(out / fname, df)
        file_rows.append((fname, n, grains[fname]))
        files_spec[fname] = {
            "description": table_docs[fname],
            "fields": fields_from_df(df, descriptions.get(fname, {}), string_cols.get(fname)),
        }

    write_dictionary(out / "data_dictionary.json", meta, files_spec)
    write_overview(
        out / "overview.xlsx",
        package=package_title,
        framing=framing,
        files=file_rows,
        join_keys=join_keys,
        source=meta["source"],
        license_text=meta["license"],
    )

    # Every on-disk file (except optional extras already listed) must appear in dictionary.
    on_disk = sorted(p.name for p in out.iterdir() if p.is_file())
    listed = set(files_spec) | {"data_dictionary.json", "overview.xlsx"} | set(extra_files or [])
    mystery = [n for n in on_disk if n not in listed and not n.startswith(".")]
    if mystery:
        raise SystemExit(f"{slug}: files on disk not in dictionary: {mystery}")

    pub = ensure_dir(PUBLIC_PACKAGES / slug)
    for p in out.iterdir():
        if p.is_file():
            target = pub / p.name
            if target.exists() or target.is_symlink():
                target.unlink()
            target.write_bytes(p.read_bytes())

    print(f"  wrote {slug}  files={len(on_disk)}  " + ", ".join(f"{n}:{r}" for n, r, _ in file_rows))
    return out


def catalog_entry(
    slug: str,
    *,
    title: str,
    framing: str,
    domain: str,
    tags: list[str],
    source: str,
    license_text: str,
    tables: dict[str, pd.DataFrame],
    grains: dict[str, str],
) -> dict[str, Any]:
    nn = slug.split("_", 1)[0]
    return {
        "id": slug,
        "prefix": "bio",
        "code": nn,
        "title": title,
        "framing": framing,
        "domain": domain,
        "tags": tags,
        "source": source,
        "license": license_text,
        "n_tables": len(tables),
        "n_fact_rows": int(sum(len(df) for name, df in tables.items() if name.startswith("fact_"))),
        "files": [
            {"name": name, "rows": int(len(df)), "grain": grains[name]}
            for name, df in tables.items()
        ],
    }
