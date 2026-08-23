"""Non-US job-ad conventions read off a posting TITLE (the hard location gate's second axis).

Why a title signal at all: three GE HealthCare postings carry `locations_json: ["Remote"]` and
name no place whatsoever, so no location catalog can ever reach them — only the German title
("Applikationsspezialist/in Molekulare Bildgebung DACH (w/m/d)") reveals they are not US roles.
A city denylist is also structurally incomplete: Buc, Basel, Penzberg and Kleinmachnow were all
names boardwatch had never heard of, and the next foreign site will be too.

Only STRUCTURAL conventions are read, never vocabulary: the DACH gender marker that German
employment law effectively mandates, the French `(H/F)` equivalent, `Ingénieur`, and a title
written in CJK script. A hand-picked German noun list was measured and dropped — every token
either never fired or was already caught by the gender marker, and `koch` risked firing on
"Koch Industries".

The CJK clause (D-294) is the script test, NOT a non-ASCII test, and the difference is what
these tests exist to pin. Over 33,572 live open postings, 379 titles carry CJK script and 0
of them classify as US; 1,440 titles contain SOME non-ASCII character and 1,061 of those are
ordinary English titles carrying an en-dash, an em-dash or a trademark sign. Widening the
clause to "not ASCII" would drop all 1,061.
"""

import pytest

from boardwatch.rank.foreign_ad_gate import has_non_us_ad_marker


class TestFires:
    @pytest.mark.parametrize(
        "title",
        [
            # DACH gender marker, in the orderings actually observed in the corpus.
            "Hilfskoch:köchin (w/m/d), 100% - befristet für 1 Jahr",
            "Systembetreuer Information Solutions (m/w/d) - Sachsen",
            "Facharbeiter (m/w/d) Ansatz/Abfüllung befristet für 2 Jahre",
            "Working Student Imports(m/f/d)",
            "Candidate Experience Partner (d/f/m)",
            "Jewelry Verification Specialist (d/f/m)",
            "Applikationsspezialist/in Molekulare Bildgebung DACH (w/m/d)",
            # French.
            "Ingénieur(e) logiciel en imagerie médicale (Full Stack)",
            "Ingénieur(e) Front End (Typescript)",
            "Ingenieur/in Verfahrenstechnik (Basel, unbefristet)",
            "CDI - Ingénieur d'Applications WHS Ultrasons (H/F)",
            "Apprenti(e) – Technicien(ne) Maintenance (H/F)",
        ],
    )
    def test_non_us_ad_conventions_fire(self, title: str) -> None:
        assert has_non_us_ad_marker(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            # Simplified Chinese, verbatim from the 16 Genentech postings that cleared the
            # hard US-only gate on an unrecognised city (D-294).
            "实习医药信息顾问",
            "战略合作经理",
            "项目经理 - 商业多元业务 - 乳腺癌治疗领域",
            "（高级）治疗领域专员 - 肺癌治疗领域 - 长沙",
            # Japanese: kanji, plus a title that is mostly Latin and only partly kana.
            "DMR（営業職_栃木）",
            "Field Service Engineer (担当：MA/US、勤務地：広島支店)",
            "【岐阜】Sales Account Manager（担当製品：在宅医療向けの睡眠・呼吸製品）",
            # Korean hangul — the third script in the range, defended before it is needed.
            "백엔드 소프트웨어 엔지니어",
        ],
    )
    def test_a_cjk_script_title_fires(self, title: str) -> None:
        assert has_non_us_ad_marker(title) is True


class TestDoesNotFire:
    @pytest.mark.parametrize(
        "title",
        [
            "Software Engineer, Backend",
            "Senior Software Engineer (Remote)",
            "Member of Technical Staff (Software Engineer, Design System)",
            "Full Stack Engineer, Support Experience (Greater China Support)",
            "Software Engineer, Password Manager",
            "Data Engineer (H1B sponsorship available)",
            "Engineer, Payments (Frankfurt)",
            # A single parenthesised letter is not the convention — the marker needs the slash.
            "Software Engineer II (m)",
            "Product Manager (f)",
            "Engineer (W)",
            # Ordinary English words that a looser rule would have caught.
            "Machine Learning Engineer",
            "Site Reliability Engineer, Fraud",
        ],
    )
    def test_english_titles_do_not_fire(self, title: str) -> None:
        assert has_non_us_ad_marker(title) is False

    @pytest.mark.parametrize(
        "title",
        [
            # The US EEO string. The four-letter form must not fire — "V" (veteran) is not one
            # of the gendered letters — and neither must the unparenthesised form.
            "Software Engineer (M/F/D/V)",
            "Software Engineer EOE M/F/D/V",
            "Software Engineer - Equal Opportunity Employer M/F/Disability/Vet",
        ],
    )
    def test_the_us_eeo_string_does_not_fire(self, title: str) -> None:
        assert has_non_us_ad_marker(title) is False

    @pytest.mark.parametrize(
        "title",
        [
            # THE INVERSE ERROR the CJK clause exists to avoid. Every one of these is an
            # ordinary English title carrying one non-ASCII punctuation mark, and a
            # "not ASCII" test would drop all of them — 1,061 of the live corpus.
            "Staff Machine Learning Engineer – (ADAS/Autonomous Driving)",
            "Staff Front-end Engineer (CX) — Coupang Play",
            "Senior Manager – Application Security",
            "Sr. Designated Support Engineer, Apache Spark™",
            "Software Engineer, Women’s Health",
            "Backend Engineer (Café Platform)",
            # Cyrillic and Greek are non-ASCII and non-CJK: out of scope for THIS clause,
            # which is a script test for three named scripts, not a Latin-only test.
            "Инженер-программист",
        ],
    )
    def test_a_non_ascii_but_non_cjk_title_does_not_fire(self, title: str) -> None:
        assert has_non_us_ad_marker(title) is False

    def test_cjk_punctuation_alone_is_not_the_signal(self) -> None:
        # U+3000..U+303F (full-width parens, the ideographic comma) is CJK PUNCTUATION and is
        # deliberately outside the ranges: a Latin title that borrows one is not a CJK ad.
        # U+FF08/U+FF09 (Halfwidth and Fullwidth Forms) -- NOT the U+3000 CJK-punctuation
        # block the range list deliberately omits, so this case alone cannot prove that
        # omission. The bracket pair below is U+3010/U+3011 and is the one that can.
        assert has_non_us_ad_marker("Software Engineer（Remote）") is False
        assert has_non_us_ad_marker("Software Engineer 【Remote】") is False
        assert has_non_us_ad_marker("Software Engineer、Remote") is False
        # U+30FB and U+30FC sit inside the kana block but are punctuation, so the range is
        # split around them. A Latin title borrowing either must not read as a Japanese ad.
        assert has_non_us_ad_marker("Software Engineer・Remote") is False
        assert has_non_us_ad_marker("Software Engineer ー Remote") is False
        # ...while real kana still fires, because it carries a kana LETTER as well.
        assert has_non_us_ad_marker("サーバーサイドエンジニア") is True

    def test_a_german_city_alone_is_a_location_signal_not_an_ad_marker(self) -> None:
        # Frankfurt belongs to the location catalog. This gate reads the AD CONVENTION only, so
        # the two signals stay independently reviewable.
        assert has_non_us_ad_marker("Backend Engineer - Frankfurt") is False
