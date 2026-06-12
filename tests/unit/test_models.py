import pytest
from pydantic import ValidationError

from boardwatch.core.models import BoardRequest, BoardSnapshot, RawPosting, ResponseValidators


def _raw_posting(posting_id: str = "1") -> RawPosting:
    return RawPosting(
        provider_posting_id=posting_id,
        title="Software Engineer",
        url="https://example.com/jobs/1",
        locations=["Remote — US"],
        department="Engineering",
        remote_policy="remote",
        posted_at=None,
        updated_at=None,
        body_text="We build things.",
        raw_json={"id": 1},
    )


def test_board_request_carries_canonical_url_and_validators() -> None:
    request = BoardRequest(
        provider="greenhouse",
        slug="acme",
        url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true&pay_transparency=true",
        validators=ResponseValidators(etag='W/"abc"', last_modified=None),
    )
    assert request.url.startswith("https://boards-api.greenhouse.io/")
    assert request.validators is not None and request.validators.etag == 'W/"abc"'


def test_snapshot_echoes_url_and_observed_validators() -> None:
    snapshot = BoardSnapshot(
        status="complete",
        postings=[_raw_posting()],
        url="https://example.com/board",
        observed_validators=ResponseValidators(etag="x", last_modified="y"),
        error=None,
    )
    assert snapshot.url == "https://example.com/board"
    assert snapshot.observed_validators is not None


@pytest.mark.parametrize("status", ["unchanged", "failed"])
def test_postings_must_be_empty_for_unchanged_and_failed(status: str) -> None:
    with pytest.raises(ValidationError):
        BoardSnapshot(
            status=status,  # type: ignore[arg-type]
            postings=[_raw_posting()],
            url="https://example.com/board",
            observed_validators=None,
            error=None,
        )


def test_validators_carry_metadata_only_no_body_field() -> None:
    assert set(ResponseValidators.model_fields) == {"etag", "last_modified"}  # D15: never bodies


def test_models_are_frozen() -> None:
    posting = _raw_posting()
    with pytest.raises(ValidationError):
        posting.title = "Other"  # type: ignore[misc]


def test_raw_posting_salary_defaults_none() -> None:
    posting = _raw_posting()
    assert posting.salary_min is None and posting.salary_max is None
    assert posting.salary_currency is None and posting.salary_period is None
