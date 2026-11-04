"""Is an amendment's value the new contract total, or just the change? This settles it.

The API doesn't document it. The government's older bulk export on data.gov.au (the
"Historical Australian Government Contract Notice Data" CSV, 2019) does: it has an
`Amendments Value` column that holds the *change* each amendment made. This script takes two
amendments from that file and compares them with the same contract in the live API.

If the API value is a running total, the step between two consecutive API values equals the
export's change exactly. The result is written to `results/AMENDMENT_CHECK.md`, and the API
values used are saved to `tests/fixtures/cn3350299_values.json` so the test runs offline.

    python -m scripts.check_amendment_values
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from scripts.download_data import get_json

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "cn3350299_values.json"
REPORT = ROOT / "results" / "AMENDMENT_CHECK.md"

CN = "CN3350299"  # Defence, "Provision of new air combat capability"
EXPORT_URL = (
    "https://data.gov.au/data/dataset/5c7fa69b-b0e9-4553-b8df-2a022dd2e982/resource/"
    "bc2097b7-8116-4e9d-9953-98813635892a/download"
)
# Copied from rows 2 and 5 of that CSV (columns `Contract ID` and `Amendments Value`).
EXPORT_CHANGES = {"CN3350299-A16": Decimal("6284067617"), "CN3350299-A18": Decimal("2118459170")}


def amendment_no(amendment_id: str | None) -> int:
    """CN123-A16 -> 16, the parent notice -> 0. Sort on this, never on the text."""
    return 0 if not amendment_id else int(amendment_id.rsplit("-A", 1)[1])


def api_values(cn: str = CN) -> dict[str, str]:
    data = get_json(f"https://api.tenders.gov.au/ocds/findById/{cn}")
    values = {}
    for rel in data["releases"]:
        contract = rel["contracts"][0]
        own = [a["id"] for a in contract.get("amendments", []) if a.get("releaseID") == rel["id"]]
        values[own[0] if own else cn] = contract["value"]["amount"]
    return dict(sorted(values.items(), key=lambda kv: amendment_no(kv[0] if kv[0] != cn else None)))


def compare(values: dict[str, str]) -> list[dict]:
    rows = []
    for amendment, change in EXPORT_CHANGES.items():
        n = amendment_no(amendment)
        before = values[f"{CN}-A{n - 1}"]
        after = values[amendment]
        step = Decimal(after) - Decimal(before)
        rows.append(
            {"amendment": amendment, "api_before": before, "api_after": after,
             "api_step": str(step), "export_change": str(change), "match": step == change}
        )
    return rows


def main() -> None:
    values = api_values()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(values, indent=1) + "\n")
    rows = compare(values)
    lines = [
        "# Amendment values: running total, not the change",
        "",
        f"Contract `{CN}` (Department of Defence) in the live AusTender OCDS API, against the",
        f"`Amendments Value` column of the government's [historical CN export]({EXPORT_URL}).",
        "",
        "| Amendment | API value before | API value after | Step in the API | Change in the export | Match |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['amendment']} | {Decimal(r['api_before']):,.2f} | {Decimal(r['api_after']):,.2f} "
            f"| {Decimal(r['api_step']):,.2f} | {Decimal(r['export_change']):,.2f} "
            f"| {'yes' if r['match'] else 'NO'} |"
        )
    verdict = all(r["match"] for r in rows)
    lines += [
        "",
        f"The contract has {len(values)} versions in the API (the notice and "
        f"{len(values) - 1} amendments).",
        "",
        "**Verdict: " + (
            "each amendment's value is the contract's new total.** Summing every version of a "
            "notice would count the same money again and again; use the latest version only."
            if verdict else "the values did not match; do not assume running totals.**"
        ),
        "",
    ]
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))
    if not verdict:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
