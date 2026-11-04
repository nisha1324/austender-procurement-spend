"""Category names for the UNSPSC codes on AusTender notices.

AusTender doesn't send category names, only codes. Agencies pick each code from the
**AusTender Customised UNSPSC Codeset** (1 July 2023 edition), which the Department of Finance
publishes on data.gov.au with the historical contract notice data (CC BY 3.0 AU). This script
downloads that file, checks its SHA-256, and writes `data/unspsc_categories.csv`: one row per
code with its title, its segment (2 digits) and its family (4 digits).

The codeset is a flat list in segment order:
- a segment is a row with no code (or a code ending in 000000), holding the segment title;
- a family is a code ending in 0000;
- the rest are classes (ending in 00) or commodities (8 digits), which AusTender allows where
  a family is too broad.

Ten families in use have codes under them but no family row of their own. Their titles are
written by hand from the codes under them (`FAMILY_TITLES_FROM_CHILDREN`) and marked as such in
the `family_title_source` column, so no one mistakes them for official names.

    python -m scripts.build_categories
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import pandas as pd

from scripts.download_data import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "austender-customised-unspsc-codeset-1-july-2023.xlsx"
OUT = ROOT / "data" / "unspsc_categories.csv"

URL = (
    "https://data.gov.au/data/dataset/5c7fa69b-b0e9-4553-b8df-2a022dd2e982/resource/"
    "bae9cb73-1500-4d45-a862-eac2706cfbd4/download/austender-customised-unspsc-codeset-1-july-2023-1.xlsx"
)
SHA256 = "90d9b46aa02992835f9114912459f6c7e6ae01c0d161ec78827361a22b9e5a32"

# Families with codes under them but no family row in the codeset. Each title is a plain
# summary of the codeset entries listed after it, not an official UNSPSC name.
FAMILY_TITLES_FROM_CHILDREN = {
    "4621": "Workplace safety training aids",            # 46211500
    "5610": "Furniture",                                 # 56101500 Furniture, 56101700 Office furniture
    "7215": "Specialised building trade services",       # HVAC, painting, electrical, carpentry, ...
    "7813": "Storage and archiving services",            # file archive, warehousing, document storage
    "8116": "Cloud services (SaaS, PaaS, IaaS)",         # 81162000, 81162100, 81162103, 81162200
    "8211": "Writing, translation and publicity services",  # technical writing, transcribing, ...
    "8411": "Accounting and audit services",             # 84111500, 84111600, 84111603
    "8517": "Funeral and associated services",           # 85171500
    "8610": "Vocational rehabilitation services",        # 86101803
    "8614": "Library or documentation services",         # 86141704
}

COLUMNS = ["code", "title", "level", "goods_services", "segment", "segment_title",
           "family", "family_title", "family_title_source"]


def download(path: Path = RAW) -> bytes:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=90) as resp:
            path.write_bytes(resp.read())
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"{path.name}: SHA-256 {digest} is not the pinned {SHA256}. "
                         "The codeset has changed; check it before updating the pin.")
    return data


def level(code: str) -> str:
    if code.endswith("000000"):
        return "segment"
    if code.endswith("0000"):
        return "family"
    if code.endswith("00"):
        return "class"
    return "commodity"


def parse(rows: pd.DataFrame) -> pd.DataFrame:
    """`rows`: the sheet below its two header lines, columns code, title, definition, goods_services."""
    rows = rows.copy()
    rows["code"] = rows["code"].fillna("").astype(str).str.strip()
    rows["title"] = rows["title"].fillna("").astype(str).str.strip()
    rows = rows[(rows.code != "") | (rows.title != "")].reset_index(drop=True)
    bad = rows[(rows.code != "") & ~rows.code.str.fullmatch(r"\d{8}")]
    if len(bad):
        raise ValueError(f"codes that aren't 8 digits: {bad.code.tolist()}")

    # A segment row without a code takes its number from the next coded row.
    segment_titles: dict[str, str] = {}
    pending: str | None = None
    for code, title in zip(rows.code, rows.title):
        if code == "":
            if pending is not None:
                raise ValueError(f"two segment rows in a row: {pending!r}, {title!r}")
            pending = title
            continue
        seg = code[:2]
        if pending is not None:
            if seg in segment_titles:
                raise ValueError(f"segment {seg} appears twice")
            segment_titles[seg] = pending
            pending = None
        if code.endswith("000000"):
            segment_titles.setdefault(seg, title)
    if pending is not None:
        raise ValueError(f"segment row {pending!r} has no codes after it")

    coded = rows[rows.code != ""].copy()
    if coded.code.duplicated().any():
        raise ValueError(f"duplicate codes: {coded.code[coded.code.duplicated()].tolist()}")
    family_rows = dict(zip(coded.code[coded.code.str.endswith("0000")].str[:4],
                           coded.title[coded.code.str.endswith("0000")]))

    out = pd.DataFrame({"code": coded.code, "title": coded.title,
                        "goods_services": coded["goods_services"].fillna("").str.strip()})
    out["level"] = out.code.map(level)
    out["segment"] = out.code.str[:2]
    out["segment_title"] = out.segment.map(segment_titles)
    out["family"] = out.code.str[:4]
    out.loc[out.level == "segment", "family"] = ""
    official = out.family.map(family_rows)
    derived = out.family.map(FAMILY_TITLES_FROM_CHILDREN)
    out["family_title"] = official.fillna(derived).fillna("")
    out["family_title_source"] = "codeset"
    out.loc[official.isna() & derived.notna(), "family_title_source"] = "derived from child codes"
    out.loc[out.level == "segment", "family_title_source"] = ""

    missing = out[(out.level != "segment") & (out.family_title == "")]
    if len(missing):
        raise ValueError(f"families with no title: {sorted(missing.family.unique())}")
    clash = set(family_rows) & set(FAMILY_TITLES_FROM_CHILDREN)
    if clash:
        raise ValueError(f"hand-written titles for families the codeset names: {sorted(clash)}")
    if out.segment_title.isna().any():
        raise ValueError(f"codes with no segment: {out.code[out.segment_title.isna()].tolist()}")
    return out[COLUMNS].reset_index(drop=True)


def read_codeset(path: Path = RAW) -> pd.DataFrame:
    sheet = pd.read_excel(path, header=None, skiprows=2, dtype=str,
                          names=["code", "title", "definition", "goods_services"])
    return parse(sheet)


def main() -> None:
    download()
    cats = read_codeset()
    cats.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(cats)} codes, {cats.segment.nunique()} segments, "
          f"{cats.family[cats.family != ''].nunique()} families")


if __name__ == "__main__":
    main()
