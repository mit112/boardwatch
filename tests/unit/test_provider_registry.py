import subprocess
import sys

import pytest

from boardwatch.providers import registry
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider
from boardwatch.providers.smartrecruiters import SmartRecruitersProvider
from boardwatch.providers.workable import WorkableProvider


def test_each_provider_declares_public_board_hosts() -> None:
    assert GreenhouseProvider().board_hosts == ("job-boards.greenhouse.io", "boards.greenhouse.io")
    assert LeverProvider().board_hosts == ("jobs.lever.co", "jobs.eu.lever.co")
    assert AshbyProvider().board_hosts == ("jobs.ashbyhq.com",)
    assert WorkableProvider().board_hosts == ("apply.workable.com",)
    assert SmartRecruitersProvider().board_hosts == ("jobs.smartrecruiters.com",)


def test_build_providers_one_instance_per_class_keyed_by_name() -> None:
    built = registry.build_providers()
    assert set(built) == {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}
    for name, inst in built.items():
        assert inst.name == name


def test_provider_names_matches_registered_set() -> None:
    assert registry.PROVIDER_NAMES == frozenset(
        {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}
    )


def test_host_provider_map_covers_all_hosts_without_collision() -> None:
    hosts = registry.host_provider_map()
    assert hosts["job-boards.greenhouse.io"] == "greenhouse"
    assert hosts["boards.greenhouse.io"] == "greenhouse"
    assert hosts["jobs.lever.co"] == "lever"
    assert hosts["jobs.eu.lever.co"] == "lever"
    assert hosts["jobs.ashbyhq.com"] == "ashby"
    assert hosts["apply.workable.com"] == "workable"
    assert hosts["jobs.smartrecruiters.com"] == "smartrecruiters"
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
