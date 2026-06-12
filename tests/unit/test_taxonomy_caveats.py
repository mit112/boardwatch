"""Every known regex caveat of the ported taxonomy, pinned with real-world strings.

Three kinds of pins:
- POSITIVE / NEGATIVE: the case-sensitivity discipline and guard patterns.
- ACCEPTED_HITS / ACCEPTED_MISSES: known imperfections carried over from the
  source pipeline deliberately (plan deviation 12) — these tests document
  behavior; "fixing" one is a semantic change requiring an EXTRACTOR_REVISION
  bump and external review.
"""


import pytest

from boardwatch.extract.taxonomy import Taxonomy, load_taxonomy


@pytest.fixture(scope="module")
def taxonomy(tmp_path_factory: pytest.TempPathFactory) -> Taxonomy:
    return load_taxonomy(tmp_path_factory.mktemp("no-override"))


POSITIVE: list[tuple[str, str]] = [
    # Go: token is case-sensitive with a followed-by-stopword guard
    ("Go", "We use Go in production."),
    ("Go", "Experience with Golang required"),
    ("Go", "Our services are written in golang"),
    ("Go", "Go, Rust, or C++ experience"),
    # React: CS token; .js forms any case
    ("React", "Experience with React and Redux"),
    ("React", "Built with react.js"),
    ("React", "React.JS experience a plus"),
    # REST: CS token (deviation 4 fix); 'restful' any case
    ("REST APIs", "Design REST APIs at scale"),
    ("REST APIs", "RESTful services"),
    ("REST APIs", "build restful endpoints"),
    # Spring: 'Spring' CS unless followed by a year; 'spring boot' any case
    ("Spring", "Spring Boot microservices"),
    ("Spring", "experience with spring boot"),
    ("Spring", "deep knowledge of Spring"),
    # ML / phrases
    ("Machine learning", "background in ML systems"),
    ("Machine learning", "machine learning pipelines"),
    ("Machine learning", "Machine Learning Engineer role"),
    # RAG
    ("RAG", "production RAG pipelines"),
    ("RAG", "Retrieval-Augmented Generation"),
    ("RAG", "retrieval augmented systems"),
    # MCP
    ("MCP", "built MCP servers"),
    ("MCP", "Model Context Protocol integrations"),
    # AI umbrella
    ("AI (umbrella)", "AI/ML experience"),
    ("AI (umbrella)", "applied Artificial Intelligence"),
    ("AI (umbrella)", "artificial intelligence research"),
    # .NET: URL-collision guard via lookbehind
    (".NET/ASP.NET", "C# and .NET experience"),
    (".NET/ASP.NET", "ASP.NET Core APIs"),
    # JavaScript vs Java word boundaries
    ("JavaScript", "modern JavaScript frameworks"),
    ("Java", "Java backend services"),
    # SQL boundaries
    ("SQL (language)", "strong SQL skills"),
    # assorted multi-form patterns
    ("Kubernetes", "deploy with K8s"),
    ("CI/CD", "own our CI/CD pipelines"),
    ("CI/CD", "continuous integration experience"),
    ("OpenTelemetry", "tracing via OTel"),
    ("Pub/Sub", "GCP Pub/Sub consumers"),
    ("Vector DBs", "store embeddings in pgvector"),
    ("Vector DBs", "Pinecone or Weaviate"),
    ("NoSQL (word)", "SQL and no-sql stores"),
    ("Bash/Shell", "comfortable with shell scripting"),
    ("Express.js", "Node with Express.js"),
    ("Express.js", "expressjs middleware"),
    ("AWS Lambda", "deploy AWS Lambda functions"),
]

NEGATIVE: list[tuple[str, str]] = [
    # Go guards: stopword lookahead + case discipline
    ("Go", "Go to market strategy"),
    ("Go", "Go above and beyond for customers"),
    ("Go", "go the extra mile"),
    ("Go", "we need a go-getter"),
    # React: lowercase English verb
    ("React", "react quickly to incidents"),
    ("React", "able to react to changing priorities"),
    # REST: the deviation-4 fix — lowercase English word must NOT match
    ("REST APIs", "the rest of the team"),
    ("REST APIs", "take the rest of the week off"),
    # Spring: year guard + case discipline
    ("Spring", "Spring 2026 Internship"),
    ("Spring", "spring semester availability"),
    # ML: no boundary inside HTML/XML; lowercase token
    ("Machine learning", "HTML and CSS layouts"),
    ("Machine learning", "XML parsing"),
    # RAG / MCP / AI case discipline and boundaries
    ("RAG", "cleaning with a rag"),
    ("MCP", "the mcp tooling"),  # lowercase token not matched (accepted)
    ("AI (umbrella)", "OpenAI partnership"),  # no boundary inside OpenAI
    ("AI (umbrella)", "FAIR lab alumni"),
    # .NET URL guard
    (".NET/ASP.NET", "visit example.net for details"),
    # JavaScript must not bleed into Java
    ("Java", "JavaScript and TypeScript only"),
    # SQL must not bleed out of product names
    ("SQL (language)", "MySQL administration"),
    ("SQL (language)", "PostgreSQL tuning"),
    # Express undercount guard (the .js is required)
    ("Express.js", "express interest in the role"),
    # OTel boundary
    ("OpenTelemetry", "hotel booking platform"),
    # token-level case discipline: standalone lowercase ml / ai never match
    ("Machine learning", "add 5 ml of reagent"),
    ("AI (umbrella)", "ai-powered tooling"),
]

# Known imperfections carried over from the source pipeline ON PURPOSE.
ACCEPTED_HITS: list[tuple[str, str]] = [
    ("AWS Lambda", "Python lambda functions"),  # conflates AWS Lambda with the keyword
    ("Go", "Our Go-To Guide for onboarding"),  # hyphen defeats the \s+ stopword guard
]

ACCEPTED_MISSES: list[tuple[str, str]] = [
    ("Express.js", "Express experience required"),  # bare 'Express' is never counted
    (".NET/ASP.NET", "VB.NET maintenance"),  # lookbehind rejects a preceding letter
    ("Spring", "the spring framework"),  # lowercase bare 'spring' not matched
]


@pytest.mark.parametrize(("name", "text"), POSITIVE)
def test_positive(taxonomy: Taxonomy, name: str, text: str) -> None:
    assert name in taxonomy.extract(text), f"{name!r} should match: {text!r}"


@pytest.mark.parametrize(("name", "text"), NEGATIVE)
def test_negative(taxonomy: Taxonomy, name: str, text: str) -> None:
    assert name not in taxonomy.extract(text), f"{name!r} should NOT match: {text!r}"


@pytest.mark.parametrize(("name", "text"), ACCEPTED_HITS)
def test_accepted_false_positive(taxonomy: Taxonomy, name: str, text: str) -> None:
    assert name in taxonomy.extract(text)  # documented accepted behavior


@pytest.mark.parametrize(("name", "text"), ACCEPTED_MISSES)
def test_accepted_miss(taxonomy: Taxonomy, name: str, text: str) -> None:
    assert name not in taxonomy.extract(text)  # documented accepted behavior
