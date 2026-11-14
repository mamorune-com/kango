import Foundation

/// 答えの文・言いまわしの一覧・相談先。正は data/phrases.json（scripts/sync_brands.py で写す）。Python の kango.PHRASES と同じもの。
struct Phrases: Decodable {
    struct Pressure: Decodable {
        let key: String
        let words: [String]
        let ja: String
        let en: String
    }

    struct Takeover: Decodable {
        let key: String
        let patterns: [String]
        let ja: String
        let en: String
    }

    struct HelplineEntry: Decodable {
        let ja: String
        let en: String
        let tel: String?
        let url: String?
    }

    let languages: [String]
    let heads: [String: [String: String]]
    let todo: [String: [String: String]]
    let messages: [String: [String: String]]
    let pressure: [Pressure]
    let takeover: [Takeover]
    let helplines: [String: [HelplineEntry]]
    let mark_labels: [String: [String: String]]

    /// アプリに同梱した文（読めなければ部品が壊れている＝すぐ止める）
    static let bundled: Phrases = {
        guard let url = Bundle.module.url(forResource: "phrases", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let p = try? JSONDecoder().decode(Phrases.self, from: data) else {
            preconditionFailure("phrases.json を読めません（scripts/sync_brands.py で写し直してください）")
        }
        return p
    }()

    func text(_ lang: String, _ key: String, _ args: [String: String] = [:]) -> String {
        var s = messages[lang]?[key] ?? messages["ja"]?[key] ?? key
        for (k, v) in args { s = s.replacingOccurrences(of: "{" + k + "}", with: v) }
        return s
    }
}

extension Phrases.Pressure {
    func reason(_ lang: String) -> String { lang == "en" ? en : ja }
}

extension Phrases.Takeover {
    func reason(_ lang: String) -> String { lang == "en" ? en : ja }
}
