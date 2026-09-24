"""DESIGN-T183 B2: the location catalog resolves a place to ISO-3 countries, not to "US or not".

`resolve_countries` is the country-level reading; `classify_location` is a thin wrapper over it
(`"USA" in resolve(...)`), so every pin in `test_location_gate.py` is the control that the
restructure changed no US verdict. What is pinned here is the new half: which country a token
names, that only a POSITIVE pack can resolve the pack's own country, and that the old flat
token sets are exactly the union of the new per-country ones.
"""

import pytest

from boardwatch.rank import location_data as data
from boardwatch.rank.foreign_ad_gate import ad_marker_countries, has_non_us_ad_marker
from boardwatch.rank.location_gate import classify_location, resolve_countries


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        ("Toronto, ON", {"CAN"}),
        ("Boston, MA", {"USA"}),
        ("Blorptown", set()),
        ("Remote", set()),
        ("Worldwide", set()),
        ("Munich, Germany", {"DEU"}),
        ("Kirkland, QC, CAN", {"CAN"}),
        ("Remote (IND)", {"IND"}),
        ("Vienna, VA", {"USA"}),
        ("Vienna", {"AUT"}),
        ("Wuxi, Jiangsu", {"CHN"}),
        ("Berlin, Germany 10115", {"DEU"}),
    ],
)
def test_a_place_resolves_to_its_countries(loc: str, expected: set[str]) -> None:
    assert resolve_countries([loc]) == frozenset(expected)


# T194: the municipalities and provincial capitals the catalog lacked, each observed in the store
# as a bare city or "City, City" with no country to do the work, and each read `unknown`, fail-open.
@pytest.mark.parametrize(
    "loc",
    [
        "Tianjin, Tianjin",
        "Tianjin",
        "Chongqing",
        "Shijiazhuang",
        "Taiyuan",
        "Hohhot",
        "Shenyang",
        "Changchun",
        "Harbin",
        "Fuzhou",
        "Jinan",
        "Zhengzhou",
        "Changsha",
        "Nanning",
        "Haikou",
        "Guiyang",
        "Lhasa",
        "Lanzhou",
        "Xining",
        "Urumqi",
        "Ürümqi",
    ],
)
def test_a_chinese_municipality_or_provincial_capital_resolves_to_china(loc: str) -> None:
    assert resolve_countries([loc]) == frozenset({"CHN"})
    assert classify_location([loc]) == "non_us"


def test_a_multi_country_region_resolves_to_all_of_them_and_never_the_us() -> None:
    emea = resolve_countries(["EMEA"])
    assert {"DEU", "GBR", "ZAF", "ARE"} <= emea
    assert "USA" not in emea


def test_segments_union() -> None:
    assert resolve_countries(["Toronto, ON", "Boston, MA"]) == frozenset({"CAN", "USA"})


def test_every_resolved_code_is_iso3166() -> None:
    codes = set(data.COUNTRY_NAMES_BY_ISO3) | set(data.CITIES_BY_ISO3)
    codes |= set().union(*data.REGIONS_TO_ISO3.values())
    codes |= {code.upper() for code in data.NON_US_ISO3}
    assert codes <= data.ISO3166_ALPHA3


def test_only_the_us_pack_resolves_the_us() -> None:
    """The token map is foreign-only: a US reading has to come from the POSITIVE pack, which
    is what lets its ordering (state before foreign token) be the pack's own."""
    assert "USA" not in data.COUNTRY_NAMES_BY_ISO3
    assert "USA" not in data.CITIES_BY_ISO3
    assert all("USA" not in codes for codes in data.REGIONS_TO_ISO3.values())
    assert data.USA_PACK.iso3 == "USA"


def test_the_flat_token_sets_are_the_union_of_the_per_country_ones() -> None:
    assert data.NON_US_COUNTRIES == frozenset().union(*data.COUNTRY_NAMES_BY_ISO3.values())
    assert data.NON_US_CITIES == frozenset().union(*data.CITIES_BY_ISO3.values())
    assert data.NON_US_REGIONS == frozenset(data.REGIONS_TO_ISO3)


def test_classify_location_is_the_us_reading_of_the_resolver() -> None:
    for loc in ("Toronto, ON", "Boston, MA", "Blorptown", "EMEA", "US, Canada"):
        got = resolve_countries([loc])
        expected = "us" if "USA" in got else "non_us" if got else "unknown"
        assert classify_location([loc]) == expected


@pytest.mark.parametrize(
    ("title", "country"),
    [
        ("Softwareentwickler (m/w/d)", "DEU"),
        ("Ingénieur logiciel (H/F)", "FRA"),
        ("软件工程师", "CHN"),
    ],
)
def test_an_ad_marker_names_its_countries(title: str, country: str) -> None:
    got = ad_marker_countries(title)
    assert country in got
    assert "USA" not in got
    assert has_non_us_ad_marker(title)


def test_a_plain_title_names_no_country() -> None:
    assert ad_marker_countries("Software Engineer") == frozenset()
    assert not has_non_us_ad_marker("Software Engineer")
