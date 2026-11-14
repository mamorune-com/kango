"""data/brands.csv と data/phrases.json（正）から、Python と Swift の同梱データを作り直す。

使い方: python3 scripts/sync_brands.py
会社や公式ドメインを足した時は data/brands.csv だけを、答えの文や言いまわしを変えた時は data/phrases.json だけを直し、
これで写す（CI が食い違いを落とす）。
"""
import csv
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "data/brands.csv"


def split(v):
    return [s.strip() for s in (v or "").split("|") if s.strip()]


rows = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "words": split(r["words"]),
         "domains": split(r["domains"]), "stems": split(r["stems"]), "checked": r["checked"] or None,
         "name_en": r.get("name_en") or r["name"]}
        for r in csv.DictReader(open(src, encoding="utf-8"))]
(root / "swift/Sources/Kango/Resources/brands.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
shutil.copyfile(src, root / "python/kango/brands.csv")
phrases = json.loads((root / "data/phrases.json").read_text(encoding="utf-8"))   # 壊れた JSON はここで止める
for dst in ("python/kango/phrases.json", "swift/Sources/Kango/Resources/phrases.json"):
    shutil.copyfile(root / "data/phrases.json", root / dst)
print(f"{len(rows)} 社と、答えの文（{'・'.join(phrases['languages'])}）を写しました")
