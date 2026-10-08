"""Offline checks: no network, no API key.  python tests/test_offline.py"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pushback import analyze, collect, data, grade, validation  # noqa: E402

EX = data.ROOT / "examples"


def test_items():
    items = data.load_items()
    assert len(items) == 5988 and len({it["scenario"] for it in items}) == 499
    assert collections.Counter(it["update_type"] for it in items) == {"neutral": 1996, "doomed_a": 1996, "doomed_b": 1996}
    assert len(data.phrasings()) == 5


def test_design():
    plan = collect.design(data.load_items())
    assert len(plan) == 6 * 499 and {(it["update_type"], it["chosen"]) for it in plan} == set(collect.CELLS)


def test_examples_regrade():
    """The recorded judge reads of every example aggregate to its recorded labels and outcome."""
    items = {it["item_id"]: it for it in data.load_items()}
    rows = [r for f in sorted((EX / "graded").glob("*.jsonl")) for r in data.read_jsonl(f)]
    assert rows
    for r in rows:
        labels = grade.aggregate(r["votes"])
        assert all(labels[k] == r[k] for k in grade.FIELDS), r["key"]
        assert grade.outcome(items[r["item_id"]], labels) == {k: r[k] for k in ("pushed_back", "outcome", "hedged")}


def test_analyze_examples():
    assert "| model |" in analyze.report(EX)
    (EX / "results.md").unlink()


def test_validation_table():
    t = {x["field"]: x for x in validation.table()}
    assert round(100 * t["dissent"]["agreement"]) == 94 and round(100 * t["request_reflected"]["agreement"]) == 96


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
