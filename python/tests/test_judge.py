"""見本の形では書けない約束を確かめる（swift/Tests/KangoTests/JudgeTests.swift と同じこと）。

色と理由のコードは、test_conformance.py が共通の見本（conformance/cases.json）で確かめています。"""
import json
from pathlib import Path

import kango

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "conformance" / "cases.json").read_text(encoding="utf-8"))


def _all():
    for case in CASES["cases"]:
        yield case, kango.judge(case["text"], case.get("ledger", CASES["ledger"]))


def test_brands_load():
    assert any(b["id"] == "amazon" and b["kind"] == "contract" for b in kango.BRANDS)
    assert any(b["id"] == "yamato" and b["kind"] == "everyone" for b in kango.BRANDS)


def test_green_never_says_genuine_or_safe():
    # 青は「割符が合いました」まで。「本物です」「安全です」とは言わない
    for case, r in _all():
        if r["level"] == "green":
            words = r["head"] + r["todo"] + "".join(x["text"] for x in r["reasons"])
            assert "本物" not in words and "安全" not in words, case["text"]


def test_helplines_unless_green():
    # 青以外では、相談先（#9110・188）を添える
    for case, r in _all():
        tels = [h["tel"] for h in r["helplines"]]
        assert tels == ([] if r["level"] == "green" else ["#9110", "188"]), case["text"]


def test_english_answers_keep_level_and_codes():
    # lang="en" で変わるのは文だけ。色・理由のコード・名乗った会社・リンク先は同じ
    for case, r in _all():
        e = kango.judge(case["text"], case.get("ledger", CASES["ledger"]), lang="en")
        assert {k: e[k] for k in ("level", "claimed", "hosts")} == {k: r[k] for k in ("level", "claimed", "hosts")}
        assert [x["code"] for x in e["reasons"]] == [x["code"] for x in r["reasons"]], case["text"]
        assert e["head"] == kango.PHRASES["heads"]["en"][e["level"]]
        if e["level"] == "green":
            words = (e["head"] + e["todo"] + "".join(x["text"] for x in e["reasons"])).lower()
            for w in ("genuine", "safe", "legit", "authentic"):
                assert w not in words, case["text"]


def test_english_uses_english_brand_names():
    r = kango.judge("【ヤマト運輸】お荷物のお届けにあがりましたが不在のため持ち帰りました https://yamato-hd.example/", [], lang="en")
    assert "Yamato Transport" in r["reasons"][0]["text"]


def test_helplines_by_region():
    text = "Your account will be suspended https://evil.example/"
    tels = lambda **kw: [(h.get("tel"), h.get("url")) for h in kango.judge(text, [], **kw)["helplines"]]
    assert tels() == [("#9110", None), ("188", None)]                 # 既定＝日本語・日本
    assert tels(lang="en") == []                                         # 英語で国が分からない時は出さない
    assert tels(lang="en", region="JP") == [("#9110", None), ("188", None)]
    assert tels(lang="en", region="us") == [(None, "https://reportfraud.ftc.gov/")]
    assert ("7726", None) in tels(lang="en", region="GB")
    assert tels(lang="en", region="AU")[0][1].startswith("https://portal.scamwatch.gov.au/")
    assert tels(lang="en", region="FR") == []                            # 窓口を確かめていない国は出さない


def test_unknown_lang_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        kango.judge("test", [], lang="xx")
