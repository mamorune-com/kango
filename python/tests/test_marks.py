"""行の印（kango.marks）の共通の見本（conformance/marks.json）を、すべて動かして確かめる。

Swift の swift/Tests/KangoTests/MarksTests.swift も、同じ見本を動かします。"""
import json
from pathlib import Path

import pytest

import kango

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "conformance" / "marks.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES["cases"])
def test_case(case):
    got = [{k: m[k] for k in ("line", "level", "codes")}
           for m in kango.marks(case["lines"], case.get("ledger", CASES["ledger"]))]
    assert got == case["marks"], case["note"]


def test_marks_do_not_change_the_answer():
    # 印を付けても、判定の答え（judge）は今までと同じ
    for case in CASES["cases"]:
        led = case.get("ledger", CASES["ledger"])
        text = "\n".join(case["lines"])
        before = kango.judge(text, led)
        kango.marks(case["lines"], led)
        assert kango.judge(text, led) == before


def test_marks_never_on_green_and_every_code_has_a_label():
    for case in CASES["cases"]:
        for m in kango.marks(case["lines"], case.get("ledger", CASES["ledger"])):
            assert m["level"] in ("red", "amber")
            assert len(m["labels"]) == len(m["codes"])
            assert "official" not in m["codes"] and "in_ledger" not in m["codes"]


def test_enough_cases():
    assert len(CASES["cases"]) >= 8, "見本が読めていません"


def test_marks_labels_in_english():
    # lang="en" で変わるのは labels の言葉だけ（行・色・コードは同じ）
    for case in CASES["cases"]:
        led = case.get("ledger", CASES["ledger"])
        ja = kango.marks(case["lines"], led)
        en = kango.marks(case["lines"], led, lang="en")
        assert [{k: m[k] for k in ("line", "level", "codes")} for m in en] == \
               [{k: m[k] for k in ("line", "level", "codes")} for m in ja]
        for m in en:
            assert m["labels"] == [kango.PHRASES["mark_labels"]["en"][c] for c in m["codes"]]
