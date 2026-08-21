"""Non-US job-ad conventions read off a posting TITLE (the hard location gate's second axis).

Why a title signal at all: three GE HealthCare postings carry `locations_json: ["Remote"]` and
name no place whatsoever, so no location catalog can ever reach them — only the German title
("Applikationsspezialist/in Molekulare Bildgebung DACH (w/m/d)") reveals they are not US roles.
A city denylist is also structurally incomplete: Buc, Basel, Penzberg and Kleinmachnow were all
names boardwatch had never heard of, and the next foreign site will be too.

Only STRUCTURAL conventions are read, never vocabulary: the DACH gender marker that German
employment law effectively mandates, the French `(H/F)` equivalent, and `Ingénieur`. A hand-
picked German noun list was measured and dropped — every token either never fired or was
already caught by the gender marker, and `koch` risked firing on "Koch Industries".
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

    def test_a_german_city_alone_is_a_location_signal_not_an_ad_marker(self) -> None:
        # Frankfurt belongs to the location catalog. This gate reads the AD CONVENTION only, so
        # the two signals stay independently reviewable.
        assert has_non_us_ad_marker("Backend Engineer - Frankfurt") is False
