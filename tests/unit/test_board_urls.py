import pytest

from boardwatch.core import board_urls
from boardwatch.core.board_urls import UnknownBoardURL, parse_board_target
from boardwatch.providers import registry


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("greenhouse:acme", ("greenhouse", "acme")),
        ("lever:globex", ("lever", "globex")),
        ("https://job-boards.greenhouse.io/acme", ("greenhouse", "acme")),
        ("https://boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
        ("https://jobs.lever.co/globex/", ("lever", "globex")),
        ("https://jobs.eu.lever.co/globex/abc-123-def", ("lever", "globex")),
        ("https://jobs.ashbyhq.com/initech?utm=x", ("ashby", "initech")),
        ("https://jobs.ashbyhq.com/initech/job/abc", ("ashby", "initech")),
    ],
)
def test_parses_known_targets(value, expected) -> None:
    assert parse_board_target(value) == expected

def test_unknown_url_is_rejected_with_supported_forms() -> None:
    with pytest.raises(UnknownBoardURL) as exc:
        parse_board_target("https://workday.com/acme")
    assert "greenhouse" in str(exc.value) and "provider:slug" in str(exc.value)

def test_help_text_enumerates_all_registry_providers() -> None:
    from boardwatch.providers.registry import PROVIDER_NAMES

    with pytest.raises(UnknownBoardURL) as exc:
        parse_board_target("notaprovider:acme")
    msg = str(exc.value)
    for name in PROVIDER_NAMES:
        assert name in msg


def test_board_urls_never_imports_store_transitively() -> None:
    # a SOURCE-STRING check misses transitive imports; assert the real import graph in a
    # clean subprocess: importing board_urls must not pull in any boardwatch.store.* module
    import subprocess
    import sys

    code = (
        "import boardwatch.core.board_urls; import sys; "
        "bad=[m for m in sys.modules if m.startswith('boardwatch.store')]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


class _ExtractorProvider:
    name = "stub"
    board_hosts: tuple[str, ...] = ("stub.example.com",)
    slug_help = "stub shortlinks omit the org; paste stub.example.com/{org}/j/{code}"

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        return None if parts[0] == "j" else parts[0]


class _NormalizerProvider:
    name = "caseless"
    board_hosts: tuple[str, ...] = ("caseless.example.com",)

    @staticmethod
    def normalize_slug(slug: str) -> str:
        return slug.lower()


def _install(monkeypatch: pytest.MonkeyPatch, *classes: type) -> None:
    monkeypatch.setattr(registry, "PROVIDER_CLASSES", tuple(classes), raising=True)
    # board_urls imported PROVIDER_NAMES by value, so patch its module global too — else the
    # qualified-form (`name:slug`) branch rejects the stub provider before normalization (H4).
    monkeypatch.setattr(board_urls, "PROVIDER_NAMES", frozenset(c.name for c in classes))
    monkeypatch.setattr(board_urls, "_HOST_PROVIDER", registry.host_provider_map())
    monkeypatch.setattr(board_urls, "_HOST_SUFFIX_PROVIDER", registry.host_suffix_provider_map())
    monkeypatch.setattr(board_urls, "_SLUG_EXTRACTORS", registry.slug_extractor_map())
    monkeypatch.setattr(board_urls, "_SLUG_NORMALIZERS", registry.slug_normalizer_map())
    monkeypatch.setattr(board_urls, "_SLUG_HELP", registry.slug_help_map())
    monkeypatch.setattr(board_urls, "_SUPPORTED", board_urls._build_supported())


def test_extractor_map_keys_are_optin_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _ExtractorProvider, _NormalizerProvider)
    mapping = registry.slug_extractor_map()
    assert set(mapping) == {"stub.example.com"}  # only the extractor opt-in
    assert callable(mapping["stub.example.com"])
    assert set(registry.slug_normalizer_map()) == {"caseless"}  # keyed by NAME


def test_extractor_rejects_shortlink_shape_with_help(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _ExtractorProvider)
    assert parse_board_target("stub.example.com/AcmeCo/x") == ("stub", "AcmeCo")
    with pytest.raises(UnknownBoardURL, match=r"stub\.example\.com/\{org\}/j/"):
        parse_board_target("stub.example.com/j/ABC123")


def test_normalize_slug_applies_to_both_forms(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _NormalizerProvider)
    # pasted-URL form
    assert parse_board_target("caseless.example.com/Visa") == ("caseless", "visa")
    # qualified provider:slug form  (H3 — the one that regressed)
    assert parse_board_target("caseless:Visa") == ("caseless", "visa")


def test_default_extraction_and_no_normalizer_is_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _ExtractorProvider)  # no normalizer for "stub"
    assert parse_board_target("stub.example.com/Mixed") == ("stub", "Mixed")


def test_shipped_greenhouse_url_still_parses() -> None:
    assert parse_board_target("boards.greenhouse.io/stripe") == ("greenhouse", "stripe")


class _SuffixHostProvider:
    name = "suffixy"
    board_hosts: tuple[str, ...] = ()
    board_host_suffixes: tuple[str, ...] = (".suffixy.example.com",)
    slug_help = "include the career-site path, e.g. tenant.suffixy.example.com/Careers"

    @staticmethod
    def slug_from_path(host: str, parts: list[str]) -> str | None:
        tenant = host.split(".", 1)[0]
        return f"{host}/{tenant}/{parts[0]}"

    @staticmethod
    def normalize_slug(slug: str) -> str:
        parts = slug.split("/")
        if len(parts) != 3 or not all(parts):
            raise ValueError("expected host/tenant/site")
        return f"{parts[0].lower()}/{parts[1].lower()}/{parts[2]}"


def test_composite_slug_survives_the_qualified_form(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _SuffixHostProvider)
    assert parse_board_target("suffixy:Acme.suffixy.example.com/Acme/Careers") == (
        "suffixy",
        "acme.suffixy.example.com/acme/Careers",
    )


def test_suffix_host_paste_form_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _SuffixHostProvider)
    assert parse_board_target("https://acme.suffixy.example.com/Careers") == (
        "suffixy",
        "acme.suffixy.example.com/acme/Careers",
    )


def test_lookalike_domain_does_not_match_the_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    # the leading dot is the label boundary: notsuffixy.example.com must NOT match
    _install(monkeypatch, _SuffixHostProvider)
    with pytest.raises(UnknownBoardURL, match="unrecognized board target"):
        parse_board_target("https://notsuffixy.example.com/Careers")


def test_bare_suffix_host_surfaces_slug_help(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _SuffixHostProvider)
    with pytest.raises(UnknownBoardURL, match="career-site path"):
        parse_board_target("https://acme.suffixy.example.com")


def test_normalizer_value_error_becomes_unknown_board_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # without the wrap a bare ValueError escapes `companies add`'s except UnknownBoardURL
    # (companies_cmd.py:74) and tracebacks the CLI
    _install(monkeypatch, _SuffixHostProvider)
    with pytest.raises(UnknownBoardURL, match="invalid suffixy board target"):
        parse_board_target("suffixy:not-a-triple")


def test_host_port_form_still_reaches_the_url_branch() -> None:
    # relaxing the qualified-form guard must not make host:port look like provider:slug
    with pytest.raises(UnknownBoardURL, match="unrecognized board target"):
        parse_board_target("example.com:8080/careers")


def test_colon_in_slug_still_splits_on_the_first_colon() -> None:
    assert parse_board_target("greenhouse:a:b") == ("greenhouse", "a:b")
