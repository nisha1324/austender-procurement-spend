"""The Part 4 check set: drawn reproducibly, labelled in full, labels valid."""
from pathlib import Path

import pandas as pd
import pytest

from scripts import draw_check_set as dcs
from scripts.training_taxonomy import BASIS, KEYS

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "data" / "check_set" / "training_labels.csv"


@pytest.fixture(scope="module")
def labels():
    return pd.read_csv(LABELS, dtype={"cn_id": str}, keep_default_na=False)


@pytest.fixture(scope="module")
def pop():
    return dcs.population(dcs.training_connection())


def test_population_is_segment_86_only(pop):
    assert len(pop) == 3589
    assert pop.cn_id.is_unique


def test_labelled_rows_are_exactly_the_draw(labels, pop):
    drawn = dcs.draw(pop)
    assert list(drawn.cn_id) == list(labels.cn_id)
    assert list(drawn.stratum) == list(labels.stratum)
    # Large stratum is a census of $1m+, random stratum is all under $1m.
    assert set(labels[labels.stratum == "large"].cn_id) == set(pop[pop.value_aud.astype(float) >= 1e6].cn_id)
    assert (labels[labels.stratum == "random"].value_aud < 1e6).all()


def test_every_row_has_a_valid_label_and_basis(labels):
    assert set(labels.label) <= set(KEYS)
    assert set(labels.basis) <= set(BASIS)
    # 'none' is the basis exactly when nothing says what the training is.
    assert ((labels.label == "unspecified") == (labels.basis == "none")).all()


def test_draw_is_deterministic_and_seeded(pop):
    a, b = dcs.draw(pop), dcs.draw(pop.sample(frac=1, random_state=1))
    assert a.equals(b)  # input order doesn't matter
    assert not dcs.draw(pop, seed=1).cn_id.equals(a.cn_id)
