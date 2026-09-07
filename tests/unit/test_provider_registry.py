import subprocess
import sys

import pytest

from boardwatch.providers import registry
from boardwatch.providers.amazon import AmazonProvider
from boardwatch.providers.apple import AppleProvider
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.eightfold import EightfoldProvider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.jibe import JibeProvider
from boardwatch.providers.lever import LeverProvider
from boardwatch.providers.phenom import PhenomProvider
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider
from boardwatch.providers.workable import WorkableProvider
from boardwatch.providers.workday import WorkdayProvider


def test_each_provider_declares_public_board_hosts() -> None:
    """Workday and Eightfold are ABSENT from this assertion, and that is the accommodation
    their identity forces rather than an omission: neither has a bounded set of exact paste
    hosts, so both declare `board_hosts = ()` and are pinned by the suffix tests below."""
    assert GreenhouseProvider().board_hosts == ("job-boards.greenhouse.io", "boards.greenhouse.io")
    assert LeverProvider().board_hosts == ("jobs.lever.co", "jobs.eu.lever.co")
    assert AshbyProvider().board_hosts == ("jobs.ashbyhq.com",)
    assert WorkableProvider().board_hosts == ("apply.workable.com",)
    assert SmartRecruitersProvider().board_hosts == ("jobs.smartrecruiters.com",)
    assert AmazonProvider().board_hosts == ("www.amazon.jobs", "amazon.jobs")
    assert AppleProvider().board_hosts == ("jobs.apple.com",)


def test_build_providers_one_instance_per_class_keyed_by_name() -> None:
    built = registry.build_providers()
    assert set(built) == {
        "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday", "jibe",
        "oraclehcm", "phenom", "eightfold", "amazon", "apple",
    }
    for name, inst in built.items():
        assert inst.name == name


def test_provider_names_matches_registered_set() -> None:
    assert registry.PROVIDER_NAMES == frozenset(
        {
            "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday", "jibe",
            "oraclehcm", "phenom", "eightfold", "amazon", "apple",
        }
    )


def test_workday_declares_a_suffix_and_no_exact_hosts() -> None:
    assert WorkdayProvider().board_hosts == ()
    assert WorkdayProvider().board_host_suffixes == (".myworkdayjobs.com",)
    assert registry.host_suffix_provider_map()[".myworkdayjobs.com"] == "workday"
    # the suffix must be the extractor/help MAP KEY, not absent
    assert ".myworkdayjobs.com" in registry.slug_extractor_map()
    assert ".myworkdayjobs.com" in registry.slug_help_map()


def test_jibe_declares_a_custom_domain_and_therefore_no_hosts_and_no_suffix() -> None:
    """A Jibe board is served from the EMPLOYER'S OWN hostname (careers.amd.com,
    jobs.statefarm.com, careers.jhuapl.edu), so there is neither a finite paste-host list nor a
    shared vendor suffix to key one off. Both maps are empty ON PURPOSE.

    `custom_domain_slug` is what says so, and it is asserted BY NAME here rather than by
    letting `test_each_provider_declares_public_board_hosts` accept an empty tuple: that check
    exists to catch a provider whose hosts nobody declared, and weakening it for this one would
    stop it catching that for the other five.
    """
    assert JibeProvider().board_hosts == ()
    assert getattr(JibeProvider, "board_host_suffixes", ()) == ()
    assert JibeProvider.custom_domain_slug is True
    # the identity is `jibe:<careers host>`; the slug IS the host, lowercased
    assert JibeProvider.normalize_slug("Careers.Acme.Test") == "careers.acme.test"
    assert "jibe" in registry.slug_normalizer_map()
    assert "jibe" not in registry.host_provider_map().values()
    assert "jibe" not in registry.host_suffix_provider_map().values()


def test_oraclehcm_declares_a_suffix_and_no_exact_hosts() -> None:
    from boardwatch.providers.oraclehcm import OracleHCMProvider

    assert OracleHCMProvider().board_hosts == ()
    assert OracleHCMProvider().board_host_suffixes == (".oraclecloud.com",)
    assert registry.host_suffix_provider_map()[".oraclecloud.com"] == "oraclehcm"
    # the suffix must be the extractor/help MAP KEY, not absent
    assert ".oraclecloud.com" in registry.slug_extractor_map()
    assert ".oraclecloud.com" in registry.slug_help_map()


def test_composite_slug_providers_are_the_three_that_declare_it() -> None:
    assert registry.composite_slug_providers() == frozenset({"workday", "oraclehcm", "phenom"})


def test_phenom_declares_neither_an_exact_host_nor_a_suffix() -> None:
    """Phenom career sites are on the EMPLOYER's own domain (jobs.baesystems.com,
    www.pgcareers.com, jobs.battelle.org), so there is no bounded hostname set to register and
    no shared suffix either -- the Workday escape hatch does not apply. The consequence is
    deliberate and is asserted here rather than worked around: a pasted Phenom URL is not
    recognized, and a board is added through the qualified `phenom:{host}/{country}/{lang}`
    form only. That form needs `composite_slug`, which is what lets "/" through it."""
    assert PhenomProvider().board_hosts == ()
    assert getattr(PhenomProvider, "board_host_suffixes", ()) == ()
    # both markers: the same `custom_domain_slug` jibe declares, AND `composite_slug`, because
    # the country/lang cannot be read off the host. phenom is the only provider that is both.
    assert PhenomProvider.custom_domain_slug is True
    assert PhenomProvider.composite_slug is True
    assert "phenom" in registry.composite_slug_providers()
    assert "phenom" not in registry.host_provider_map().values()
    assert "phenom" not in registry.host_suffix_provider_map().values()

def test_eightfold_declares_a_suffix_and_no_exact_hosts() -> None:
    """The THIRD suffix-only provider, and for a stronger reason than workday's or oraclehcm's:
    an Eightfold tenant usually sits on the EMPLOYER's own domain, which no suffix can
    enumerate. Only the vendor-hosted form is claimable, which is why the suffix is declared
    AND `board_hosts` is empty rather than one standing in for the other.
    """
    assert EightfoldProvider().board_hosts == ()
    assert EightfoldProvider().board_host_suffixes == (".eightfold.ai",)
    assert registry.host_suffix_provider_map()[".eightfold.ai"] == "eightfold"
    # the suffix must be the extractor/help MAP KEY, not absent
    assert ".eightfold.ai" in registry.slug_extractor_map()
    assert ".eightfold.ai" in registry.slug_help_map()
    # and it is NOT a composite slug: `eightfold:a/b` must keep getting the diagnostic
    assert "eightfold" not in registry.composite_slug_providers()


def test_amazon_declares_exact_hosts_whose_paths_can_never_carry_a_slug() -> None:
    """The FIRST provider that registers exact paste hosts and still extracts nothing from them.

    An amazon.jobs board is one job CATEGORY, and a category is a query parameter
    (`?category[]=Software Development`), so no path segment of any amazon.jobs URL names one --
    not a search URL's and not a posting URL's. `slug_from_path` therefore answers None for
    every URL, which routes the paste through `slug_help` instead of letting the default
    first-segment extractor hand `normalize_slug` a locale segment (`en`) and produce a catalog
    diagnostic about a word the user never typed. Asserted by NAME rather than left to the
    default, because "no extractor registered" and "an extractor that deliberately declines"
    are indistinguishable from the map alone.
    """
    assert AmazonProvider().board_hosts == ("www.amazon.jobs", "amazon.jobs")
    assert getattr(AmazonProvider, "board_host_suffixes", ()) == ()
    assert AmazonProvider.slug_from_path("www.amazon.jobs", ["en", "search"]) is None
    assert AmazonProvider.slug_from_path("www.amazon.jobs", ["en", "jobs", "10530555", "x"]) is None
    # both exact hosts must be extractor AND help map keys, not just one of them
    for host in AmazonProvider.board_hosts:
        assert host in registry.slug_extractor_map()
        assert "amazon:software-development" in registry.slug_help_map()[host]
    # the identity is `amazon:<category token>`, and the token is a CLOSED catalog
    assert AmazonProvider.normalize_slug("Software-Development") == "software-development"
    with pytest.raises(ValueError):
        AmazonProvider.normalize_slug("en")
    assert "amazon" in registry.slug_normalizer_map()
    # and it is NOT a composite slug: `amazon:a/b` must keep getting the diagnostic
    assert "amazon" not in registry.composite_slug_providers()


def test_apple_declares_one_exact_host_whose_paths_can_never_carry_a_slug() -> None:
    """The SECOND provider in amazon's position, for the same structural reason: a
    jobs.apple.com board is one COUNTRY and a country is a query parameter
    (`?location=united-states-USA`), so no path segment names one -- the only segment before
    `search` is the locale (`en-us`), which is exactly the word the default first-segment
    extractor would hand `normalize_slug`.

    The catalog guard is load-bearing here in a way it is not for most providers: an unknown
    location code is answered with HTTP 200 and `totalRecords: 0` rather than an error, so an
    out-of-catalog slug would be watched forever as a board that is merely empty today.
    """
    assert AppleProvider().board_hosts == ("jobs.apple.com",)
    assert getattr(AppleProvider, "board_host_suffixes", ()) == ()
    assert AppleProvider.slug_from_path("jobs.apple.com", ["en-us", "search"]) is None
    assert AppleProvider.slug_from_path(
        "jobs.apple.com", ["en-us", "details", "900000001", "x"]
    ) is None
    assert "jobs.apple.com" in registry.slug_extractor_map()
    assert "apple:united-states" in registry.slug_help_map()["jobs.apple.com"]
    # the identity is `apple:<country token>`, and the token is a CLOSED catalog
    assert AppleProvider.normalize_slug("United-States") == "united-states"
    for outside in ("en-us", "united-states-USA", "usa"):
        with pytest.raises(ValueError):
            AppleProvider.normalize_slug(outside)
    assert "apple" in registry.slug_normalizer_map()
    # and it is NOT a composite slug: `apple:a/b` must keep getting the diagnostic
    assert "apple" not in registry.composite_slug_providers()


def test_host_provider_map_covers_all_hosts_without_collision() -> None:
    hosts = registry.host_provider_map()
    assert hosts["job-boards.greenhouse.io"] == "greenhouse"
    assert hosts["boards.greenhouse.io"] == "greenhouse"
    assert hosts["jobs.lever.co"] == "lever"
    assert hosts["jobs.eu.lever.co"] == "lever"
    assert hosts["jobs.ashbyhq.com"] == "ashby"
    assert hosts["apply.workable.com"] == "workable"
    assert hosts["jobs.smartrecruiters.com"] == "smartrecruiters"
    assert hosts["www.amazon.jobs"] == "amazon"
    assert hosts["amazon.jobs"] == "amazon"
    assert hosts["jobs.apple.com"] == "apple"
    total = sum(len(cls().board_hosts) for cls in registry.PROVIDER_CLASSES)
    assert len(hosts) == total  # no host maps to two providers


def test_registry_import_is_store_free() -> None:
    code = (
        "import boardwatch.providers.registry; import sys; "
        "bad=[m for m in sys.modules if m.startswith('boardwatch.store')]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"registry pulled in store modules: {result.stdout.strip()}"


def test_default_providers_delegates_to_registry() -> None:
    from boardwatch.scan.coordinator import default_providers

    assert set(default_providers()) == set(registry.build_providers())


def test_build_providers_raises_on_duplicate_name(monkeypatch) -> None:
    class FakeA:
        name = "dup"
        board_hosts = ("a.example.com",)

    class FakeB:
        name = "dup"
        board_hosts = ("b.example.com",)

    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (FakeA, FakeB))
    with pytest.raises(ValueError, match="duplicate provider name"):
        registry.build_providers()


def test_host_provider_map_raises_on_duplicate_host(monkeypatch) -> None:
    class FakeA:
        name = "a"
        board_hosts = ("shared.example.com",)

    class FakeB:
        name = "b"
        board_hosts = ("shared.example.com",)

    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (FakeA, FakeB))
    with pytest.raises(ValueError, match="shared.example.com"):
        registry.host_provider_map()


def test_identity_derivation_does_not_instantiate_providers(monkeypatch) -> None:
    class Exploding:
        name = "boom"
        board_hosts = ("boom.example.com",)

        def __init__(self) -> None:  # pragma: no cover - must never run
            raise AssertionError("identity derivation must not instantiate providers")

    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (Exploding,))
    # host_provider_map reads both name and board_hosts off the class, with no cls()
    assert registry.host_provider_map() == {"boom.example.com": "boom"}


def test_identity_derivation_raises_on_duplicate_name(monkeypatch) -> None:
    class A:
        name = "dup"
        board_hosts = ("a.example.com",)

    class B:
        name = "dup"
        board_hosts = ("b.example.com",)

    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (A, B))
    with pytest.raises(ValueError, match="duplicate provider name"):
        registry.host_provider_map()


class _SuffixProvider:
    name = "suffixy"
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (".suffixy.example.com",)
    slug_help = "include the site path, e.g. tenant.suffixy.example.com/Careers"

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        return parts[0]


def test_suffix_map_is_keyed_by_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (_SuffixProvider,), raising=True)
    assert registry.host_suffix_provider_map() == {".suffixy.example.com": "suffixy"}
    assert registry.host_provider_map() == {}


def test_extractor_and_help_maps_register_suffix_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # A suffix-only provider declares board_hosts = (), so a map that iterates board_hosts
    # alone silently registers NOTHING for it and every pasted URL fails to parse.
    monkeypatch.setattr(registry, "PROVIDER_CLASSES", (_SuffixProvider,), raising=True)
    assert set(registry.slug_extractor_map()) == {".suffixy.example.com"}
    assert set(registry.slug_help_map()) == {".suffixy.example.com"}


def test_duplicate_host_suffix_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Other:
        name = "other"
        board_hosts: tuple[str, ...] = ()
        board_host_suffixes: tuple[str, ...] = (".suffixy.example.com",)

    monkeypatch.setattr(
        registry, "PROVIDER_CLASSES", (_SuffixProvider, _Other), raising=True
    )
    with pytest.raises(ValueError, match="duplicate board host suffix"):
        registry.host_suffix_provider_map()
