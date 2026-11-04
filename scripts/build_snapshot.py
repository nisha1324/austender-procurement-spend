"""Flatten the raw OCDS day files into one tidy table: `data/releases.csv.gz`.

One row per *release*, which is one version of a contract notice: the original notice
(`release_type = contract`) or a later amendment to it (`release_type = amendment`).
Each AusTender release has exactly one contract, one award, one supplier and one UNSPSC
item; the build stops if that ever stops being true, rather than silently dropping data.

Personal contact details (officer names, email addresses, phone numbers, street addresses)
are left out. They aren't needed for spend analysis. Branch and division are kept, and are
read from the supplier party, which is where the API puts the agency's contact block.

    python -m scripts.build_snapshot
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "data" / "releases.csv.gz"
SNAPSHOT = ROOT / "data" / "SNAPSHOT.json"

COLUMNS = [
    "release_id", "ocid", "cn_id", "release_type", "amendment_id", "amends_release_id",
    "release_date", "cn_published", "fetched_day",
    "agency", "agency_abn", "agency_branch", "agency_division",
    "supplier_id", "supplier_name", "supplier_abn", "supplier_locality", "supplier_region",
    "supplier_postcode", "supplier_country",
    "unspsc", "description", "agency_reference", "start_date", "end_date",
    "value_aud", "currency", "status",
    "method", "method_details", "limited_reason_code", "limited_reason",
    "exemption_flag", "exemption_code", "exemption",
]


def _one(seq, what: str, release_id: str):
    if seq is None or len(seq) != 1:
        n = 0 if seq is None else len(seq)
        raise ValueError(f"{release_id}: expected exactly one {what}, found {n}")
    return seq[0]


def _abn(party: dict) -> str | None:
    for ident in party.get("additionalIdentifiers") or []:
        if ident.get("scheme") == "AU-ABN":
            return ident.get("id")
    return None


def flatten_release(rel: dict, fetched_day: str) -> dict:
    rid = rel["id"]
    tags = rel.get("tag") or []
    if tags == ["contract"]:
        release_type = "contract"
    elif tags == ["contractAmendment"]:
        release_type = "amendment"
    else:
        raise ValueError(f"{rid}: unexpected tag {tags}")

    contract = _one(rel.get("contracts"), "contract", rid)
    award = _one(rel.get("awards"), "award", rid)
    supplier_ref = _one(award.get("suppliers"), "supplier", rid)
    item = _one(contract.get("items"), "item", rid)

    agencies = [p for p in rel.get("parties", []) if "procuringEntity" in p.get("roles", [])]
    agency = _one(agencies, "procuring entity", rid)
    suppliers = [p for p in rel.get("parties", []) if p.get("id") == supplier_ref["id"]]
    supplier = _one(suppliers, "supplier party", rid)
    if "supplier" not in supplier.get("roles", []):
        raise ValueError(f"{rid}: award supplier is not marked as a supplier party")

    amendments = contract.get("amendments") or []
    amendment = None
    if release_type == "amendment":
        # The amendment that *this* release records (earlier ones may be listed too).
        mine = [a for a in amendments if a.get("releaseID") == rid]
        amendment = _one(mine, "own amendment record", rid)
    elif amendments:
        raise ValueError(f"{rid}: an original notice should not list amendments")

    tender = rel.get("tender") or {}
    s_addr = supplier.get("address") or {}
    # Trap: AusTender puts the *agency's* contact (officer, branch, division) on the supplier
    # party's contactPoint, not on the procuring entity. Only branch and division are kept.
    a_contact = supplier.get("contactPoint") or {}
    value = contract.get("value") or {}
    period = contract.get("period") or {}
    classification = item.get("classification") or {}
    if classification.get("scheme") != "UNSPSC":
        raise ValueError(f"{rid}: item is not classified with UNSPSC")

    return {
        "release_id": rid,
        "ocid": rel.get("ocid"),
        "cn_id": contract.get("id"),
        "release_type": release_type,
        "amendment_id": amendment.get("id") if amendment else None,
        "amends_release_id": amendment.get("amendsReleaseID") if amendment else None,
        "release_date": rel.get("date"),
        # AusTender puts the notice's publish date in `dateSigned`; it is not a signing date.
        "cn_published": contract.get("dateSigned"),
        "fetched_day": fetched_day,
        "agency": agency.get("name"),
        "agency_abn": _abn(agency),
        "agency_branch": a_contact.get("branch"),
        "agency_division": a_contact.get("division"),
        "supplier_id": supplier.get("id"),
        "supplier_name": supplier.get("name"),
        "supplier_abn": _abn(supplier),
        "supplier_locality": s_addr.get("locality"),
        "supplier_region": s_addr.get("region"),
        "supplier_postcode": s_addr.get("postalCode"),
        "supplier_country": s_addr.get("countryName"),
        "unspsc": classification.get("id"),
        "description": contract.get("description"),
        "agency_reference": contract.get("title"),
        "start_date": period.get("startDate"),
        "end_date": period.get("endDate"),
        "value_aud": value.get("amount"),
        "currency": value.get("currency"),
        "status": contract.get("status"),
        "method": tender.get("procurementMethod"),
        "method_details": tender.get("procurementMethodDetails"),
        "limited_reason_code": tender.get("limitedTenderReasonCode"),
        "limited_reason": tender.get("limitedTenderReason"),
        "exemption_flag": tender.get("limitedTenderExempt"),
        "exemption_code": tender.get("exemptionCode"),
        "exemption": tender.get("exemption"),
    }


def load_raw(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, dict]:
    files = sorted(raw_dir.glob("*.json.gz"))
    if not files:
        raise SystemExit(f"no raw files in {raw_dir}; run `python -m scripts.download_data` first")
    rows, fetched, licences, pages = [], [], set(), 0
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            day = json.load(fh)
        licences.add(day["license"])
        fetched.append(day["fetched_at"])
        pages += day["pages"]
        rows.extend(flatten_release(r, day["day"]) for r in day["releases"])
    df = pd.DataFrame(rows, columns=COLUMNS)
    meta = {
        "day_files": len(files),
        "first_day": files[0].name.split(".")[0],
        "last_day": files[-1].name.split(".")[0],
        "api_pages": pages,
        "licences": sorted(licences),
        "fetched_from": min(fetched),
        "fetched_to": max(fetched),
    }
    return df, meta


def published_day_canberra(cn_published: pd.Series) -> pd.Series:
    ts = pd.to_datetime(cn_published, utc=True).dt.tz_convert("Australia/Sydney")
    return ts.dt.strftime("%Y-%m-%d")


def build(df: pd.DataFrame) -> pd.DataFrame:
    # The API's date window includes both ends, so a notice published at exactly Canberra
    # midnight comes back for two days. Keep each release only under the Canberra day it was
    # published (midnight starts the new day). This also drops anything past the last day.
    pub_day = published_day_canberra(df["cn_published"])
    keep = df["fetched_day"] == pub_day
    dropped = df[~keep]
    # Nothing may vanish: a dropped row must have its twin kept, or fall after the last day.
    lost = dropped[~dropped["release_id"].isin(df.loc[keep, "release_id"])
                   & (pub_day[~keep] <= df["fetched_day"].max())]
    if not lost.empty:
        raise ValueError(f"{len(lost)} releases sit under a day they weren't published on")
    df = df[keep]
    # Any repeat left must be identical; a release id with two different contents fails.
    dupes = df[df.duplicated("release_id", keep=False)]
    if not dupes.empty:
        conflicting = dupes.drop_duplicates().duplicated("release_id", keep=False)
        if conflicting.any():
            raise ValueError(f"{conflicting.sum()} release ids repeat with different contents")
    df = df.drop_duplicates()
    return df.sort_values(["cn_published", "cn_id", "release_date", "release_id"]).reset_index(drop=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    raw, meta = load_raw()
    df = build(raw)
    df.to_csv(OUT, index=False, compression={"method": "gzip", "mtime": 0})
    meta.update(
        {
            "source": "AusTender OCDS API, findByDates/contractPublished (Department of Finance)",
            "api": "https://api.tenders.gov.au/ocds/",
            "raw_releases": int(len(raw)),
            "boundary_repeats_dropped": int(len(raw) - len(df)),
            "releases": int(len(df)),
            "contract_notices": int((df.release_type == "contract").sum()),
            "amendments": int((df.release_type == "amendment").sum()),
            "file": OUT.name,
            "sha256": sha256(OUT),
            "built_with": f"pandas {pd.__version__}",
        }
    )
    SNAPSHOT.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
