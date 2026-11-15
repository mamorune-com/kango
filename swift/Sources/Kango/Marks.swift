import Foundation

/// 文面の「どの行が」引っかかったか（画面写真に枠を付ける・文面に印を付けるため）。
/// Python の `kango.marks` と同じ規則（SPEC.md「行に印を付ける」）。
public struct Mark: Equatable, Sendable {
    /// 行の番号（0から）
    public let line: Int
    /// その行の色（赤か黄。青の行には印を付けない）
    public let level: Verdict.Level
    /// その行に当たる理由のコード（判定の理由と同じ並び）
    public let codes: [String]
    /// コードごとの短い説明（codes と同じ数・同じ並び）
    public let labels: [String]
}

extension Judge {
    /// 行の印の短い説明（製品や言語ごとに言い回しを変えてよい。共通の見本では比べない）
    public static let markLabels: [String: String] = Phrases.bundled.mark_labels["ja"] ?? [:]

    static let hostCodes: Set<String> = ["disguised", "idn", "mimic", "off_domain", "shortener", "unknown_domain"]

    /// lines は文面を行に分けたもの（画面写真から読んだ1行ずつ など）。判定は行を改行でつないだ文面で行い、
    /// その赤と黄の理由を、理由のもとになった行に割り当てる。答え（色・理由）は judge と同じで、変えない。
    /// 青の理由（割符が合った所）には印を付けない＝「印の無い所は安全」と読ませないため。
    /// lang＝labels の言語（"ja" か "en"）。
    public static func marks(lines: [String], ledger: Set<String>, brands: [Brand] = Catalog.bundled,
                             lang: String = "ja") -> [Mark] {
        let lang = languages.contains(lang) ? lang : "ja"
        let labelsByCode = Phrases.bundled.mark_labels[lang] ?? markLabels
        let detail = judge(text: lines.joined(separator: "\n"), ledger: ledger, brands: brands).reasons
        var out: [Mark] = []
        for (i, line) in lines.enumerated() {
            let low = norm(line)
            let lowScalars = Array(low.unicodeScalars)
            let found = scan(line)
            let hosts = Set(found.urls.compactMap(host(of:)) + found.bare)
            let plainRange = NSRange(found.plain.startIndex..., in: found.plain)
            let lowRange = NSRange(low.startIndex..., in: low)
            var level = Verdict.Level.green
            var codes: [String] = []
            var labels: [String] = []
            for r in detail where r.level != .green && !codes.contains(r.code) {
                let hit: Bool
                switch r.code {
                case "not_in_ledger":
                    hit = brands.first { $0.id == r.target }.map { b in b.words.contains { hasToken(lowScalars, norm($0)) } } ?? false
                case _ where hostCodes.contains(r.code):
                    hit = r.target.map { hosts.contains($0) } ?? false
                case "phone":
                    hit = phonePattern.firstMatch(in: found.plain, range: plainRange) != nil
                case "pressure":
                    hit = pressure.contains { p in p.words.contains { has(lowScalars, $0) } }
                case "takeover":
                    hit = takeover.contains { t in t.patterns.contains { $0.firstMatch(in: low, range: lowRange) != nil } }
                default:
                    hit = false
                }
                if hit {
                    level = max(level, r.level)
                    codes.append(r.code)
                    labels.append(labelsByCode[r.code] ?? r.code)
                }
            }
            if !codes.isEmpty { out.append(Mark(line: i, level: level, codes: codes, labels: labels)) }
        }
        return out
    }
}
