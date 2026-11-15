"""勘合の関所（せきしょ）— AI に渡す前の文書（.md など）に、隠れた命令や隠した文字が混ざっていないかを調べる。

  from kango.sekisho import check
  check(open("README.md", encoding="utf-8").read(), trusted_hosts=["github.com"])
  # -> {"level": "red" | "amber" | "none", "head": ..., "findings": [...], "sha256": ..., "approved": bool}

  python -m kango.sekisho 受け取った.md --trusted github.com

AI エージェントは、渡された文書の中の「指示らしい文」に従ってしまうことがあります（プロンプトインジェクション）。
関所は、AI に渡す前に、決まった規則だけで文書を調べ、見つけた場所（行と文字）を返します。

守る線（勘合と同じ）：AI を使わない（同じ入力には同じ答え）／「安全」と断定しない（何も見つからない時の答えは
"none"＝見つかりませんでした、で、青ではない）／文書を保存せず外へ送らない／リンク先へアクセスしない。
規則と、守れないことの説明は docs/sekisho.md。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterable, List, Optional

__all__ = ["check", "fingerprint", "RULES"]

# 目に見えない文字。表示されないので、人には読めず AI にだけ届く。
#   ゼロ幅の文字・向きを変える文字（文字の並びを見た目と変える）・タグ文字（英字を丸ごと隠せる）
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
# HTML で見えなくした所（display:none・visibility:hidden・文字の大きさ0・白い文字・hidden 属性）
_HIDDEN_STYLE = re.compile(
    r"<[a-z][^>]*(?:style\s*=\s*[\"'][^\"']*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])"
    r"|color\s*:\s*(?:#fff(?:fff)?\b|white\b))|\shidden(?:\s|>|=))[^>]*>",
    re.I)
_URL = re.compile(r"https?://[^\s<>\"'`)\]]+", re.I)
_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(https?://[^\s)]+)", re.I)
_BASE64 = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")

# 言いまわしの規則：(コード, 言いまわし, 何が問題か, どう確かめるか)
# 言いまわしは、文書の外（目に見える所）にあれば黄、隠した所（コメント・見えない HTML）にあれば赤にする。
RULES = [
    ("override",
     r"(?:ignore|disregard|forget)\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules?)"
     r"|(?:以前|前|これまで|上記|今まで)の(?:指示|命令|ルール|設定|プロンプト)を(?:すべて|全て)?(?:無視|忘れ|取り消)"
     r"|system\s*prompt|システムプロンプト|you\s+are\s+now\b|あなたは(?:今から|これから)"
     # スペイン語・フランス語・ドイツ語・ポルトガル語・中国語・韓国語
     r"|(?:ignora(?:r)?|olvida(?:r)?)\s+(?:todas\s+)?las\s+instrucciones(?:\s+(?:anteriores|previas))?"
     r"|(?:ignore[zr]?|oublie[zr]?)\s+(?:toutes\s+)?les\s+instructions(?:\s+(?:précédentes|antérieures))?"
     r"|(?:ignoriere?|vergiss)\s+(?:alle\s+)?(?:vorherigen\s+|bisherigen\s+|obigen\s+)?(?:anweisungen|befehle)"
     r"|(?:ignore|esqueça)\s+(?:todas\s+)?as\s+instruções(?:\s+(?:anteriores|prévias))?"
     r"|(?:忽略|无视|無視|忘记|忘記)(?:之前|以前|上面|上述|先前|所有)的?(?:所有)?(?:指示|指令|规则|規則|提示)|系统提示词|系統提示詞|你现在是|你現在是"
     r"|(?:이전|위|앞|지금까지)의?\s*(?:모든\s*)?(?:지시|명령|규칙|지침)(?:을|를|은|는)?\s*(?:무시|잊어)|시스템\s*프롬프트|(?:너는|당신은)\s*이제",
     "AI への指示を書きかえようとする言いまわしです。",
     "この文書が、AI の役割や指示を変える必要のある文書か確かめてください。そうでなければ AI に渡さないでください。"),
    ("conceal",
     r"(?:do\s+not|don'?t|never)\s+(?:tell|inform|mention\s+(?:this\s+)?to|reveal\s+(?:this\s+)?to)\s+the\s+user"
     r"|(?:ユーザー|利用者|人間|使用者)に(?:は)?(?:言わ|伝え|知らせ|見せ|教え)(?:ないで|るな|ず)|黙って(?:実行|送|行)"
     r"|no\s+(?:se\s+lo\s+|le\s+)?(?:digas|menciones|cuentes)\s+(?:nada\s+)?al\s+usuario"
     r"|ne\s+(?:le\s+|lui\s+)?(?:dis|dites)\s+(?:rien|pas)(?:\s+(?:de\s+)?(?:ça|cela|ceci))?\s+à\s+l.utilisateur|sans\s+(?:le\s+|rien\s+)?dire\s+à\s+l.utilisateur"
     r"|(?:sag|sage|erzähl|erwähne)\s+(?:es\s+|das\s+)?dem\s+(?:benutzer|nutzer|anwender)\s+nicht|ohne\s+(?:es\s+)?dem\s+(?:benutzer|nutzer)\s+zu\s+sagen"
     r"|não\s+(?:conte|diga|mencione)\s+(?:nada\s+)?ao\s+usuário"
     r"|不要(?:告诉|告訴|通知|让|讓)(?:用户|用戶|使用者)|(?:瞒着|瞞著)(?:用户|用戶)"
     r"|사용자(?:에게|한테)\s*(?:말하지|알리지|보여주지)\s*(?:마|말)",
     "人に隠して何かをさせようとする言いまわしです。",
     "隠す理由がある文書か確かめてください。AI が人に黙って動く指示は、ふつうの文書には入りません。"),
    ("exfiltrate",
     r"(?:send|upload|post|forward|email|exfiltrate)\s+(?:\w+\s+){0,4}(?:api\s*keys?|tokens?|passwords?|secrets?|credentials?|\.env|ssh\s+keys?|cookies?)"
     r"|(?:api\s*キー|apiキー|トークン|パスワード|秘密鍵|認証情報|\.env|クッキー)[^。\n]{0,20}(?:送|アップロード|転送|貼り付け|投稿)"
     r"|(?:envía|enviar|sube|subir|reenvía)\s+(?:\w+\s+){0,4}(?:claves?\s+(?:de\s+)?api|tokens?|contraseñas?|credenciales|secretos?)"
     r"|(?:envoie[zr]?|transmet(?:s|tez|tre)|télécharge[zr]?)\s+(?:\w+\s+){0,4}(?:clés?\s+(?:d.)?api|jetons?|tokens?|mots?\s+de\s+passe|identifiants|secrets?)"
     r"|(?:sende|schicke|lade)\s+(?:\w+\s+){0,4}(?:api-?schlüssel|tokens?|passw(?:ort|örter|orte?r)|zugangsdaten|geheimnisse)"
     r"|(?:envie|enviar|mande|carregue)\s+(?:\w+\s+){0,4}(?:chaves?\s+(?:de\s+)?api|tokens?|senhas?|credenciais|segredos?)"
     r"|(?:api\s*密钥|api\s*密鑰|令牌|密码|密碼|私钥|私鑰|凭证|憑證|\.env)[^。\n]{0,20}(?:发送|發送|上传|上傳|转发|轉發|发给|發給)"
     r"|(?:发送|發送|上传|上傳|转发|轉發)[^。\n]{0,10}(?:api\s*密钥|api\s*密鑰|令牌|密码|密碼|私钥|私鑰|凭证|憑證)"
     r"|(?:api\s*키|토큰|비밀번호|패스워드|개인\s*키|인증\s*정보|\.env)[^.\n]{0,20}(?:보내|전송|업로드)",
     "鍵やパスワードを外へ送らせようとする言いまわしです。",
     "鍵やパスワードを外へ送る必要は、まずありません。AI に渡さず、書いた人に確かめてください。"),
    ("command",
     r"(?:curl|wget)\s[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b|rm\s+-rf\s+[/~]|powershell[^\n]*-e(?:nc|ncodedcommand)?\s"
     r"|chmod\s+\+x[^\n]*&&",
     "ネットから取ってきたものを、そのまま動かす命令です。",
     "AI にこの命令を動かさせないでください。動かす必要があるなら、中身を人が読んでから人が動かしてください。"),
    # 解析役の AI に向けて「調べるな」「害は無い」と言わせる言いまわし。マルウェアの中に、AI の解析役を
    # 断らせたり「無害」と答えさせたりする文が埋め込まれた例が報告されている（2026-11 の報告を受けて足した）。
    ("deflect",
     r"(?:do\s+not|don'?t|never)\s+(?:analy[sz]e|scan|inspect|examine|investigate|report|flag|look\s+(?:at|into))\b"
     r"|(?:stop|refuse)\s+(?:to\s+)?(?:analy[sz](?:e|ing)|scann?(?:ing)?|inspect(?:ing)?)"
     r"|refuse\s+(?:\w+\s+){0,4}(?:due\s+to|because\s+of)\s+copyright"
     r"|copyright(?:ed)?\b[^.\n]{0,40}\b(?:refuse|cannot\s+(?:be\s+)?analy[sz]|must\s+not\s+(?:be\s+)?analy[sz])"
     r"|(?:this|the)\s+(?:file|code|program|sample|script|binary|document|executable)\s+is\s+"
     r"(?:completely\s+|totally\s+|perfectly\s+)?(?:harmless|benign|clean|not\s+malicious|not\s+(?:a\s+)?malware|safe(?=\s*[.!]|\s*$))"
     r"|(?:respond|reply|answer|report|classify)\s+(?:\w+\s+){0,3}(?:with|as)\s+[\"']?(?:no\s+malware\s+detected|benign|safe|clean|harmless)"
     r"|no\s+malware\s+detected"
     r"|(?:解析|分析|調査|スキャン|検査)(?:を|は)?(?:断|拒否|拒ん|しないで|するな|せず|やめ|中止)"
     r"|(?:調べ|解析し|分析し|スキャンし|検査し)(?:ないで|るな)"
     r"|著作権[^。\n]{0,30}(?:断|拒否|拒ん|解析できません|解析しないで|お答えできません)"
     r"|(?:この|本|当)(?:ファイル|プログラム|コード|文書|ソフト|サンプル)(?:は|には)[^。\n]{0,10}"
     r"(?:無害|危険(?:では|じゃ)(?:ない|ありません)|悪意(?:は|が)?(?:ない|ありません)|マルウェアでは(?:ない|ありません)|安全(?:です|だ|。|$))"
     r"|no\s+(?:lo\s+)?(?:analices|escanees|inspecciones)|este\s+(?:archivo|código|programa)\s+es\s+(?:completamente\s+|totalmente\s+)?(?:inofensivo|benigno)"
     r"|n.analyse[zr]?\s+pas|ne\s+(?:pas\s+)?analyser|ce\s+(?:fichier|code|programme)\s+est\s+(?:totalement\s+|complètement\s+)?(?:inoffensif|bénin)"
     r"|(?:analysiere|scanne|untersuche)\s+(?:diese\s+datei\s+|dies\s+|das\s+)?nicht|diese\s+(?:datei|software)\s+ist\s+(?:völlig\s+|komplett\s+)?(?:harmlos|gutartig)"
     r"|não\s+(?:analise|escaneie|inspecione)|este\s+(?:arquivo|código|programa)\s+é\s+(?:totalmente\s+|completamente\s+)?(?:inofensivo|benigno)"
     r"|不要(?:分析|扫描|掃描|检查|檢查)|(?:此|这个|這個|本)(?:文件|程序|程式|代码|代碼|檔案)(?:是)?(?:完全)?(?:无害|無害)的?"
     r"|분석하지\s*(?:마|말)|(?:이|본)\s*(?:파일|프로그램|코드)(?:은|는)\s*(?:완전히\s*)?무해",
     "AI の解析役に、調べるのをやめさせたり「無害」と答えさせたりする言いまわしです。",
     "文書が自分で「無害です」「調べないで」と言う理由は、ふつうありません。AI の答えをうのみにせず、人が中身を確かめてください。"),
]
_RULES = [(code, re.compile(pat, re.I), why, how) for code, pat, why, how in RULES]

# 英語の説明（check(..., lang="en")）。日本語はコードの中の文（RULES・_FIXED・_HEADS）。
_EN = {
    "override": ("Wording that tries to rewrite the AI's instructions.",
                 "Check whether this document really needs to change the AI's role or instructions. If not, don't give it to the AI."),
    "conceal": ("Wording that tries to make the AI do something without telling the person.",
                "Check whether there's a reason to hide anything. Ordinary documents don't tell an AI to act behind the person's back."),
    "exfiltrate": ("Wording that tries to send keys or passwords somewhere.",
                   "There's almost never a reason to send keys or passwords out. Don't give it to the AI; ask the author."),
    "command": ("A command that downloads something and runs it straight away.",
                "Don't let the AI run this. If it really needs to run, a person should read it first and run it themselves."),
    "deflect": ("Wording aimed at an AI analyzer, telling it to stop checking or to call the file harmless.",
                "A document has no ordinary reason to say \"this is harmless\" or \"don't analyze me\". Don't take the AI's answer at face value; have a person check it."),
    "invisible": ("There are invisible characters. People can't read them, but the AI can.",
                  "Remove the invisible characters before passing it on, or ask the author why they're there."),
    "hidden_html": ("Part of the HTML is hidden. It doesn't show on screen, but the AI reads it.",
                    "Open the source and have a person check what the hidden part says."),
    "comment": ("There's a comment (<!-- -->). It doesn't show on screen, but the AI reads it.",
                "Have a person read the comment. If it contains anything like instructions, don't pass the document on."),
    "image_beacon": ("An image address has extra text after \"?\". If the AI opens the image, that text reaches whoever runs the server.",
                     "Check that nothing secret or from the conversation could end up in the image address."),
    "outside_link": ("A link to an address that isn't on your trusted list.",
                     "Have a person check the address before letting the AI open the link."),
    "encoded": ("A long encoded-looking string (base64 or similar). Its content can't be read.",
                "Until a person has checked what it says, don't let anyone tell the AI to decode and run it."),
}
_HEADS = {
    "ja": {"red": "赤：隠れた指示か、隠した文字があります。AI に渡さないでください。",
           "amber": "黄：確かめてほしい所があります。人が読んでから渡してください。",
           "none": "見つかりませんでした（安全という意味ではありません）。"},
    "en": {"red": "Red: there are hidden instructions or hidden characters. Don't give this to the AI.",
           "amber": "Amber: some parts need checking. Have a person read it before passing it on.",
           "none": "Nothing found (this doesn't mean it's safe)."},
}

_FIXED = {
    "invisible": ("目に見えない文字が入っています。人には読めず、AI にだけ届きます。",
                  "見えない文字を消してから渡すか、書いた人に理由を確かめてください。"),
    "hidden_html": ("HTML で見えなくした所があります。画面には出ず、AI にだけ届きます。",
                    "見えない所に何が書かれているか、ソースを開いて人が確かめてください。"),
    "comment": ("コメント（<!-- -->）があります。画面には出ず、AI にだけ届きます。",
                "コメントの中身を人が読んでください。指示らしい文があれば渡さないでください。"),
    "image_beacon": ("画像の住所に、続きの文字（?〜）が付いています。AI が画像を開くと、その文字が相手に届きます。",
                     "画像の住所に、秘密や会話の中身が入るような書き方がないか確かめてください。"),
    "outside_link": ("信用する住所の一覧にない住所へのリンクです。",
                     "AI にこのリンクを開かせる前に、人が住所を確かめてください。"),
    "encoded": ("長い暗号のような文字の並び（base64 など）があります。中身が読めません。",
                "中身を人が確かめるまで、AI に「解いて実行して」と言わせないでください。"),
}


def fingerprint(text: str) -> str:
    """文書の指紋（sha256）。人が確かめた文書の指紋を控えておけば、同じ文書かを照らし合わせられる（割符）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _host(url: str) -> str:
    rest = url.split("://", 1)[-1]
    rest = re.split(r"[/?#\\]", rest, maxsplit=1)[0]
    rest = rest.rsplit("@", 1)[-1].split(":", 1)[0]
    return rest.lower().rstrip(".")


def _trusted(host: str, trusted: List[str]) -> bool:
    return any(host == t or host.endswith("." + t) for t in trusted)


def _joins(prev: str, ch: str) -> bool:
    """ch が、前の文字に付いて1つの文字になるもの（アクセントなどの付ける文字・ハングルの中声と終声の字母）か。"""
    o = ord(ch)
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Mc", "Me"):
        return True
    p = ord(prev)
    lead = 0x1100 <= p <= 0x115F or 0xA960 <= p <= 0xA97F
    vowel = 0x1160 <= p <= 0x11A7 or 0xD7B0 <= p <= 0xD7C6
    syllable = 0xAC00 <= p <= 0xD7A3
    if 0x1160 <= o <= 0x11A7 or 0xD7B0 <= o <= 0xD7C6:   # 中声
        return lead or vowel
    if 0x11A8 <= o <= 0x11FF or 0xD7CB <= o <= 0xD7FB:   # 終声
        return vowel or syllable or 0x11A8 <= p <= 0x11FF or 0xD7CB <= p <= 0xD7FB
    return False


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _quote(s: str) -> str:
    s = _INVISIBLE.sub(lambda m: "<U+%04X>" % ord(m.group()), s.strip())
    return s if len(s) <= 80 else s[:77] + "..."


def check(text: str, trusted_hosts: Optional[Iterable[str]] = None,
          approved: Optional[Iterable[str]] = None, lang: str = "ja") -> dict:
    """文書を調べる。

    言いまわしは、日本語・英語・スペイン語・フランス語・ドイツ語・ポルトガル語・中国語・韓国語で探す。
    lang: 答えの文（head・why・how）の言語（"ja" か "en"）。色とコードは言語で変わらない。

    trusted_hosts: 信用する住所（例 ["github.com"]）。渡すと、それ以外へのリンクを黄（outside_link）にする。
    approved: 人が前に確かめた文書の指紋（fingerprint の値）。同じなら approved=True を返す（答えの色は変えない）。
    """
    if lang not in _HEADS:
        raise ValueError(f"lang は ja か en です：{lang!r}")
    findings: List[dict] = []

    def add(code, sev, pos, quote, why=None, how=None):
        w, h = _EN[code] if lang == "en" else (why, how) if why else _FIXED[code]
        findings.append({"code": code, "sev": sev, "line": _line_of(text, pos), "quote": _quote(quote),
                         "why": w, "how": h})

    for m in _INVISIBLE.finditer(text):
        if m.group() == "﻿" and m.start() == 0:
            continue  # 文書の先頭の BOM は、ふつうに付くもの
        add("invisible", "red", m.start(), text[max(0, m.start() - 10):m.end() + 10])

    # 隠した所（コメント・見えない HTML）の範囲。言いまわしがここにあれば赤。
    hidden = []
    for m in _COMMENT.finditer(text):
        hidden.append((m.start(), m.end()))
        add("comment", "amber", m.start(), m.group())
    for m in _HIDDEN_STYLE.finditer(text):
        close = text.find("</", m.end())
        end = close if close != -1 else min(len(text), m.end() + 400)
        hidden.append((m.start(), end))
        add("hidden_html", "red", m.start(), text[m.start():end])

    # 言いまわしは、見えない文字を抜いて、全角と半角をそろえてから読む（「無​視」のような分け書きを防ぐ）。
    # 抜いた文字の数だけ位置がずれるので、元の位置への対応表を持つ。
    # アクセントを後から付ける書き方（e + ́）や、ハングルを字母（ᄋ+ᅵ+ᆫ…）で組む書き方は、見た目が同じでも
    # 1文字ずつでは別の文字になる。もとの文字と、続く「付ける文字」をひとまとめにしてから NFKC にする。
    kept = [i for i, ch in enumerate(text) if not _INVISIBLE.match(ch)]
    groups: List[List[int]] = []
    for i in kept:
        if groups and _joins(text[groups[-1][-1]], text[i]):
            groups[-1].append(i)
        else:
            groups.append([i])
    plain_parts, where = [], []
    for g in groups:
        s = unicodedata.normalize("NFKC", "".join(text[i] for i in g))
        plain_parts.append(s)
        where.extend([g[0]] * len(s))
    plain = "".join(plain_parts)
    kept = where
    for code, rx, why, how in _RULES:
        for m in rx.finditer(plain):
            pos = kept[m.start()]
            sev = "red" if any(a <= pos < b for a, b in hidden) else "amber"
            add(code, sev, pos, m.group(), why, how)

    for m in _IMAGE.finditer(text):
        if "?" in m.group(1) and not _trusted(_host(m.group(1)), list(trusted_hosts or [])):
            add("image_beacon", "amber", m.start(1), m.group(1))
    if trusted_hosts is not None:
        trusted = [t.lower().strip(".") for t in trusted_hosts if t.strip()]
        for m in _URL.finditer(text):
            if not _trusted(_host(m.group()), trusted):
                add("outside_link", "amber", m.start(), m.group())
    for m in _BASE64.finditer(text):
        add("encoded", "amber", m.start(), m.group())

    findings.sort(key=lambda f: (f["line"], f["code"]))
    level = "red" if any(f["sev"] == "red" for f in findings) else "amber" if findings else "none"
    head = _HEADS[lang][level]
    fp = fingerprint(text)
    return {"level": level, "head": head, "findings": findings, "sha256": fp,
            "approved": fp in set(approved or [])}


# 画面に出す文（python -m kango.sekisho）。--lang en の時は英語だけにする。
_CLI = {
    "ja": {"disclaimer": "決まった規則で見つけた候補です。何も見つからなくても安全とは限りません。最後は人が確かめてください。",
           "approved": "・人が前に確かめた文書と同じです（指紋が一致）。",
           "line": "・%d行目 %s（%s）%s", "quote": "    「%s」", "red": "赤", "amber": "黄"},
    "en": {"disclaimer": "These are candidates found by fixed rules. Finding nothing doesn't mean it's safe. A person should make the final check.",
           "approved": "- Same as a document a person checked before (fingerprint matches).",
           "line": "- Line %d %s (%s) %s", "quote": "    \"%s\"", "red": "Red", "amber": "Amber"},
}


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    import sys

    p = argparse.ArgumentParser(prog="python -m kango.sekisho",
                                description="AI に渡す前の文書を、決まった規則だけで調べます。"
                                            "AI を使わず、文書を保存せず、リンク先へもアクセスしません。")
    p.add_argument("file", nargs="?", help="調べる文書（省くと標準入力から読みます）")
    p.add_argument("--trusted", default=None, metavar="HOST,HOST",
                   help="信用する住所をカンマ区切りで（例：github.com）。それ以外へのリンクを黄にします")
    p.add_argument("--approved", default=None, metavar="FILE",
                   help="人が確かめた文書の指紋（sha256）を1行に1つ書いたファイル")
    p.add_argument("--json", action="store_true", help="答えを JSON で出す")
    p.add_argument("--lang", default="ja", choices=sorted(_HEADS), help="答えの文の言語（ja か en）")
    p.add_argument("--findings", action="store_true",
                   help="答えを akaire-findings/v1 の形の JSON で出す（アカイレなどの表示に渡せます）")
    a = p.parse_args(argv)

    if a.file:
        with open(a.file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    trusted = None if a.trusted is None else [s.strip() for s in a.trusted.split(",") if s.strip()]
    approved = None
    if a.approved:
        with open(a.approved, encoding="utf-8") as f:
            approved = [s.split()[0] for s in f if s.strip() and not s.startswith("#")]
    r = check(text, trusted_hosts=trusted, approved=approved, lang=a.lang)

    if a.findings:
        src = a.file or "stdin"
        sev = {"red": "red", "amber": "orange"}
        out = {"schema": "akaire-findings/v1", "tool": "kango-sekisho", "sources": [src],
               "disclaimer": _CLI[a.lang]["disclaimer"],
               "findings": [{"tool": "kango-sekisho", "src": "%s L%d" % (src, f["line"]),
                             "loc": {"line": f["line"], "quote": f["quote"]}, "sev": sev[f["sev"]],
                             "label": f["code"], "why": f["why"], "how": f["how"], "source": ""}
                            for f in r["findings"]]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(r["head"])
        if r["approved"]:
            print(_CLI[a.lang]["approved"])
        for f in r["findings"]:
            print(_CLI[a.lang]["line"] % (f["line"], _CLI[a.lang][f["sev"]], f["code"], f["why"]))
            print(_CLI[a.lang]["quote"] % f["quote"])
            print("    → %s" % f["how"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
