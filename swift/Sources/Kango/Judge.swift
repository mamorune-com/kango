import Foundation

/// 判定の結果。青でも「本物」「安全」とは言わない（割符が合った、まで）。
public struct Verdict: Equatable, Sendable {
    public enum Level: Int, Comparable, Codable, Sendable {
        case green = 0, amber, red
        public static func < (a: Level, b: Level) -> Bool { a.rawValue < b.rawValue }
    }

    public struct Reason: Equatable, Sendable {
        public let code: String
        public let text: String
        /// この理由の色と、何についての理由か（リンク先の住所、または会社の id）。
        /// 行に印を付ける `Judge.marks` だけが使う（Python の judge の答えにも出さない）。
        let level: Level
        let target: String?

        init(code: String, text: String, level: Level, target: String? = nil) {
            self.code = code
            self.text = text
            self.level = level
            self.target = target
        }
    }

    public let level: Level
    public let reasons: [Reason]
    public let claimed: [String]
    public let hosts: [String]
    /// 答えの文の言語（"ja" か "en"）。色と理由のコードは言語で変わらない
    public let lang: String
    /// 相談先を出す国・地域（"JP"・"US"・"GB"・"AU"）。nil なら、日本語は日本、英語は出さない
    public let region: String?

    init(level: Level, reasons: [Reason], claimed: [String], hosts: [String], lang: String = "ja", region: String? = nil) {
        self.level = level
        self.reasons = reasons
        self.claimed = claimed
        self.hosts = hosts
        self.lang = lang
        self.region = region
    }

    /// 相談先を決める国・地域（大文字）。region が nil なら、日本語は "JP"、英語は ""（出さない）
    var helplineRegion: String { (region ?? (lang == "ja" ? "JP" : "")).uppercased() }

    /// 同じ答えか。相談先の国も比べる（"us" と "US"、日本語で nil と "JP" は、出す相談先が同じなので同じ答え）
    public static func == (a: Verdict, b: Verdict) -> Bool {
        a.level == b.level && a.reasons == b.reasons && a.claimed == b.claimed && a.hosts == b.hosts
            && a.lang == b.lang && a.helplineRegion == b.helplineRegion
    }

    static func levelName(_ l: Level) -> String {
        switch l {
        case .green: return "green"
        case .amber: return "amber"
        case .red: return "red"
        }
    }

    public var head: String { Phrases.bundled.heads[lang]?[Verdict.levelName(level)] ?? "" }

    public var todo: String { Phrases.bundled.todo[lang]?[Verdict.levelName(level)] ?? "" }

    public struct Helpline: Hashable, Sendable {
        public let label: String
        /// かける番号（無い窓口は ""）
        public let tel: String
        /// 届け出のページ（無い窓口は nil）
        public let url: String?

        public init(label: String, tel: String, url: String? = nil) {
            self.label = label
            self.tel = tel
            self.url = url
        }
    }

    /// 迷った時の窓口（青では出さない）
    public var helplines: [Helpline] {
        if level == .green { return [] }
        return (Phrases.bundled.helplines[helplineRegion] ?? []).map { h in
            Helpline(label: lang == "en" ? h.en : h.ja, tel: h.tel ?? "", url: h.url)
        }
    }
}

/// 勘合（割符の照合）。決定的・端末の中だけで動く。python/kango と同じ規則（SPEC.md）。
/// ★文章の上手さは見ない／リンク先へアクセスしない／文面を保存しない。
public enum Judge {
    static let shorteners: Set<String> = ["bit.ly", "t.co", "tinyurl.com", "is.gd", "x.gd", "t.ly", "cutt.ly", "ow.ly", "rebrand.ly"]

    /// 答えの文の言語
    public static let languages: [String] = Phrases.bundled.languages
    /// 相談先を出せる国・地域
    public static let regions: [String] = Phrases.bundled.helplines.keys.sorted()

    /// 詐欺によくある言いまわし（言葉ひとつでは赤にしない＝黄まで）。日本語・英語ほか主要な言語の言葉を、理由ごとにまとめてある。
    static let pressure: [Phrases.Pressure] = Phrases.bundled.pressure

    /// 乗っ取りの入口によくある頼みごと（顔認証・指紋・パスキーそのものではなく、本人に操作させる手口）。
    /// 言葉だけでは赤にしない＝黄まで。照合は正規化した文面（NFKC・小文字）に対して行う。
    /// 「.」は改行にも当てる（頼みごとの途中で行を変えて照合を外す手口があるため）
    static let takeover: [(patterns: [NSRegularExpression], entry: Phrases.Takeover)] = Phrases.bundled.takeover.map { t in
        (t.patterns.map { try! NSRegularExpression(pattern: $0, options: [.dotMatchesLineSeparators]) }, t)
    }

    static func matches(_ p: NSRegularExpression, _ s: String) -> Bool {
        p.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) != nil
    }

    /// 見た目が似た文字（amaz0n・rakut3n 等）を戻してから、似せた住所を探す
    static let lookalike: [Character: Character] = ["0": "o", "1": "l", "3": "e", "5": "s", "4": "a"]

    /// リンクが終わる文字＝空白と制御文字・かぎかっこ・山かっこ（<> 〈〉 《》）・亀甲かっこ・引用符・閉じかっこ・読点「、」。
    /// 空白は \s と書かない（何を空白とみなすかが言語ごとに違い、答えが食い違うため）。
    static let endChars = #"\u0000-\u0020\u007f-\u009f\u1680「」『』【】〈〉《》〔〕<>"'）)、"#
    /// リンク＝ http: か https: のあとに / か \ が続く文字の並び（ブラウザは \ も / とみなし、/ が1つでも開く）。
    static let urlPattern = try! NSRegularExpression(pattern: #"https?:[/\\]+[^"# + endChars + #"]+"#, options: [.caseInsensitive])
    /// リンクの中に入っている、もう1つのリンクの始まり（https://本物/・https://偽物/ や ?url=https://… など）
    static let innerPattern = try! NSRegularExpression(pattern: #"https?:[/\\]"#, options: [.caseInsensitive])
    /// リンクの「住所の部分」（最初の / \ ? # まで）
    static let authorityPattern = try! NSRegularExpression(pattern: #"^https?:[/\\]+([^/\\?#]*)"#, options: [.caseInsensitive])
    /// 見た目の「住所の部分」（\ を区切りと思わずに読んだ時。ここに @ や \ があれば見せかけ）
    static let shownPattern = try! NSRegularExpression(pattern: #"^https?:[/\\]+([^/?#]*)"#, options: [.caseInsensitive])
    /// https:// の無いリンク（rakuten-card-login.com/abc など。メッセージアプリはこれも押せるリンクにする）。
    /// 英数字とハイフンの並びを . でつなぎ、最後が英字2〜24文字。前後に英数字や @ が付くもの（メールアドレスなど）は数えない。
    static let barePattern = try! NSRegularExpression(pattern: #"(?<![a-z0-9@._%+\-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![a-z0-9\-@])(?:[/?#][^"# + endChars + #"]*)?"#, options: [.caseInsensitive])
    /// ファイル名（meisai.pdf など）は住所として数えない（どれもトップレベルドメインではない）
    static let fileExtensions: Set<String> = ["pdf", "html", "htm", "jpg", "jpeg", "png", "gif", "txt", "csv", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "js", "css", "json", "xml", "php", "exe", "apk"]
    /// 住所にふつう使う文字（英小文字・数字・. ・-）。これ以外を含む住所＝見た目を似せる手口か、壊れた住所
    static let hostCharsPattern = try! NSRegularExpression(pattern: #"^[a-z0-9.\-]+$"#)

    /// 電話番号＝次のどれか。前後に数字が続くもの（注文番号など）は数えない。番号が本物かは確かめられない＝黄まで。
    /// ・0（または +81）で始まり、区切り（空白＝スペース・タブ・改行・U+1680、かっこ・ハイフン類・「.」「・」＝数字の間に3文字まで）を除いて
    ///   10〜11桁（+81 の時は9〜10桁）。2桁目が 0 の番号（0077 など）も数える。英国・フランス・ドイツなどの国内の書き方もこれに当たる。
    /// ・+ と国番号で始まる国際的な書き方（+81 以外）。区切りを除いて 8〜15桁。
    /// ・オーストラリアの全国共通の番号（1300・1800 で始まる10桁＝区切りは上と同じ。13 で始まる6桁＝「13 22 21」「131 450」のように空白で区切ったもの）。
    /// ・北米の書き方（(800) 555-0199・800-555-0199・1-800-555-0199・800—555—0199）。3桁・3桁・4桁を区切り（空白・「.」・ハイフン類）でつなぐ（区切りの無い10桁は数えない）。
    static let phoneSeparators = #"[ \t\n\u1680()\-‐−–—―ー.・]{0,3}"#
    static let phonePattern = try! NSRegularExpression(
        pattern: #"(?<![0-9])(?:(?:\+81|0)"# + phoneSeparators + #"[0-9](?:"# + phoneSeparators + #"[0-9]){8,9}"#
            + #"|\+(?!81)[1-9](?:"# + phoneSeparators + #"[0-9]){7,14}"#
            + #"|1[38]00(?:"# + phoneSeparators + #"[0-9]){6}|13 [0-9]{2} [0-9]{2}|13[1-9] [0-9]{3}"#
            + #"|(?:1[ .\-‐−–—―])?(?:\([2-9][0-9]{2}\) ?|[2-9][0-9]{2}[ .\-‐−–—―])[2-9][0-9]{2}[ .\-‐−–—―][0-9]{4})(?![0-9])"#)

    /// 改行のなかま（CR・垂直タブ・改ページ・U+001C〜001F・U+0085・行と段落の区切り）。LF にそろえる
    /// （「.」や空白が何に当たるかが言語ごとに違い、答えが食い違うため）。
    static func isBreak(_ v: UInt32) -> Bool {
        v == 0x0D || v == 0x0B || v == 0x0C || (0x1C...0x1F).contains(v) || v == 0x85 || v == 0x2028 || v == 0x2029
    }

    /// 目に見えない文字（ゼロ幅の空白・異体字セレクタ・向きを変える印など）。言葉や番号の間にはさんで照合を外す手口に使われる。
    /// Unicode の版で変わらないよう、範囲を書き並べる（SPEC.md と Python の _INVISIBLE と同じ）。
    static func isInvisible(_ v: UInt32) -> Bool {
        switch v {
        case 0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B...0x180F, 0x200B...0x200F, 0x202A...0x202E,
             0x2060...0x206F, 0x3164, 0xFE00...0xFE0F, 0xFEFF, 0xFFA0,
             0x1BCA0...0x1BCA3, 0x1D173...0x1D17A, 0xE0000...0xE0FFF:
            return true
        default:
            return false
        }
    }

    /// NFKC にして、改行のなかまを LF にそろえる（リンクを探す時の文面）
    static func prep(_ s: String) -> String {
        var out = String.UnicodeScalarView()
        for u in s.precomposedStringWithCompatibilityMapping.unicodeScalars {
            out.append(isBreak(u.value) ? ("\n" as Unicode.Scalar) : u)
        }
        return String(out)
    }

    static func withoutInvisible(_ s: String) -> String {
        var out = String.UnicodeScalarView()
        for u in s.unicodeScalars where !isInvisible(u.value) { out.append(u) }
        return String(out)
    }

    /// 目に見えない文字を取りのぞく（言葉や電話番号を探す時の文面）。取りのぞいてから、もう一度 NFKC にする。
    static func bareText(_ s: String) -> String {
        withoutInvisible(withoutInvisible(s).precomposedStringWithCompatibilityMapping)
    }

    static func norm(_ s: String) -> String { bareText(prep(s)).lowercased() }

    /// 文字の番号（Unicode スカラー）の並びで「含むか」を見る。Swift の String.contains は「見た目の1文字」の単位で比べるので、
    /// 言葉のすぐ後ろに結合文字などが続くと一致しなくなる（Python と答えが食い違う）。
    static func has(_ hay: [Unicode.Scalar], _ needle: String) -> Bool {
        let n = Array(needle.unicodeScalars)
        if n.isEmpty { return true }
        if hay.count < n.count { return false }
        for i in 0...(hay.count - n.count) where hay[i] == n[0] {
            if hay[i..<(i + n.count)].elementsEqual(n) { return true }
        }
        return false
    }

    static func isAsciiAlnum(_ u: Unicode.Scalar) -> Bool {
        (0x61...0x7A).contains(u.value) || (0x30...0x39).contains(u.value)
    }

    /// hay に w が含まれるか。w の先頭の「[」＝その前が英数字でないこと、末尾の「]」＝その後ろが英数字でないこと
    /// （"[ups]" は groups の中の ups に当たらない・"[chase card" は purchase card に当たらない）。Python の _has と同じ。
    static func hasToken(_ hay: [Unicode.Scalar], _ w: String) -> Bool {
        var n = Array(w.unicodeScalars)
        let left = n.first == "["
        let right = n.count > 1 && n.last == "]"
        if left { n.removeFirst() }
        if right { n.removeLast() }
        if !left && !right { return has(hay, w) }
        if n.isEmpty { return true }
        if hay.count < n.count { return false }
        for i in 0...(hay.count - n.count) where hay[i..<(i + n.count)].elementsEqual(n) {
            let j = i + n.count
            if (!left || i == 0 || !isAsciiAlnum(hay[i - 1])) && (!right || j == hay.count || !isAsciiAlnum(hay[j])) {
                return true
            }
        }
        return false
    }

    static func authority(of url: String, _ pattern: NSRegularExpression) -> String? {
        let range = NSRange(url.startIndex..., in: url)
        guard let m = pattern.firstMatch(in: url, range: range),
              let r = Range(m.range(at: 1), in: url) else { return nil }
        return String(url[r])
    }

    /// リンクの本当の行き先の住所（ホスト名）。ブラウザと同じ読み方をする：
    /// \ は / と同じ・@ より前（利用者名とパスワード）は住所ではない・: の後ろは番号（ポート）・「。」は「.」と同じ。
    public static func host(of url: String) -> String? {
        guard let auth = authority(of: url, authorityPattern) else { return nil }
        // 文字の番号（Unicode スカラー）の単位で切る（@ や : のすぐ後ろに結合文字が続いても、同じ所で切れるように）
        var s = Array(auth.unicodeScalars)
        if let i = s.lastIndex(of: "@") { s = Array(s[(i + 1)...]) }
        if s.first == "[" {
            if let i = s.firstIndex(of: "]") { s = Array(s[..<i]) }
            s.append("]")
        } else if let i = s.firstIndex(of: ":") {
            s = Array(s[..<i])
        }
        var view = String.UnicodeScalarView()
        for u in s { view.append(u == "。" ? "." : u) }
        var low = Array(String(view).lowercased().unicodeScalars)
        while low.last == "." { low.removeLast() }
        var out = String.UnicodeScalarView()
        out.append(contentsOf: low)
        return low.isEmpty ? nil : String(out)
    }

    /// 文面を、リンク・https:// の無いリンクの住所・それ以外の文字（電話番号を探す所）に分ける
    static func scan(_ text: String) -> (urls: [String], bare: [String], plain: String) {
        let t = prep(text) as NSString
        let whole = NSRange(location: 0, length: t.length)
        var urls: [String] = []
        for m in urlPattern.matches(in: t as String, range: whole) {
            let u = t.substring(with: m.range) as NSString
            urls.append(u as String)
            // リンクの中に、もう1つリンクが入っていれば、それも数える（前のリンクに続けて書いて隠す手口）
            for inner in innerPattern.matches(in: u as String, range: NSRange(location: 0, length: u.length))
            where inner.range.location > 0 {
                urls.append(u.substring(from: inner.range.location))
            }
        }
        let rest = urlPattern.stringByReplacingMatches(in: t as String, range: whole, withTemplate: " ") as NSString
        var bare: [String] = []
        // ファイル名はリンクではないので、文面に残す（090-1234-5678.pdf のように番号を隠す手口）
        let plain = NSMutableString(string: rest as String)
        let found = barePattern.matches(in: rest as String, range: NSRange(location: 0, length: rest.length))
        var links: [NSRange] = []
        for m in found {
            let name = rest.substring(with: m.range(at: 1)).lowercased()
            if fileExtensions.contains(name.components(separatedBy: ".").last ?? "") { continue }
            bare.append(name)
            links.append(m.range)
        }
        for r in links.reversed() { plain.replaceCharacters(in: r, with: " ") }
        return (urls, bare, bareText(plain as String))
    }

    public static func urls(in text: String) -> [String] { scan(text).urls }

    /// リンク（https:// の無いものも）を除いた文面に、電話番号が書かれているか（リンクの中の数字は数えない）
    public static func hasPhoneNumber(_ text: String) -> Bool {
        let plain = scan(text).plain
        return phonePattern.firstMatch(in: plain, range: NSRange(plain.startIndex..., in: plain)) != nil
    }

    static func hasOnlyHostChars(_ h: String) -> Bool {
        hostCharsPattern.firstMatch(in: h, range: NSRange(h.startIndex..., in: h)) != nil
    }

    /// 正規化した文面の先頭（空白・タブ・改行を除く）が「【」なら、最初の「】」までの見出し（【】を含む）。無ければ空。
    static func heading(_ low: [Unicode.Scalar]) -> [Unicode.Scalar] {
        let t = low.drop { $0 == " " || $0 == "\t" || $0 == "\n" }
        guard t.first == "\u{3010}", let k = t.firstIndex(of: "\u{3011}") else { return [] }
        return Array(t[t.startIndex...k])
    }

    public static func isOfficial(_ host: String, _ brand: Brand) -> Bool {
        brand.domains.contains { host == $0 || host.hasSuffix("." + $0) }
    }

    /// 公式でない住所に、会社の名前（似せた文字も含む）が入っていれば その会社
    public static func mimicked(_ host: String, in brands: [Brand]) -> Brand? {
        let plain = Array(String(host.map { lookalike[$0] ?? $0 }).unicodeScalars)
        let hs = Array(host.unicodeScalars)
        return brands.first { b in
            !isOfficial(host, b) && b.stems.contains { hasToken(hs, $0) || hasToken(plain, $0) }
        }
    }

    /// 勘合の判定。lang＝答えの文の言語（"ja" か "en"・それ以外は "ja"）。region＝相談先の国・地域（"JP"・"US"・"GB"・"AU"）。
    /// 色と理由のコードは lang と region で変わらない。
    public static func judge(text: String, ledger: Set<String>, brands: [Brand] = Catalog.bundled,
                             lang: String = "ja", region: String? = nil) -> Verdict {
        let lang = languages.contains(lang) ? lang : "ja"
        let ph = Phrases.bundled
        let low = norm(text)
        let lowScalars = Array(low.unicodeScalars)
        var claimed = brands.filter { b in b.words.contains { hasToken(lowScalars, norm($0)) } }
        // 文面が【】の見出しで始まり、見出しの中で会社を名乗っていれば、名乗った会社は見出しの会社だけ
        let head = heading(lowScalars)
        if !head.isEmpty {
            let named = claimed.filter { b in b.words.contains { hasToken(head, norm($0)) } }
            if !named.isEmpty { claimed = named }
        }
        let found = scan(text)
        let hosts = unique(found.urls.compactMap(host(of:)) + found.bare)
        var reasons: [Verdict.Reason] = []
        var level = Verdict.Level.green

        func say(_ code: String, _ text: String, _ l: Verdict.Level, _ target: String? = nil) {
            reasons.append(.init(code: code, text: text, level: l, target: target))
            level = max(level, l)
        }

        if claimed.isEmpty {
            say("no_claim", ph.text(lang, "no_claim"), .amber)
        }
        for b in claimed where b.kind == .contract {
            if ledger.contains(b.id) {
                say("in_ledger", ph.text(lang, "in_ledger", ["name": b.displayName(lang)]), .green, b.id)
            } else {
                say("not_in_ledger", ph.text(lang, "not_in_ledger", ["name": b.displayName(lang)]), .red, b.id)
            }
        }

        // 「@」や「\」で本当の行き先をごまかす書き方（https://本物の住所@偽の住所/・https://偽の住所\@本物の住所/）
        let tricked = unique(found.urls.filter { u in
            (authority(of: u, shownPattern) ?? "").unicodeScalars.contains { $0 == "@" || $0 == "\\" }
        }.map { host(of: $0) ?? "" })   // 行き先が空で読み取れないもの（https://本物の住所@/）も数える（"" で表す）
        for h in tricked {
            if h.isEmpty {
                say("disguised", ph.text(lang, "disguised_unreadable"), .red)
            } else {
                say("disguised", ph.text(lang, "disguised", ["host": h]), .red, h)
            }
        }

        for h in hosts {
            if shorteners.contains(h) {
                say("shortener", ph.text(lang, "shortener", ["host": h]), .amber, h)
                continue
            }
            if h.hasPrefix("xn--") || h.contains(".xn--") || !hasOnlyHostChars(h) {
                say("idn", ph.text(lang, "idn", ["host": h]), .red, h)
                continue
            }
            let owner = brands.first { isOfficial(h, $0) }
            if !claimed.isEmpty && !claimed.contains(where: { isOfficial(h, $0) }) {
                if let look = mimicked(h, in: claimed) {
                    say("mimic", ph.text(lang, "mimic", ["host": h, "name": look.displayName(lang)]), .red, h)
                } else {
                    say("off_domain", ph.text(lang, "off_domain", ["host": h]), .red, h)
                }
            } else if let owner {
                say("official", ph.text(lang, "official", ["host": h, "name": owner.displayName(lang)]), .green, h)
            } else if let look = mimicked(h, in: brands) {
                say("mimic", ph.text(lang, "mimic", ["host": h, "name": look.displayName(lang)]), .red, h)
            } else {
                say("unknown_domain", ph.text(lang, "unknown_domain", ["host": h]), .amber, h)
            }
        }

        // リンク（https:// の無いものも）の中の数字は数えない（住所はリンクとして照合済み）
        if phonePattern.firstMatch(in: found.plain, range: NSRange(found.plain.startIndex..., in: found.plain)) != nil {
            say("phone", ph.text(lang, "phone"), .amber)
        }

        let sep = ph.messages[lang]?["list_sep"] ?? "、"
        let tricks = unique(pressure.filter { p in p.words.contains { has(lowScalars, $0) } }.map { $0.reason(lang) })
        if !tricks.isEmpty {
            say("pressure", ph.text(lang, "pressure", ["list": tricks.joined(separator: sep)]), .amber)
        }

        let asks = unique(takeover.filter { t in t.patterns.contains { matches($0, low) } }.map { $0.entry.reason(lang) })
        if !asks.isEmpty {
            say("takeover", ph.text(lang, "takeover", ["list": asks.joined(separator: sep)]), .amber)
        }

        // 何ひとつ照らし合わせられなかった（配送・郵便・国税庁を名乗り、リンクが無い等）＝青にしない。
        // 青は、何か1つでも割符が合った時（in_ledger・official）だけ。
        if reasons.isEmpty {
            say("nothing_to_check", ph.text(lang, "nothing_to_check"), .amber)
        }

        return Verdict(level: level, reasons: reasons, claimed: claimed.map(\.id), hosts: hosts, lang: lang, region: region)
    }

    static func unique(_ xs: [String]) -> [String] {
        var seen = Set<String>()
        return xs.filter { seen.insert($0).inserted }
    }
}
