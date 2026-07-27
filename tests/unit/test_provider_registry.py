import subprocess
import sys

import pytest

from boardwatch.providers import registry
from boardwatch.providers.ashby import AshbyProvider
from boardwatch.providers.greenhouse import GreenhouseProvider
from boardwatch.providers.lever import LeverProvider


def test_each_provider_declares_public_board_hosts() -> None:
    assert GreenhouseProvider().board_hosts == ("job-boards.greenhouse.io", "boards.greenhouse.io")
    assert LeverProvider().board_hosts == ("jobs.lever.co", "jobs.eu.lever.co")
    assert AshbyProvider().board_hosts == ("jobs.ashbyhq.com",)


def test_build_providers_one_instance_per_class_keyed_by_name() -> None:
    built = registry.build_providers()
    assert set(built) == {"greenhouse", "lever", "ashby"}
    for name, inst in built.items():
        assert inst.name == name


def test_provider_names_matches_registered_set() -> None:
    assert registry.PROVIDER_NAMES == frozenset({"greenhouse", "lever", "ashby"})


def test_host_provider_map_covers_all_hosts_without_collision() -> None:
    hosts = registry.host_provider_map()
    assert hosts["job-boards.greenhouse.io"] == "greenhouse"
    assert hosts["boards.greenhouse.io"] == "greenhouse"
    assert hosts["jobs.lever.co"] == "lever"
    assert hosts["jobs.eu.lever.co"] == "lever"
    assert hosts["jobs.ashbyhq.com"] == "ashby"
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
