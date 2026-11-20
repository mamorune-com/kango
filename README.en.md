# kango

**日本語: [README.md](README.md)**

kango checks an email, text message or chat message against two "tallies" and answers green, amber or red:

1. **Your own ledger** — the list of companies you actually do business with.
2. **Each company's official domains** — the web addresses that company really uses.

Spam filters look at the wording and the sender. kango looks at **your relationship with the company**. A scam written in perfect, natural English by an AI still comes out red if the tallies don't match.

```
PayPal: Your account has been limited https://paypal-resolution.example/
  → Red: It claims to be from PayPal, but PayPal isn't in your ledger (the companies you actually use).
         The link "paypal-resolution.example" is made to look like an address of PayPal, but it isn't an official one.

USPS: The package could not be delivered. Update your address: usps-redeliver.example/x
  → Red: The link is made to look like USPS, but it isn't an official address.

Chase alert: A $45.00 transaction was made https://secure.chase.com/web/auth/dashboard
  → Green: The tallies match (kango never says "this is genuine").
```

## What kango will and won't do

- **No AI.** Only fixed rules. The same input always gets the same answer.
- **No guarantees.** Green means "the tallies match", nothing more. kango never says a message is genuine or safe.
- **Nothing leaves the device.** The message and your ledger are never stored or sent anywhere.
- **No link is ever opened.** kango only compares text; it never contacts the sender's server.

## Getting started

### Python

```sh
pip install "git+https://github.com/mamorune-com/kango@v0.9.0#subdirectory=python"
```

The `kango` package on PyPI is an unrelated project. `pip install kango` will not install this one.

```python
from kango import judge

r = judge("PayPal: You sent a payment of $20.00. https://www.paypal.com/myaccount/activity",
          ledger=["paypal"], lang="en", region="US")
r["level"]      # "green" / "amber" / "red"
r["head"]       # "The tallies match"
r["reasons"]    # [{"code": "in_ledger", "text": "PayPal is in your ledger."}, ...]
r["todo"]       # what the person should do next
r["helplines"]  # where to get help (empty when green)
```

- `lang` — the language of the answer text: `"ja"` (default) or `"en"`. The level, the reason codes, the claimed companies and the hosts are the same in every language.
- `region` — which country's helplines to show: `"JP"`, `"US"`, `"GB"` or `"AU"`. If you leave it out, Japanese answers show Japan's helplines and English answers show none (kango can't tell where the person lives). Other countries get none for now.

From the command line:

```sh
python -m kango --ledger paypal,netflix --lang en --region GB
# paste the message, then press Ctrl-D (on Windows, Ctrl-Z then Enter)

python -m kango --brands --lang en   # the companies you can put in a ledger
```

Paste real messages rather than passing them with `echo` or as an argument, so they don't end up in your shell history.

### Swift (iOS 17 / macOS 13 or later)

Add `https://github.com/mamorune-com/kango` with Xcode's *File → Add Package Dependencies…*, or add this line to the dependencies in `Package.swift`:

```swift
.package(url: "https://github.com/mamorune-com/kango", from: "0.9.0")
```

```swift
import Kango

let v = Judge.judge(text: message, ledger: ["paypal", "netflix"], lang: "en", region: "US")
v.level       // .green / .amber / .red
v.head        // "The tallies match"
v.helplines   // [Verdict.Helpline] (label, tel, url)
```

A new version can change the answer for the same message. See [CHANGELOG.md](CHANGELOG.md) before you upgrade.

### Putting it in front of an AI agent

An AI that reads mail or opens links on someone's behalf can be phished just like a person. Run `judge` before the agent opens a link or types anything in, let it continue only on green, and stop and ask the person on amber or red. The check must be done by your program, not by the AI, so that a message can't talk the AI out of it.

### The checkpoint (for documents you give to an AI)

`kango.sekisho` is a separate tool that checks a document (Markdown, text, HTML) **before** you hand it to an AI. It looks for hidden instructions (prompt injection): text that tries to rewrite the AI's instructions, hide things from the person, send out keys or passwords, run downloaded commands, or tell an AI analyzer that a file is "harmless". It also flags invisible characters, hidden HTML, comments, tracking images and links outside your trusted list. It reads English, Japanese, Spanish, French, German, Portuguese, Chinese and Korean, and can answer in English:

```sh
python -m kango.sekisho received.md --trusted github.com --lang en
```

```python
from kango.sekisho import check
check(text, trusted_hosts=["github.com"], lang="en")["level"]   # "red" / "amber" / "none"
```

"none" means nothing was found. It does not mean the document is safe.

## How a message is judged

All rules are in [SPEC.md](SPEC.md) (in Japanese). In short:

- **Which company does it claim to be?** If a company's name appears (for example "PayPal", "Microsoft account", "UPS:"), the message claims to be that company.
- **Is that company in your ledger?** Banks, cards, shops and online services only contact their own customers. If one of them writes to you and it isn't in your ledger, that's red. Couriers, postal services and tax offices can contact anyone, so for them kango checks only the links.
- **Where do the links really go?** Each link is read the way a browser reads it (including tricks like `https://real-site@fake-site/`). A link to the company's official domain is green. A link that contains the company's name but isn't official (`paypal-resolution.example`, `amaz0n.example`) is red. Shortened links are amber because the destination is hidden.
- **Scam wording and takeover requests** ("within 24 hours", "verify your identity", "tell us the verification code", "we need remote access", "git clone our repo and run npm install") make a message amber. Wording alone never makes it red. kango looks for these in English, Japanese, Spanish, French, German, Italian, Portuguese, Chinese, Korean, Indonesian and Vietnamese.
- **Phone numbers** can't be verified, so a message with one is never green. kango recognizes Japanese numbers, international numbers starting with `+`, and North American numbers like `(800) 555-0199`.

The Python and Swift versions follow the same rules. Both test suites run the same language-neutral test vectors ([conformance/cases.json](conformance/cases.json)), so you can also use them to check a port to another language.

## Companies covered

[data/brands.csv](data/brands.csv) is the source of truth: 111 companies, 40 in Japan and 71 elsewhere — major banks and brokerages in Japan, the US, Korea, the UK, Europe and Taiwan (for example Citi, Schwab, Fidelity, KB Kookmin, Toss, Lloyds, NatWest, Monzo, Revolut, ING, Deutsche Bank, BNP Paribas, BBVA, Intesa Sanpaolo, Rabobank, E.SUN, Cathay United and Yuanta), PayPal, Microsoft, Netflix, Meta (Facebook, Instagram, WhatsApp), eBay, Coinbase, Binance, Chase, Bank of America, Wells Fargo, HSBC, Barclays, Airbnb, Booking.com, Steam, DHL, FedEx, UPS, USPS, Royal Mail, Canada Post, Australia Post, DocuSign, the IRS and HMRC, plus Amazon, Apple and Google worldwide. The `checked` column is the date we confirmed the domains on the company's own official page. **A blank `checked` would mean we haven't confirmed them yet** (none right now). We only add domains that the company itself lists; we don't guess.

To add or fix a company, see [CONTRIBUTING.md](CONTRIBUTING.md#english).

## Limits

kango only looks at company names, link addresses, scam wording and takeover requests in the text. It can't do the following.

- **Amber is common.** Shortened links, messages that don't name a company, and messages with nothing to check (a courier or tax office with no link) are amber, never green.
- **Companies not on the list aren't covered.** If a company you use is missing, its messages are amber at best.
- **A missing ledger entry causes a false red.** A genuine message from a company you use but didn't add to your ledger is red.
- **Answer text is in Japanese and English only.** Helplines are available for Japan, the US, the UK and Australia only.
- **Email addresses and chat IDs aren't checked.** If the claimed company is in your ledger, a message asking you to "reply to this address" can still be green.
- **A hijacked official account or site gets through.** So can an open redirect on an official domain whose destination is hidden (for example, percent-encoded).
- **User content on official domains is official.** A page anyone can create on an official domain (for example a Facebook page or a DocuSign envelope) passes the domain check. For Google, only the account and support domains are on the list for this reason.
- **Scams that don't name a company stay amber.** Investment and romance scams can't be turned red.
- **Text only.** Turn images and QR codes into text before calling kango. Voice calls and malware are out of scope.

## Where the idea comes from

kango isn't a new invention. Password managers only fill in your password on the site's real address, and passkeys (FIDO2 / WebAuthn) only work on the domain they were created for. kango applies the same proven idea to incoming messages. Red and green are decided by things an attacker can't fake — your own ledger, and domains they don't own — not by how convincing the text is.

## Why isn't this already everywhere? (our view)

- **It needs a per-person ledger.** A company that collected "who does business with whom" would create a serious privacy problem. kango keeps the ledger on the device.
- **There's no data to monetize.** Because nothing leaves the device, it doesn't fit business models built on collected data.
- **Most protection relies on blocklists.** Blocklists matter, but they lag behind brand-new phishing sites. kango compares against a list of *real* addresses instead, so a brand-new fake site that claims to be a listed company is still "not an official address". Use it alongside blocklists, not instead of them.

## Official source

The only official source of kango is this repository (github.com/mamorune-com/kango). Apps or sites claiming "verified safe by kango" have nothing to do with us.

## Found a bypass?

If you find a way to make a fake message come out green, please don't open a public issue. Report it privately as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 ([LICENSE](LICENSE)). You may build kango into commercial apps and services, including paid ones. When you distribute it, include the license and the [NOTICE](NOTICE). A plain-language summary is in [docs/commercial-use.md](docs/commercial-use.md) (in Japanese).

This is a decision aid, not a guarantee. If in doubt, open the official app or your usual bookmark instead of the link, and contact your bank, card company or local fraud helpline.

Provided by MAMORUNE Inc.
