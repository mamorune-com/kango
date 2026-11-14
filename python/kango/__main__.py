"""勘合をコマンドで試す。

  echo "【楽天カード】ご請求額が確定しました https://www.rakuten-card.co.jp/" | python -m kango --ledger rakuten
  python -m kango --ledger rakuten,docomo --json < message.txt
  python -m kango --brands
  python -m kango --ledger paypal --lang en --region US < message.txt   # 答えを英語で・相談先は米国

文面は保存せず、外へ送らず、リンク先へもアクセスしません。
届いた文面は、文面を省いて起動し、貼り付けてから Ctrl-D で渡すのがおすすめです（引数や echo で渡すと、シェルの履歴に文面が残ります）。
答えの色によらず、終了コードは 0 です（色は --json の "level" で読めます）。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import BRANDS, LANGUAGES, REGIONS, judge

LABELS = {"ja": {"green": "青", "amber": "黄", "red": "赤", "todo": "次にすること", "help": "相談先"},
          "en": {"green": "Green", "amber": "Amber", "red": "Red", "todo": "What to do", "help": "Get help"}}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m kango",
        description="勘合で文面を照らし合わせ、青・黄・赤で答えます。"
                    "AI を使わず、文面を保存せず、リンク先へもアクセスしません。",
        epilog="届いた文面は、文面を省いて起動し、貼り付けてから Ctrl-D で渡すのがおすすめです"
               "（引数や echo で渡すと、シェルの履歴に文面が残ります）。",
    )
    p.add_argument("text", nargs="?", help="照らし合わせる文面（省くと標準入力から読みます）")
    p.add_argument("--ledger", default="", metavar="ID,ID",
                   help="契約台帳＝取引している会社の id をカンマ区切りで（例：rakuten,docomo）")
    p.add_argument("--json", action="store_true", help="答えを JSON で出す")
    p.add_argument("--brands", action="store_true", help="台帳に入れられる会社の一覧を出す（id・名前・種類・確かめた日）")
    p.add_argument("--lang", default="ja", choices=LANGUAGES, help="答えの文の言語（ja か en。既定は ja）")
    p.add_argument("--region", default=None, metavar="CODE",
                   help="相談先を出す国・地域（" + "・".join(REGIONS) + "）。省くと、日本語なら日本、英語なら出さない")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = _parser()
    a = p.parse_args(argv)

    if a.brands:
        for b in BRANDS:
            name = b["name"] if a.lang == "ja" else b["name_en"]
            print("\t".join([b["id"], name, b["kind"], b["checked"] or ("未確認" if a.lang == "ja" else "unverified")]))
        return 0

    ledger = [s.strip() for s in a.ledger.split(",") if s.strip()]
    unknown = [s for s in ledger if s not in {b["id"] for b in BRANDS}]
    if unknown:
        p.error("会社の一覧にない id です：" + "、".join(unknown) + "（--brands で一覧を出せます）")
    if not ledger:
        print("（台帳が空です。取引している会社を --ledger で渡してください。--brands で一覧を出せます）" if a.lang == "ja" else
              "(Your ledger is empty. Pass the companies you use with --ledger. --brands lists them.)", file=sys.stderr)

    text = a.text
    if text is None:
        if sys.stdin.isatty():
            print("文面を貼り付けて、最後に Ctrl-D（Windows は Ctrl-Z のあと Enter）を押してください。" if a.lang == "ja" else
                  "Paste the message, then press Ctrl-D (on Windows, Ctrl-Z then Enter).", file=sys.stderr)
        text = sys.stdin.read()
    if not text.strip():
        p.error("文面が空です")

    v = judge(text, ledger, lang=a.lang, region=a.region)
    if a.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
        return 0
    L = LABELS[a.lang]
    colon = "：" if a.lang == "ja" else ": "
    print(f"{L[v['level']]}{colon}{v['head']}")
    for r in v["reasons"]:
        print(f"・{r['text']}（{r['code']}）" if a.lang == "ja" else f"- {r['text']} ({r['code']})")
    print(f"{L['todo']}{colon}{v['todo']}")
    for h in v["helplines"]:
        print(f"{L['help']}{colon}" + " ".join(x for x in (h["label"], h.get("tel"), h.get("url")) if x))
    return 0


if __name__ == "__main__":
    sys.exit(main())
