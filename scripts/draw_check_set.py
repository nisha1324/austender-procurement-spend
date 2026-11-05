"""Draw the Part 4 check set: notices to label by hand before any rules are written.

Two strata, so the check covers both the typical notice and the money:
- `large`: every training notice worth $1m or more (latest value), a census;
- `random`: 200 notices drawn at random (seed 2025) from the rest.

Writes `data/check_set/to_label.csv`. The labelled copy, `data/check_set/training_labels.csv`,
adds `label`, `basis` and `note` by hand (see `data/check_set/LABELLING_GUIDE.md`); a test checks
that its notices are exactly this draw.

    python -m scripts.draw_check_set
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.profile_releases import ROOT, SQL_DIR
from scripts.spend_cube import spend_connection

CHECK_DIR = ROOT / "data" / "check_set"
LARGE_FROM = 1_000_000
RANDOM_N = 200
SEED = 2025
COLUMNS = ["cn_id", "stratum", "description", "supplier_name", "agency", "value_aud"]


def training_connection(releases_csv: Path | None = None):
    con = spend_connection(releases_csv) if releases_csv else spend_connection()
    con.execute((SQL_DIR / "03_training.sql").read_text())
    return con


def population(con) -> pd.DataFrame:
    return con.sql("SELECT * FROM training ORDER BY cn_id").df()


def draw(pop: pd.DataFrame, n: int = RANDOM_N, seed: int = SEED) -> pd.DataFrame:
    pop = pop.sort_values("cn_id").reset_index(drop=True)
    large = pop[pop.value_aud.astype(float) >= LARGE_FROM].assign(stratum="large")
    rest = pop[pop.value_aud.astype(float) < LARGE_FROM]
    rand = rest.sample(n=min(n, len(rest)), random_state=seed).assign(stratum="random")
    out = pd.concat([large, rand]).sort_values(["stratum", "cn_id"])
    out["value_aud"] = out.value_aud.astype(float).round(2)
    return out[COLUMNS].reset_index(drop=True)


def main() -> None:
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    pop = population(training_connection())
    sample = draw(pop)
    sample.to_csv(CHECK_DIR / "to_label.csv", index=False)
    print(f"{len(pop):,} training notices; drew {len(sample)} "
          f"({(sample.stratum == 'large').sum()} large, {(sample.stratum == 'random').sum()} random)")


if __name__ == "__main__":
    main()
