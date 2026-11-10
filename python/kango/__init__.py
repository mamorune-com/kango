"""勘合（kango）— 届いた連絡を「自分の契約台帳」と「会社の公式ドメイン」の2つの割符で照合する。

  from kango import judge
  judge("【楽天カード】ご請求額が確定しました https://www.rakuten-card.co.jp/", ledger=["rakuten"])
  # -> {"level": "green" | "amber" | "red", "head": ..., "reasons": [...], ...}

守る線：AIを使わない（決定的な照合だけ）／「本物」「安全」と断定しない／文面を保存しない・送らない／
リンク先へアクセスしない。規則の説明は リポジトリの SPEC.md。
"""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional

__all__ = ["judge", "marks", "load_brands", "BRANDS", "host_of", "is_official", "mimicked_brand"]


def _split(v: str) -> List[str]:
    return [s.strip() for s in (v or "").split("|") if s.strip()]


def load_brands(path: Optional[Path] = None) -> List[dict]:
    path = path or Path(__file__).with_name("brands.csv")
    with open(path, encoding="utf-8") as f:
        return [{"id": r["id"], "name": r["name"], "kind": r["kind"],
                 "words": _split(r["words"]), "domains": _split(r["domains"]),
                 "stems": _split(r["stems"]), "checked": r.get("checked") or None}
                for r in csv.DictReader(f)]


BRANDS = load_brands()

SHORTENERS = ("bit.ly", "t.co", "tinyurl.com", "is.gd", "x.gd", "t.ly", "cutt.ly", "ow.ly", "rebrand.ly")
# 詐欺によくある言いまわし（言葉ひとつでは赤にしない＝黄まで）
PRESSURE = (
    ("停止", "アカウントの停止で急がせる"), ("凍結", "凍結をちらつかせる"),
    ("24時間以内", "期限で急がせる"), ("本日中", "期限で急がせる"),
    ("支払い情報", "支払い情報を入力させようとする"), ("お支払い方法", "支払い方法を更新させようとする"),
    ("カード情報", "カード情報を求める"), ("暗証番号", "暗証番号を求める（正規の会社は聞きません）"),
    ("パスワード", "パスワードの入力を求める"), ("ギフトカード", "ギフトカードでの支払いを求める"),
    ("未納", "未納を理由に払わせる"), ("不在", "不在通知を装う"),
    ("ご本人確認", "本人確認を名目に入力させる"), ("異常なログイン", "不正ログインで不安をあおる"),
)
# 乗っ取りの入口によくある頼みごと（顔認証・指紋・パスキーそのものではなく、本人に操作させる手口）。
# 言葉だけでは赤にしない＝黄まで。照合は正規化した文面（NFKC・小文字）に対して行う。
TAKEOVER = (
    (r"(パスキー|顔認証|指紋認証|生体認証).{0,6}(再登録|再設定|作り直|登録し直|設定し直|登録をし直|設定をし直)",
     "パスキーや顔認証を作り直させようとする"),
    (r"(自撮り|セルフィー|顔写真(?!付)|顔の(写真|画像|動画)).{0,30}(身分証|免許証|マイナンバーカード|パスポート|在留カード|送信|送って|送付|アップロード)",
     "顔写真や身分証を送らせようとする"),
    (r"(身分証|免許証|マイナンバーカード|パスポート|在留カード).{0,30}(自撮り|セルフィー|顔写真(?!付)|顔の(写真|画像|動画))",
     "顔写真や身分証を送らせようとする"),
    (r"(アカウント|ログイン).{0,6}(復旧|復元|ロック解除|ロックを解除|制限解除|制限を解除)",
     "アカウントの復旧を名目に操作させる"),
    (r"(確認コード|認証コード|認証番号|ワンタイムパスワード|セキュリティコード|qrコード|二次元コード|[0-9]桁の(番号|コード|数字)).{0,20}(教えて|伝えて|読み上げて|お知らせください|返信して|読み取って|読みとって|スキャンして)",
     "確認コードやQRコードを渡させようとする"),
    (r"(遠隔操作|リモート操作|リモートサポート|画面共有|画面を共有|anydesk|teamviewer|quick ?support|クイックサポート|airdroid)",
     "遠隔操作や画面共有をさせようとする"),
    # 偽の面接・偽の会議アプリ・コマンドの貼り付け（開発者や会社員の PC を乗っ取る入口）。
    (r"(課題|選考|面接|コーディングテスト|技術テスト|リポジトリ|github).{0,40}(実行して|動かして|起動して|セットアップして|ビルドして|クローンして|git clone|npm |yarn |pnpm |pip install)",
     "面接の課題などを口実に、渡したコードを動かさせようとする"),
    (r"(面接|会議|ミーティング|通話|面談|打ち合わせ|ウェビナー).{0,40}(アプリ|ソフト|ツール|プラグイン|拡張機能|ドライバ|コーデック).{0,20}(インストール|ダウンロード|入れて|更新して|アップデートして)",
     "会議や面接のためと言って、アプリや部品を入れさせようとする"),
    (r"(ターミナル|コマンドプロンプト|powershell|ファイル名を指定して実行).{0,40}(貼り付け|貼りつけ|ペースト|入力して|実行して|打って)|curl [^\n]{0,100}\|\s*(sh|bash|zsh)",
     "コマンドを貼り付けて実行させようとする"),
)
# 「.」は改行にも当てる（頼みごとの途中で行を変えて照合を外す手口があるため）
_TAKEOVER = tuple((re.compile(p, re.S), r) for p, r in TAKEOVER)
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
# 電話番号＝0（または +81）で始まり、区切り（空白＝スペース・タブ・改行・U+1680、かっこ・ハイフン類・「.」「・」＝数字の間に3文字まで）を除いて
# 10〜11桁（+81 の時は9〜10桁）。2桁目が 0 の番号（0077 など）も数える。
# 前後に数字が続くもの（注文番号など）は数えない。番号が本物かは確かめられない＝黄まで。
_SEP = r"[ \t\n\u1680()\-‐−–—―ー.・]{0,3}"
_PHONE = re.compile(r"(?<![0-9])(?:\+81|0)" + _SEP + r"[0-9](?:" + _SEP + r"[0-9]){8,9}(?![0-9])")
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

HEADS = {"green": "割符が合いました", "amber": "確かめきれません",
         "red": "割符が合いません。偽物の疑いが強いです"}
TODO = {
    "green": "念のため、リンクではなく公式アプリやいつものブックマークから開いて確かめてください。",
    "amber": "リンクは押さずに、公式アプリやいつものブックマークから開いて確かめてください。",
    "red": "リンクは押さないでください。入力してしまった時は、すぐにパスワードを変え、カード会社や銀行に連絡してください。",
}
HELPLINES = [{"label": "警察相談専用電話", "tel": "#9110"}, {"label": "消費者ホットライン", "tel": "188"}]


def _prep(s: str) -> str:
    """NFKC にして、改行のなかまを LF にそろえる（リンクを探す時の文面）。"""
    return _BREAKS.sub("\n", unicodedata.normalize("NFKC", s or ""))


def _bare_text(s: str) -> str:
    """目に見えない文字を取りのぞく（言葉や電話番号を探す時の文面）。取りのぞいてから、もう一度 NFKC にする。"""
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", _INVISIBLE.sub("", s)))


def _norm(s: str) -> str:
    return _bare_text(_prep(s)).lower()


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
        if any(st in host or st in plain for st in b["stems"]):
            return b
    return None


def judge(text: str, ledger: Iterable[str], brands: Optional[List[dict]] = None) -> dict:
    """勘合の判定（決定的・純粋）。level は green / amber / red。"""
    return _judge(text, ledger, brands)[0]


def _judge(text: str, ledger: Iterable[str], brands: Optional[List[dict]] = None):
    """判定と、理由ごとの「何についての理由か」（行に印を付ける marks が使う。judge の答えには出さない）。"""
    brands = BRANDS if brands is None else brands
    owned = set(ledger or ())
    low = _norm(text)
    claimed = [b for b in brands if any(_norm(w) in low for w in b["words"])]
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
        say("no_claim", "どの会社を名乗っているか読み取れませんでした。", 1)
    for b in claimed:
        if b["kind"] == "contract" and b["id"] not in owned:
            say("not_in_ledger", f"「{b['name']}」を名乗っていますが、あなたの割符（契約している会社）にありません。", 2, b["id"])
        elif b["kind"] == "contract":
            say("in_ledger", f"「{b['name']}」はあなたの割符にあります。", 0, b["id"])

    # 「@」や「\」で本当の行き先をごまかす書き方（https://本物の住所@偽の住所/・https://偽の住所\@本物の住所/）
    # 行き先が空で読み取れないもの（https://本物の住所@/）も、見せかけとして数える（行き先は "" で表す）
    tricked = [host_of(u) or "" for u in urls if any(c in _SHOWN.match(u).group(1) for c in "@\\")]
    for h in dict.fromkeys(tricked):
        if h:
            say("disguised", f"リンクの住所に「@」や「\\」を使った見せかけがあります。本当の行き先は「{h}」です。", 2, h)
        else:
            say("disguised", "リンクの住所に「@」や「\\」を使った見せかけがあります。本当の行き先は読み取れません。", 2)

    for h in dict.fromkeys(hosts):   # 同じ住所は1回だけ
        if h in SHORTENERS:
            say("shortener", f"リンク（{h}）は短縮URLで、行き先が見えません。", 1, h)
            continue
        if h.startswith("xn--") or ".xn--" in h or not _HOST_OK.fullmatch(h):
            say("idn", f"リンク先「{h}」は、ふつうの住所には使わない文字を含んでいます。見た目を似せる手口に使われます。", 2, h)
            continue
        owner = next((b for b in brands if is_official(h, b)), None)
        if claimed and not any(is_official(h, b) for b in claimed):
            look = mimicked_brand(h, claimed)
            if look:
                say("mimic", f"リンク先「{h}」は「{look['name']}」に似せた住所ですが、公式の住所ではありません。", 2, h)
            else:
                say("off_domain", f"リンク先「{h}」は、名乗った会社の公式の住所ではありません。", 2, h)
        elif owner:
            say("official", f"リンク先「{h}」は「{owner['name']}」の公式の住所と一致しました。", 0, h)
        else:
            look = mimicked_brand(h, brands)
            if look:
                say("mimic", f"リンク先「{h}」は「{look['name']}」に似せた住所ですが、公式の住所ではありません。", 2, h)
            else:
                say("unknown_domain", f"リンク先「{h}」は、登録された公式の住所ではありません。", 1, h)

    # リンク（https:// の無いものも）の中の数字は数えない（住所はリンクとして照合済み）
    if _PHONE.search(plain):
        say("phone", "電話番号が書かれています。この番号が本物かは確かめられません。"
            "電話する時は、公式サイトやカードの裏面など、自分で確かめた番号からかけてください。", 1)

    tricks = list(dict.fromkeys(r for w, r in PRESSURE if w in low))
    if tricks:
        say("pressure", "詐欺によくある言いまわし：" + "、".join(tricks) + "。", 1)

    asks = list(dict.fromkeys(r for p, r in _TAKEOVER if p.search(low)))
    if asks:
        say("takeover", "乗っ取りの入口によくある頼みごと：" + "、".join(asks) + "。"
            "本物の会社は、ふつうメールやSMSのリンク・電話でこれを頼みません。公式アプリから自分で確かめてください。", 1)

    # 何ひとつ照らし合わせられなかった（配送・郵便・国税庁を名乗り、リンクが無い等）＝青にしない。
    # 青は、何か1つでも割符が合った時（in_ledger・official）だけ。
    if not reasons:
        say("nothing_to_check", "割符（契約している会社）や公式の住所へのリンクなど、照らし合わせられるものがありませんでした。", 1)

    level = ("green", "amber", "red")[rank]
    return ({"level": level, "head": HEADS[level], "reasons": reasons, "todo": TODO[level],
             "helplines": HELPLINES if level != "green" else [],
             "claimed": [b["id"] for b in claimed], "hosts": list(dict.fromkeys(hosts))}, detail)


# 行の印の短い説明（製品や言語ごとに言い回しを変えてよい。共通の見本では比べない）
MARK_LABELS = {
    "not_in_ledger": "割符にない会社の名前",
    "disguised": "本当の行き先をごまかしたリンク",
    "idn": "ふつう使わない文字のリンク",
    "mimic": "会社の名前に似せたリンク",
    "off_domain": "名乗った会社の公式の住所ではないリンク",
    "shortener": "行き先が見えない短縮URL",
    "unknown_domain": "登録された公式の住所ではないリンク",
    "phone": "電話番号（本物かは確かめられない）",
    "pressure": "詐欺によくある言いまわし",
    "takeover": "乗っ取りの入口によくある頼みごと",
}
_HOST_CODES = frozenset({"disguised", "idn", "mimic", "off_domain", "shortener", "unknown_domain"})


def marks(lines: Iterable[str], ledger: Iterable[str], brands: Optional[List[dict]] = None) -> List[dict]:
    """文面の「どの行が」引っかかったか（画面写真に枠を付ける・文面に印を付けるため）。

    lines は文面を行に分けたもの（画面写真から読んだ1行ずつ など）。判定は行を改行でつないだ文面で行い、
    その赤と黄の理由を、理由のもとになった行に割り当てる。答え（色・理由）は judge と同じで、変えない。
    青の理由（割符が合った所）には印を付けない＝「印の無い所は安全」と読ませないため。
    返すのは [{"line": 行の番号, "level": "red" | "amber", "codes": [...], "labels": [...]}]（印のある行だけ、行の順）。"""
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
                hit = b is not None and any(_norm(w) in low for w in b["words"])
            elif code in _HOST_CODES:
                hit = target in hosts
            elif code == "phone":
                hit = bool(_PHONE.search(plain))
            elif code == "pressure":
                hit = any(w in low for w, _ in PRESSURE)
            elif code == "takeover":
                hit = any(p.search(low) for p, _ in _TAKEOVER)
            else:
                hit = False
            if hit:
                rank = max(rank, level)
                codes.append(code)
                labels.append(MARK_LABELS[code])
        if codes:
            out.append({"line": i, "level": ("green", "amber", "red")[rank], "codes": codes, "labels": labels})
    return out
