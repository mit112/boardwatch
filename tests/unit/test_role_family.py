import pytest

from boardwatch.extract.role_family import ROLE_FAMILIES, classify_role_family


def test_priority_order_is_the_ported_order() -> None:
    assert [family for family, _ in ROLE_FAMILIES] == [
        "mobile", "security", "devops_sre", "data_eng",
        "ml_ai", "fullstack", "frontend", "backend",
    ]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("iOS Engineer", "mobile"),
        ("Senior Swift Developer", "mobile"),
        ("Mobile Security Engineer", "mobile"),  # priority: mobile outranks security
        ("Security Engineer, Platform", "security"),
        ("Site Reliability Engineer", "devops_sre"),
        ("Cloud Engineer II", "devops_sre"),
        # Pinned port behavior: 'infrastructure engineer' outranks ml_ai
        ("ML Infrastructure Engineer", "devops_sre"),
        ("Data Engineer", "data_eng"),
        ("Machine Learning Engineer", "ml_ai"),
        ("Applied Scientist, GenAI", "ml_ai"),
        ("Full-Stack Developer", "fullstack"),
        ("Frontend Engineer", "frontend"),
        ("Backend API Engineer", "backend"),
        ("Software Engineer, Distributed Systems", "backend"),
        ("Software Engineer", "general_swe"),
        ("New Grad Software Engineer 2026", "general_swe"),
    ],
)
def test_classification(title: str, expected: str) -> None:
    assert classify_role_family(title) == expected
