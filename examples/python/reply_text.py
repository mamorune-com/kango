"""LINE ボットなどで、判定の結果を返信の文章にする例（docs/integration.md）。

- 色だけに頼らない（「青」「黄」「赤」を文字でも書く）。
- 青を「安全」「本物」と言い換えない。
- 届いた文面は保存しない・ログに出さない。

動かして確かめる：python examples/python/reply_text.py
"""
from typing import Iterable

from kango import judge

LABEL = {"green": "青", "amber": "黄", "red": "赤"}


def reply_for(text: str, ledger: Iterable[str]) -> str:
    v = judge(text, list(ledger))
    lines = [f"【{LABEL[v['level']]}】{v['head']}"]
    lines += ["・" + r["text"] for r in v["reasons"]]
    lines.append(v["todo"])
    lines += [f"{h['label']}：{h.get('tel') or h.get('url')}" for h in v["helplines"]]
    return "\n".join(lines)


if __name__ == "__main__":
    out = reply_for("【Amazon】お支払い情報を更新してください https://amazon-co-jp.account-verify.top/login", ["amazon"])
    assert out.startswith("【赤】割符が合いません") and "#9110" in out and "188" in out
    out = reply_for("【楽天カード】ご請求額が確定しました https://www.rakuten-card.co.jp/", ["rakuten"])
    assert out.startswith("【青】割符が合いました") and "安全" not in out and "本物" not in out
    print(out)
    print("ok")
