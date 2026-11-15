import XCTest
@testable import Kango

/// 見本の形では書けない約束を確かめる（python/tests/test_judge.py と同じこと）。
/// 色と理由のコードは、ConformanceTests.swift が共通の見本（conformance/cases.json）で確かめている。
final class JudgeTests: XCTestCase {
    func verdicts() throws -> [(text: String, verdict: Verdict)] {
        let all = try ConformanceTests.loadCases()
        return all.cases.map { c in (text: c.text, verdict: Judge.judge(text: c.text, ledger: Set(c.ledger ?? all.ledger))) }
    }

    func testCatalogLoads() {
        XCTAssertTrue(Catalog.bundled.contains { $0.id == "amazon" && $0.kind == .contract })
        XCTAssertTrue(Catalog.bundled.contains { $0.id == "yamato" && $0.kind == .everyone })
    }

    func testGreenNeverSaysGenuineOrSafe() throws {
        // 青は「割符が合いました」まで。「本物です」「安全です」とは言わない
        for (text, v) in try verdicts() where v.level == .green {
            let words = v.head + v.todo + v.reasons.map(\.text).joined()
            XCTAssertFalse(words.contains("本物"), text)
            XCTAssertFalse(words.contains("安全"), text)
        }
    }

    func testHelplinesUnlessGreen() throws {
        // 青以外では、相談先（#9110・188）を添える
        for (text, v) in try verdicts() {
            XCTAssertEqual(v.helplines.map(\.tel), v.level == .green ? [] : ["#9110", "188"], text)
        }
    }

    func testEnglishAnswersKeepLevelAndCodes() throws {
        // lang: "en" で変わるのは文だけ。色・理由のコード・名乗った会社・リンク先は同じ（python/tests/test_judge.py と同じこと）
        let all = try ConformanceTests.loadCases()
        for c in all.cases {
            let ledger = Set(c.ledger ?? all.ledger)
            let ja = Judge.judge(text: c.text, ledger: ledger)
            let en = Judge.judge(text: c.text, ledger: ledger, lang: "en")
            XCTAssertEqual(en.level, ja.level, c.text)
            XCTAssertEqual(en.reasons.map(\.code), ja.reasons.map(\.code), c.text)
            XCTAssertEqual(en.claimed, ja.claimed, c.text)
            XCTAssertEqual(en.hosts, ja.hosts, c.text)
            XCTAssertNotEqual(en.head, ja.head, c.text)
            if en.level == .green {
                let words = (en.head + en.todo + en.reasons.map(\.text).joined()).lowercased()
                for w in ["genuine", "safe", "legit", "authentic"] { XCTAssertFalse(words.contains(w), c.text) }
            }
        }
    }

    func testEnglishUsesEnglishBrandNames() {
        let v = Judge.judge(text: "【ヤマト運輸】お荷物のお届けにあがりましたが不在のため持ち帰りました https://yamato-hd.example/", ledger: [], lang: "en")
        XCTAssertTrue(v.reasons[0].text.contains("Yamato Transport"))
    }

    func testHelplinesByRegion() {
        let text = "Your account will be suspended https://evil.example/"
        func lines(_ lang: String = "ja", _ region: String? = nil) -> [String] {
            Judge.judge(text: text, ledger: [], lang: lang, region: region).helplines.map { $0.tel + "|" + ($0.url ?? "") }
        }
        XCTAssertEqual(lines(), ["#9110|", "188|"])
        XCTAssertEqual(lines("en"), [])
        XCTAssertEqual(lines("en", "JP"), ["#9110|", "188|"])
        XCTAssertEqual(lines("en", "us"), ["|https://reportfraud.ftc.gov/"])
        XCTAssertTrue(lines("en", "GB").contains("7726|"))
        XCTAssertTrue(lines("en", "AU")[0].hasPrefix("|https://portal.scamwatch.gov.au/"))
        XCTAssertEqual(lines("en", "FR"), [])
    }

    func testVerdictEqualityIncludesRegion() {
        // 同じ文面でも、相談先の国が違えば別の答え。出す相談先が同じなら同じ答え
        let text = "Your account will be suspended https://evil.example/"
        let us = Judge.judge(text: text, ledger: [], lang: "en", region: "US")
        XCTAssertEqual(us, Judge.judge(text: text, ledger: [], lang: "en", region: "us"))
        XCTAssertNotEqual(us, Judge.judge(text: text, ledger: [], lang: "en", region: "GB"))
        XCTAssertNotEqual(us, Judge.judge(text: text, ledger: [], lang: "en"))
        XCTAssertEqual(Judge.judge(text: text, ledger: []), Judge.judge(text: text, ledger: [], region: "JP"))
    }

    func testMarksLabelsInEnglish() {
        let lines = ["UPS: Your package is on hold.", "Pay the redelivery fee within 24 hours:", "https://ups-fee.example/pay"]
        let ja = Judge.marks(lines: lines, ledger: [])
        let en = Judge.marks(lines: lines, ledger: [], lang: "en")
        XCTAssertEqual(en.map(\.codes), ja.map(\.codes))
        XCTAssertEqual(en.first?.labels, ["Wording common in scams"])
    }
}
