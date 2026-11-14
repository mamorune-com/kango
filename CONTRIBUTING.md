# 会社・公式ドメインの追加と修正

1. `data/brands.csv` に1行足すか、直します（列の意味は下）。
2. `python3 scripts/sync_brands.py` で Python と Swift の同梱データを作り直します。
3. Pull Request に、**その会社自身の公式ページの URL**（フィッシングの注意喚起・FAQ など、公式ドメインが書かれているページ）を必ず書いてください。確かめた日付を `checked` に入れます。

| 列 | 意味 |
|---|---|
| `id` | 英小文字の短い名前（台帳に入る値） |
| `name` | 画面に出す名前 |
| `kind` | `contract`（契約者だけに連絡が来る）／`everyone`（誰にでも来うる） |
| `words` | 文面にこの言葉があれば「この会社を名乗っている」とみなす（`|` 区切り） |
| `domains` | 公式の住所（`|` 区切り・下位ドメインも公式とみなす） |
| `stems` | 偽の住所に紛れ込みやすい名前の断片（似せた住所の検出に使う） |
| `checked` | 公式ページで確かめた日付（空欄＝未確認） |
| `name_en` | 英語の答えに出す名前（空欄なら `name`） |

`words` と `stems` の言葉の先頭に `[` を付けると「その前が英数字でない時だけ」、末尾に `]` を付けると「その後ろが英数字でない時だけ」一致します。**3〜5文字の英語の名前には必ず付けてください**（`[ups]` が無いと `groups` や `startups` を UPS とみなし、`[chase card` が無いと `purchase card` を Chase とみなします）。決まりは SPEC.md の「言葉の両端の印」です。

**本物の連絡によく出る言葉は `words` に入れないでください。** たとえば「Facebookページ」は、お店のお知らせにふつうに書かれます。これを入れると、台帳に Meta が無い人には、そのお知らせが赤になります。アカウントやログインについての言葉（「Facebook account」「Instagram:」など）だけにします。

**グループ会社の住所の抜けに注意してください。** 例えば三井住友カードの `vpass.ne.jp` が抜けると、本物の連絡を「似せた住所」として赤にしてしまいます。追加したら、本物の住所が青になる見本を、共通の見本（[conformance/cases.json](conformance/cases.json)）に1件足してください。

## 審査について

会社一覧は「青（割符が合いました）」を決める、いちばん大事な部分です。誰かが偽サイトの住所を「公式」として混ぜると、その偽サイトが青になってしまいます。そのため、会社一覧と判定の変更は、管理者が**その会社の公式ページを自分で開いて確かめてから**取り込みます。公式ページの URL が無い変更は取り込みません。

## 答えの文・言いまわし・相談先を足す・直す時

`data/phrases.json` を直し、`python3 scripts/sync_brands.py` で写します。言いまわし（`pressure` の `words`・`takeover` の `patterns`）を足したら、**本物の連絡が誤って黄にならないか**も確かめてください（例：本物の確認コードの SMS の「Never share this code」は、乗っ取りの頼みごとにしない）。相談先は、その国の政府や警察の公式ページで確かめたものだけを入れ、Pull Request にそのページの URL を書きます。英語の文は、英語を母語とする人が読んで自然な文にしてください。

## 判定の規則を足す・直す時

[docs/extending.md](docs/extending.md) の手順に沿ってください。SPEC.md を先に直し、Python と Swift を同じように直して、共通の見本（[conformance/cases.json](conformance/cases.json)）に見本を足します。

## 抜け道を見つけた時

偽物の連絡が青になる抜け道は、公開の Issue や Pull Request には書かず、[SECURITY.md](SECURITY.md) の方法で、非公開でお知らせください。

---

## English

### Adding or fixing a company

1. Add or edit one row in `data/brands.csv`, then run `python3 scripts/sync_brands.py`.
2. In the pull request, **link the company's own official page** that lists its official domains (a phishing-awareness page, help article, etc.) and put the date you checked it in `checked`. Changes without such a link are not merged: an attacker who slips a fake domain into the list would turn their fake site green.
3. Add a case to [conformance/cases.json](conformance/cases.json) where the company's real address comes out green (ledger: that company only).

Columns: `id` (ledger value), `name` (Japanese display name), `kind` (`contract` = only customers get messages; `everyone` = anyone may, e.g. couriers, tax offices), `words` (if any appears in the message, it "claims" to be this company), `domains` (official domains; subdomains count), `stems` (name fragments that show up in fake addresses), `checked`, `name_en` (English display name).

Put `[` in front of a word or stem to require that the character before it is not an ASCII letter or digit, and `]` at the end to require the same after it. **Always use these for short English names** (`[ups]` so that "groups" and "startups" don't count as UPS; `[chase card` so that "purchase card" doesn't count as Chase). Don't add words that commonly appear in genuine messages (for example "Facebook page"); stick to account- and sign-in-related wording.

### Wording, phrase lists and helplines

These live in `data/phrases.json` (copied to Python and Swift by the same script). When you add pressure words or takeover patterns, also check that genuine messages don't turn amber (a real "Never share this code" SMS must not count as a takeover request). Only add helplines you've checked on an official government or police page, and link it in the PR. English text should read naturally to a native speaker.

### Reporting a bypass

If you find a way to make a fake message come out green, please don't open a public issue. Use the private route in [SECURITY.md](SECURITY.md).
