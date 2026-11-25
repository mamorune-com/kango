"""勘合（kango）— 届いた連絡を「自分の契約台帳」と「会社の公式ドメイン」の2つの割符で照合する。

  from kango import judge
  judge("【楽天カード】ご請求額が確定しました https://www.rakuten-card.co.jp/", ledger=["rakuten"])
  # -> {"level": "green" | "amber" | "red", "head": ..., "reasons": [...], ...}
  judge("Your PayPal account is limited https://paypal-verify.example/", ledger=[], lang="en", region="US")
  # 答えの文を英語に、相談先を米国の窓口に（既定は日本語・日本の窓口）

守る線：AIを使わない（決定的な照合だけ）／「本物」「安全」と断定しない／文面を保存しない・送らない／
リンク先へアクセスしない。規則の説明は リポジトリの SPEC.md。
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional

__all__ = ["judge", "marks", "load_brands", "BRANDS", "LANGUAGES", "REGIONS", "host_of", "is_official", "mimicked_brand"]


def _split(v: str) -> List[str]:
    return [s.strip() for s in (v or "").split("|") if s.strip()]


def load_brands(path: Optional[Path] = None) -> List[dict]:
    path = path or Path(__file__).with_name("brands.csv")
    with open(path, encoding="utf-8") as f:
        return [{"id": r["id"], "name": r["name"], "kind": r["kind"],
                 "words": _split(r["words"]), "domains": _split(r["domains"]),
                 "stems": _split(r["stems"]), "checked": r.get("checked") or None,
                 "name_en": r.get("name_en") or r["name"]}
                for r in csv.DictReader(f)]


BRANDS = load_brands()

# 答えの文・言いまわしの一覧・相談先（正は data/phrases.json。scripts/sync_brands.py で写す）
PHRASES = json.loads(Path(__file__).with_name("phrases.json").read_text(encoding="utf-8"))
LANGUAGES = tuple(PHRASES["languages"])          # 答えの文の言語（"ja" と "en"）
REGIONS = tuple(PHRASES["helplines"])            # 相談先を出せる国・地域（JP・US・GB・AU）

SHORTENERS = ("bit.ly", "t.co", "tinyurl.com", "is.gd", "x.gd", "t.ly", "cutt.ly", "ow.ly", "rebrand.ly")
# 詐欺によくある言いまわし（言葉ひとつでは赤にしない＝黄まで）。日本語・英語ほか主要な言語の言葉を、理由ごとにまとめてある。
# 照合は正規化した文面（NFKC・小文字・目に見えない文字を除く）に、そのまま含まれるかで行う。
_PRESSURE = tuple((p["words"], p) for p in PHRASES["pressure"])
# 乗っ取りの入口によくある頼みごと（顔認証・指紋・パスキーそのものではなく、本人に操作させる手口）。
# 言葉だけでは赤にしない＝黄まで。照合は正規化した文面（NFKC・小文字）に対して行う。
# 「.」は改行にも当てる（頼みごとの途中で行を変えて照合を外す手口があるため）
_TAKEOVER = tuple((tuple(re.compile(x, re.S) for x in t["patterns"]), t) for t in PHRASES["takeover"])
# 以前の形（言葉・日本語の理由）。外から読む人のために残す。
PRESSURE = tuple((w, p["ja"]) for p in PHRASES["pressure"] for w in p["words"])
TAKEOVER = tuple((x, t["ja"]) for t in PHRASES["takeover"] for x in t["patterns"])
# 大文字と小文字を区別しない照合（re.I）は、ASCII の中だけで行う（re.A）。付けないと Python だけが ı（U+0131）を i とみなし、答えが食い違う。
# リンクが終わる文字＝空白と制御文字・かぎかっこ・山かっこ（<> 〈〉 《》）・亀甲かっこ・引用符・閉じかっこ・読点「、」。
# 空白は \s と書かない（何を空白とみなすかが言語ごとに違い、答えが食い違うため）。
_END = r"\x00-\x20\x7f-\x9f\u1680「」『』【】〈〉《》〔〕<>\"'）)、"
# リンク＝ http: か https: のあとに / か \ が続く文字の並び（ブラウザは \ も / とみなし、/ が1つでも開く）。
_URL = re.compile(r"https?:[/\\]+[^" + _END + r"]+", re.I | re.A)
# リンクの中に入っている、もう1つのリンクの始まり（https://本物/・https://偽物/ や ?url=https://… など）
_INNER = re.compile(r"https?:[/\\]", re.I | re.A)
# リンクの「住所の部分」（最初の / \ ? # まで）
_AUTH = re.compile(r"https?:[/\\]+([^/\\?#]*)", re.I | re.A)
# 見た目の「住所の部分」（\ を区切りと思わずに読んだ時。ここに @ や \ があれば見せかけ）
_SHOWN = re.compile(r"https?:[/\\]+([^/?#]*)", re.I | re.A)
# https:// の無いリンク（rakuten-card-login.com/abc など。メッセージアプリはこれも押せるリンクにする）。
# 英数字とハイフンの並びを . でつなぎ、最後が英字2〜24文字。前後に英数字や @ が付くもの（メールアドレスなど）は数えない。
_BARE = re.compile(r"(?<![a-z0-9@._%+\-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![a-z0-9\-@])"
                   r"(?:[/?#][^" + _END + r"]*)?", re.I | re.A)
# ファイル名（meisai.pdf など）は住所として数えない（どれもトップレベルドメインではない）
_FILE_EXT = frozenset("pdf html htm jpg jpeg png gif txt csv doc docx xls xlsx ppt pptx js css json xml php exe apk".split())
# 住所にふつう使う文字（英小文字・数字・. ・-）。これ以外を含む住所＝見た目を似せる手口か、壊れた住所
_HOST_OK = re.compile(r"[a-z0-9.\-]+")
# 電話番号＝次のどれか。前後に数字が続くもの（注文番号など）は数えない。番号が本物かは確かめられない＝黄まで。
# ・0（または +81）で始まり、区切り（空白＝スペース・タブ・改行・U+1680、かっこ・ハイフン類・「.」「・」＝数字の間に3文字まで）を除いて
#   10〜11桁（+81 の時は9〜10桁）。2桁目が 0 の番号（0077 など）も数える。英国・フランス・ドイツなどの国内の書き方もこれに当たる。
# ・+ と国番号で始まる国際的な書き方（+81 以外）。区切りを除いて 8〜15桁。
# ・オーストラリアの全国共通の番号（1300・1800 で始まる10桁＝区切りは上と同じ。13 で始まる6桁＝「13 22 21」「131 450」のように空白で区切ったもの）。
# ・北米の書き方（(800) 555-0199・800-555-0199・1-800-555-0199・800—555—0199）。3桁・3桁・4桁を区切り（空白・「.」・ハイフン類）でつなぐ（区切りの無い10桁は数えない）。
_SEP = r"[ \t\n\u1680()\-‐−–—―ー.・]{0,3}"
_PHONE = re.compile(r"(?<![0-9])(?:(?:\+81|0)" + _SEP + r"[0-9](?:" + _SEP + r"[0-9]){8,9}"
                    r"|\+(?!81)[1-9](?:" + _SEP + r"[0-9]){7,14}"
                    r"|1[38]00(?:" + _SEP + r"[0-9]){6}|13 [0-9]{2} [0-9]{2}|13[1-9] [0-9]{3}"
                    r"|(?:1[ .\-‐−–—―])?(?:\([2-9][0-9]{2}\) ?|[2-9][0-9]{2}[ .\-‐−–—―])[2-9][0-9]{2}[ .\-‐−–—―][0-9]{4})(?![0-9])")
# 改行のなかま（CR・垂直タブ・改ページ・U+001C〜001F・U+0085・行と段落の区切り）。LF にそろえる
# （「.」や空白が何に当たるかが言語ごとに違い、答えが食い違うため）。
_BREAKS = re.compile("[\r\x0b\x0c\x1c-\x1f\x85\u2028\u2029]")
# 目に見えない文字（ゼロ幅の空白・異体字セレクタ・向きを変える印など）。言葉や番号の間にはさんで照合を外す手口に使われる。
# Unicode の版で変わらないよう、範囲を書き並べる（SPEC.md と Swift の invisible と同じ）。
_INVISIBLE = re.compile("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e"
                        "\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0"
                        "\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]")
# 見た目が似た文字（amaz0n・rakuten → rakut3n 等）を戻してから似せた住所を探す
_LOOKALIKE = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "4": "a"})

# 日本語の見出し・次にすること・相談先（以前の形。外から読む人のために残す）
HEADS = PHRASES["heads"]["ja"]
TODO = PHRASES["todo"]["ja"]


def _helplines(lang: str, region: Optional[str]) -> List[dict]:
    """国・地域ごとの相談先。region を省くと、日本語なら日本の窓口、英語なら出さない（どこの国の人か分からないため）。"""
    if region is None:
        region = "JP" if lang == "ja" else ""
    out = []
    for h in PHRASES["helplines"].get(region.upper(), []):
        d = {"label": h[lang]}
        d.update({k: h[k] for k in ("tel", "url") if k in h})
        out.append(d)
    return out


HELPLINES = _helplines("ja", "JP")


def _t(lang: str, key: str, **kw: str) -> str:
    s = PHRASES["messages"][lang][key]
    for k, v in kw.items():
        s = s.replace("{" + k + "}", v)
    return s


def _name(b: dict, lang: str) -> str:
    return b["name"] if lang == "ja" else b.get("name_en") or b["name"]


_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


def _has(hay: str, w: str) -> bool:
    """hay に w が含まれるか。w の先頭の「[」＝その前が英数字でないこと、末尾の「]」＝その後ろが英数字でないこと
    （"[ups]" は groups の中の ups に当たらない・"[chase card" は purchase card に当たらない）。"""
    left = w.startswith("[")
    right = w.endswith("]") and len(w) > 1
    core = w[1 if left else 0:len(w) - 1 if right else len(w)]
    if not (left or right):
        return core in hay
    i = hay.find(core)
    while i != -1:
        j = i + len(core)
        if (not left or i == 0 or hay[i - 1] not in _ALNUM) and (not right or j == len(hay) or hay[j] not in _ALNUM):
            return True
        i = hay.find(core, i + 1)
    return False


def _prep(s: str) -> str:
    """NFKC にして、改行のなかまを LF にそろえる（リンクを探す時の文面）。"""
    return _BREAKS.sub("\n", unicodedata.normalize("NFKC", s or ""))


def _bare_text(s: str) -> str:
    """目に見えない文字を取りのぞく（言葉や電話番号を探す時の文面）。取りのぞいてから、もう一度 NFKC にする。"""
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", _INVISIBLE.sub("", s)))


def _norm(s: str) -> str:
    return _bare_text(_prep(s)).lower()


def _heading(low: str) -> str:
    """正規化した文面の先頭（空白・タブ・改行を除く）が「【」なら、最初の「】」までの見出し（【】を含む）。無ければ ""。"""
    t = low.lstrip(" \t\n")
    if not t.startswith("\u3010"):
        return ""
    k = t.find("\u3011")
    return t[:k + 1] if k > 0 else ""


def host_of(url: str) -> Optional[str]:
    """リンクの本当の行き先の住所（ホスト名）。ブラウザと同じ読み方をする：
    \\ は / と同じ・@ より前（利用者名とパスワード）は住所ではない・: の後ろは番号（ポート）・「。」は「.」と同じ。"""
    m = _AUTH.match(url)
    if not m:
        return None
    h = m.group(1).rsplit("@", 1)[-1]
    h = h.split("]", 1)[0] + "]" if h.startswith("[") else h.split(":", 1)[0]
    h = h.replace("。", ".").lower().rstrip(".")
    return h or None


def _scan(text: str):
    """文面を、リンク・https:// の無いリンクの住所・それ以外の文字（電話番号を探す所）に分ける。"""
    t = _prep(text)
    urls = []
    for u in _URL.findall(t):
        urls.append(u)
        # リンクの中に、もう1つリンクが入っていれば、それも数える（前のリンクに続けて書いて隠す手口）
        urls.extend(u[m.start():] for m in _INNER.finditer(u) if m.start() > 0)
    rest = _URL.sub(" ", t)

    def is_file(m) -> bool:
        return m.group(1).rsplit(".", 1)[-1].lower() in _FILE_EXT

    bare = [m.group(1).lower() for m in _BARE.finditer(rest) if not is_file(m)]
    # ファイル名はリンクではないので、文面に残す（090-1234-5678.pdf のように番号を隠す手口）
    plain = _BARE.sub(lambda m: m.group(0) if is_file(m) else " ", rest)
    return urls, bare, _bare_text(plain)


def is_official(host: str, brand: dict) -> bool:
    return any(host == d or host.endswith("." + d) for d in brand["domains"])


def mimicked_brand(host: str, brands: Iterable[dict]) -> Optional[dict]:
    """公式でない住所に、会社の名前（似せた文字も含む）が入っていれば その会社。"""
    plain = host.translate(_LOOKALIKE)
    for b in brands:
        if is_official(host, b):
            continue
        if any(_has(host, st) or _has(plain, st) for st in b["stems"]):
            return b
    return None


def _check_lang(lang: str) -> None:
    if lang not in LANGUAGES:
        raise ValueError(f"lang は {', '.join(LANGUAGES)} のどれかです：{lang!r}")


def judge(text: str, ledger: Iterable[str], brands: Optional[List[dict]] = None,
          lang: str = "ja", region: Optional[str] = None) -> dict:
    """勘合の判定（決定的・純粋）。level は green / amber / red。

    lang＝答えの文（head・reasons の text・todo・相談先の名前）の言語（"ja" か "en"）。色と理由のコードは言語で変わらない。
    region＝相談先を出す国・地域（"JP"・"US"・"GB"・"AU"）。省くと、日本語なら日本、英語なら出さない。"""
    _check_lang(lang)
    return _judge(text, ledger, brands, lang, region)[0]


def _judge(text: str, ledger: Iterable[str], brands: Optional[List[dict]] = None,
           lang: str = "ja", region: Optional[str] = None):
    """判定と、理由ごとの「何についての理由か」（行に印を付ける marks が使う。judge の答えには出さない）。"""
    brands = BRANDS if brands is None else brands
    owned = set(ledger or ())
    low = _norm(text)
    claimed = [b for b in brands if any(_has(low, _norm(w)) for w in b["words"])]
    # 文面が【】の見出しで始まり、見出しの中で会社を名乗っていれば、名乗った会社は見出しの会社だけ
    # （本文に別の会社名がただ出てくるだけ＝「Apple Pay に登録」など、を名乗りとみなさない）
    head = _heading(low)
    if head:
        named = [b for b in claimed if any(_has(head, _norm(w)) for w in b["words"])]
        if named:
            claimed = named
    urls, bare, plain = _scan(text)
    hosts = [h for h in (host_of(u) for u in urls) if h] + bare
    reasons: List[dict] = []
    detail: List[tuple] = []   # (code, level, target)
    rank = 0   # 0 green / 1 amber / 2 red

    def say(code: str, msg: str, level: int, target: Optional[str] = None) -> None:
        nonlocal rank
        reasons.append({"code": code, "text": msg})
        detail.append((code, level, target))
        rank = max(rank, level)

    if not claimed:
        say("no_claim", _t(lang, "no_claim"), 1)
    for b in claimed:
        if b["kind"] == "contract" and b["id"] not in owned:
            say("not_in_ledger", _t(lang, "not_in_ledger", name=_name(b, lang)), 2, b["id"])
        elif b["kind"] == "contract":
            say("in_ledger", _t(lang, "in_ledger", name=_name(b, lang)), 0, b["id"])

    # 「@」や「\」で本当の行き先をごまかす書き方（https://本物の住所@偽の住所/・https://偽の住所\@本物の住所/）
    # 行き先が空で読み取れないもの（https://本物の住所@/）も、見せかけとして数える（行き先は "" で表す）
    tricked = [host_of(u) or "" for u in urls if any(c in _SHOWN.match(u).group(1) for c in "@\\")]
    for h in dict.fromkeys(tricked):
        if h:
            say("disguised", _t(lang, "disguised", host=h), 2, h)
        else:
            say("disguised", _t(lang, "disguised_unreadable"), 2)

    for h in dict.fromkeys(hosts):   # 同じ住所は1回だけ
        if h in SHORTENERS:
            say("shortener", _t(lang, "shortener", host=h), 1, h)
            continue
        if h.startswith("xn--") or ".xn--" in h or not _HOST_OK.fullmatch(h):
            say("idn", _t(lang, "idn", host=h), 2, h)
            continue
        owner = next((b for b in brands if is_official(h, b)), None)
        if claimed and not any(is_official(h, b) for b in claimed):
            look = mimicked_brand(h, claimed)
            if look:
                say("mimic", _t(lang, "mimic", host=h, name=_name(look, lang)), 2, h)
            else:
                say("off_domain", _t(lang, "off_domain", host=h), 2, h)
        elif owner:
            say("official", _t(lang, "official", host=h, name=_name(owner, lang)), 0, h)
        else:
            look = mimicked_brand(h, brands)
            if look:
                say("mimic", _t(lang, "mimic", host=h, name=_name(look, lang)), 2, h)
            else:
                say("unknown_domain", _t(lang, "unknown_domain", host=h), 1, h)

    # リンク（https:// の無いものも）の中の数字は数えない（住所はリンクとして照合済み）
    if _PHONE.search(plain):
        say("phone", _t(lang, "phone"), 1)

    sep = PHRASES["messages"][lang]["list_sep"]
    tricks = [p[lang] for words, p in _PRESSURE if any(w in low for w in words)]
    if tricks:
        say("pressure", _t(lang, "pressure", list=sep.join(dict.fromkeys(tricks))), 1)

    asks = [t[lang] for pats, t in _TAKEOVER if any(x.search(low) for x in pats)]
    if asks:
        say("takeover", _t(lang, "takeover", list=sep.join(dict.fromkeys(asks))), 1)

    # 何ひとつ照らし合わせられなかった（配送・郵便・国税庁を名乗り、リンクが無い等）＝青にしない。
    # 青は、何か1つでも割符が合った時（in_ledger・official）だけ。
    if not reasons:
        say("nothing_to_check", _t(lang, "nothing_to_check"), 1)

    level = ("green", "amber", "red")[rank]
    return ({"level": level, "head": PHRASES["heads"][lang][level], "reasons": reasons, "todo": PHRASES["todo"][lang][level],
             "helplines": _helplines(lang, region) if level != "green" else [],
             "claimed": [b["id"] for b in claimed], "hosts": list(dict.fromkeys(hosts))}, detail)


# 行の印の短い説明（製品や言語ごとに言い回しを変えてよい。共通の見本では比べない）
MARK_LABELS = PHRASES["mark_labels"]["ja"]
_HOST_CODES = frozenset({"disguised", "idn", "mimic", "off_domain", "shortener", "unknown_domain"})


def marks(lines: Iterable[str], ledger: Iterable[str], brands: Optional[List[dict]] = None,
          lang: str = "ja") -> List[dict]:
    """文面の「どの行が」引っかかったか（画面写真に枠を付ける・文面に印を付けるため）。

    lines は文面を行に分けたもの（画面写真から読んだ1行ずつ など）。判定は行を改行でつないだ文面で行い、
    その赤と黄の理由を、理由のもとになった行に割り当てる。答え（色・理由）は judge と同じで、変えない。
    青の理由（割符が合った所）には印を付けない＝「印の無い所は安全」と読ませないため。
    返すのは [{"line": 行の番号, "level": "red" | "amber", "codes": [...], "labels": [...]}]（印のある行だけ、行の順）。
    lang＝labels の言語（"ja" か "en"）。"""
    _check_lang(lang)
    brands = BRANDS if brands is None else brands
    lines = list(lines)
    _, detail = _judge("\n".join(lines), ledger, brands)
    out: List[dict] = []
    for i, line in enumerate(lines):
        low = _norm(line)
        urls, bare, plain = _scan(line)
        hosts = set(h for h in (host_of(u) for u in urls) if h) | set(bare)
        rank, codes, labels = 0, [], []
        for code, level, target in detail:
            if level == 0 or code in codes:
                continue
            if code == "not_in_ledger":
                b = next((b for b in brands if b["id"] == target), None)
                hit = b is not None and any(_has(low, _norm(w)) for w in b["words"])
            elif code in _HOST_CODES:
                hit = target in hosts
            elif code == "phone":
                hit = bool(_PHONE.search(plain))
            elif code == "pressure":
                hit = any(w in low for words, _ in _PRESSURE for w in words)
            elif code == "takeover":
                hit = any(x.search(low) for pats, _ in _TAKEOVER for x in pats)
            else:
                hit = False
            if hit:
                rank = max(rank, level)
                codes.append(code)
                labels.append(PHRASES["mark_labels"][lang][code])
        if codes:
            out.append({"line": i, "level": ("green", "amber", "red")[rank], "codes": codes, "labels": labels})
    return out
