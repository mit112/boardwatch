"""The loopback review server (design §7.2, §7.3). Standard library `http.server` only.

`api.py` decides what a field means; this module owns the socket, the token, the headers and the
status codes. Everything below is a security decision that an adversarial review of revision 2
asked for, and each one is annotated with what it defends against, because a header nobody can
explain is a header the next change deletes.

**Bind 127.0.0.1 or refuse.** Not "warn and continue": the whole threat model rests on the socket
being unreachable from the network, and a warning is a thing that scrolls past. `0.0.0.0` and a LAN
address both raise `NonLoopbackBindError` before any socket exists.

**The token is stable per install**, in `{config_dir}/web-token` at mode 0600. A per-launch token
cannot be bookmarked, and it buys nothing anyway: it is handed to the browser opener, so it lands
in that process's argv where any same-user process can read it. What a token genuinely defends
against is a malicious page in the browser reaching loopback by DNS rebinding or a cross-site
form post, and a stable secret sent in a header defeats that just as well. The URL becomes
pinnable, which is worth three fewer actions at the start of every session.

**The token is accepted from the `Authorization` header and from nowhere else.** Not a query
string, not a cookie. A query string reaches server logs, browser history, and the `Referer` of
anything the page links to; accepting it "as a convenience" would quietly undo the reason the
client puts it in the fragment and calls `history.replaceState`. The client sends it as a bearer
header, so there is nothing to be convenient about.

**The `Host` header is checked against the bound authority**, which is the other half of the
rebinding defence: a page on `evil.test` that resolves that name to 127.0.0.1 still sends
`Host: evil.test`, and that is the request this refuses. `Origin` is checked for the same reason
in the other direction, and a preflight — which only a cross-origin caller ever sends — is
refused rather than answered.

**The CSP is a response header and never a `<meta>` tag.** A document-level policy would also
govern the Vite dev server's inline react-refresh preamble and break `npm run dev`; a response
header lets the shipped bundle be locked down while the dev server stays usable. The built
`index.html` carries no inline script and no inline style, so nothing needs relaxing.

**Nothing on this path is logged.** `log_message` is silenced deliberately: the answers panel
serves an address, a phone number and a salary expectation, and even the default request-line log
would write a URL to stderr. If a token ever did arrive in a query string, a log line is exactly
how it would escape.

**Reads open a read-only engine per request; the only writers are the four mark functions.** A
read-only open of a WAL store still creates `-shm` and `-wal` files, so "read-only" here means
this process does not modify the database — it does not mean the data directory can be mounted
read-only, and nothing should advertise that it can.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlsplit

from sqlalchemy import Connection, Engine
from sqlalchemy.exc import OperationalError

from boardwatch.core.clock import utcnow
from boardwatch.delivery.answers import AnswersError
from boardwatch.delivery.api import (
    ApiContext,
    PdfFile,
    PdfIssue,
    answers_payload,
    detail_payload,
    funnel_payload,
    queue_payload,
    resolve_pdf,
    reveal,
    runs_payload,
)
from boardwatch.delivery.queue import reconcile_queue, sync_queue
from boardwatch.store.applications import (
    MarkOutcome,
    MarkResult,
    mark_job_applied,
    mark_job_unapplied,
)
from boardwatch.store.db import (
    WalUnsafeFilesystemError,
    get_engine,
    get_readonly_engine,
)
from boardwatch.store.funnel_queries import job_id_for_posting
from boardwatch.store.queue_state import mark_job_skipped, unmark_job_skipped

#: The one address this server may bind. A frozenset so the refusal reads as a closed catalog
#: rather than as a `!=` somebody can widen without noticing.
LOOPBACK_ADDRESSES = frozenset({"127.0.0.1"})

#: Stable per install, beside the config. Not in the data directory: it is a credential, not data,
#: and the data directory is the thing a user might sync between machines.
TOKEN_FILENAME = "web-token"
TOKEN_MODE = 0o600
TOKEN_BYTES = 32

#: No inline script, no inline style, no remote origin, no framing, no form posts. `default-src
#: 'none'` makes every directive a deliberate addition rather than a leftover.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

#: Two SQLite result codes, by number, from `sqlite3.Error.sqlite_errorcode`. Read as a code and
#: never by matching "database is locked" in a message: this repository classifies at the raise
#: site, and a driver is free to reword its prose.
SQLITE_BUSY = 5
SQLITE_LOCKED = 6

#: A bounded retry, then 503. The point is the bound: `get_engine`'s 5000 ms default would make a
#: contended write look like a hung page, and a stall ending in a traceback is the worst of both.
WRITE_ATTEMPTS = 3
WRITE_BUSY_TIMEOUT_MS = 300
READ_BUSY_TIMEOUT_MS = 500

_ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_QUEUE = re.compile(r"^/api/queue$")
_QUEUE_ITEM = re.compile(r"^/api/queue/(\d+)$")
_QUEUE_ACTION = re.compile(r"^/api/queue/(\d+)/(applied|unapplied|skipped|unskip|reveal)$")
_PDF = re.compile(r"^/api/pdf/(\d+)$")
_RUN = re.compile(r"^/api/runs/(\d+)$")
_ASSET = re.compile(r"^/assets/(.+)$")


class NonLoopbackBindError(RuntimeError):
    """The requested bind address is not loopback. Typed, and raised before any socket exists."""

    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(
            f"refusing to bind {host!r}: the review server serves the owner's answers, résumé "
            f"and third-party job text, and is only ever reachable from this machine. "
            f"Permitted: {', '.join(sorted(LOOPBACK_ADDRESSES))}"
        )


class BundleMissingError(RuntimeError):
    """The built web bundle is absent from the installed package."""


def load_or_create_token(config_dir: Path) -> str:
    """The install's bearer token, created on first use at mode 0600.

    `os.open` with `O_CREAT | O_EXCL` and an explicit mode, rather than `write_text` followed by
    `chmod`: the two-step version leaves the secret world-readable for the window between them,
    and the exclusive create is also what makes two simultaneous first launches produce one token
    instead of racing each other to overwrite it.

    An existing file is trusted as-is and never rewritten. An empty or whitespace-only one is
    treated as absent, because a zero-byte token would authenticate every request that sent
    nothing.
    """
    path = config_dir / TOKEN_FILENAME
    existing = _read_token(path)
    if existing is not None:
        return existing
    config_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, TOKEN_MODE)
    except FileExistsError:
        raced = _read_token(path)
        if raced is not None:
            # Another launch won the race; its token is as good as this one would have been.
            return raced
        # The file exists and holds no usable token, so it is corrupt rather than contended —
        # and re-raising here would brick the command permanently on a single truncated write.
        return _replace_token(path, token)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(token)
    # Windows ignores the `os.open` mode bits, so the mode is asserted rather than assumed.
    os.chmod(path, TOKEN_MODE)
    return token


def _replace_token(path: Path, token: str) -> str:
    """Replace an unusable token file atomically, through a sibling temp file.

    Not a truncate-in-place: that leaves a zero-byte token on disk for the width of the write,
    and a zero-byte token is one `_read_token` reports as absent while a concurrent reader could
    have loaded it. `os.replace` makes the file go from the old content to the new one with no
    observable state in between, and the temp file carries the restrictive mode from creation.
    """
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, TOKEN_MODE)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(token)
    os.chmod(temp, TOKEN_MODE)
    os.replace(temp, path)
    return token


def _read_token(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value or None


def static_root() -> Path:
    """The built bundle's directory inside the installed package.

    Resolved through `importlib.resources.files` on the `boardwatch` package rather than from
    `__file__`, because a `__file__`-relative path is not reachable in every installed layout —
    the same route `eligibility/catalog.py` and `delivery/answers.py` use for their shipped data.
    `boardwatch/web/` carries no `__init__.py` on purpose (it holds no Python), so the traversal
    starts at the package that does.
    """
    return Path(str(files("boardwatch") / "web" / "static"))


@dataclass(frozen=True)
class ServerDeps:
    """Everything a request needs. Frozen: nothing a request does may change what the next
    request is authorised against."""

    ctx: ApiContext
    token: str
    authority: str


class ReviewServer(ThreadingHTTPServer):
    """Threaded so a slow PDF read cannot block the page that asked for it.

    `daemon_threads` because a browser holding a keep-alive connection open must not keep the
    process alive after Ctrl-C.
    """

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, ctx: ApiContext, token: str) -> None:
        host = address[0]
        if host not in LOOPBACK_ADDRESSES:
            raise NonLoopbackBindError(host)
        super().__init__(address, ReviewHandler)
        # AFTER binding, because port 0 means "any free port" and the Host check has to compare
        # against the port that was actually chosen.
        self.deps = ServerDeps(ctx=ctx, token=token, authority=f"{host}:{self.server_address[1]}")

    @property
    def url(self) -> str:
        """The pinnable session URL, token in the FRAGMENT so it never reaches a server log, the
        browser's history, or a `Referer`."""
        return f"http://{self.deps.authority}/#{self.deps.token}"


class ReviewHandler(BaseHTTPRequestHandler):
    """One request. Every path through here ends in exactly one `_send`."""

    protocol_version = "HTTP/1.1"
    server_version = "boardwatch"
    # Suppresses the Python version from every response's `Server` header. Not defence in depth so
    # much as not volunteering the interpreter build to whatever reached this socket.
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        """Silence. See the module docstring: the answers panel is on this path.

        `format` shadows a builtin because the base class named it that; overriding with a
        different name would not override anything.
        """

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_OPTIONS(self) -> None:
        """A preflight is only ever sent by a cross-origin request, and there is no legitimate
        cross-origin caller. Refused without a single `Access-Control-*` header, because answering
        one is what would make the cross-origin request possible."""
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "cross-origin preflight is not served")

    # ------------------------------------------------------------------------------- dispatch

    @property
    def _deps(self) -> ServerDeps:
        return cast(ReviewServer, self.server).deps

    def _dispatch(self, method: str) -> None:
        deps = self._deps
        # Host first: a rebinding attempt should not reach routing, let alone the database.
        if self.headers.get("Host") != deps.authority:
            self._error(HTTPStatus.FORBIDDEN, "unexpected Host")
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{deps.authority}":
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request refused")
            return
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            self._static(method, path)
            return
        if not self._authorised(deps.token):
            self._error(HTTPStatus.UNAUTHORIZED, "a bearer token is required")
            return
        try:
            self._api(method, path)
        except OperationalError as exc:
            if not _is_locked(exc):
                raise
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "the store is busy; try again")
        except FileNotFoundError:
            # `get_readonly_engine` refuses to invent a store it was asked only to read.
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "no store yet; run boardwatch first")
        except WalUnsafeFilesystemError as exc:
            # The read-only opener KEEPS this check, so it fires per request rather than at
            # start-up. Answered rather than allowed to escape: an escaping exception resets the
            # connection, and the browser then shows a network error for a condition that has a
            # precise explanation the owner needs to read.
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))

    def _authorised(self, token: str) -> bool:
        """`Authorization: Bearer <token>`, and nothing else. A token in the query string is not
        looked for and therefore cannot be accepted.

        `compare_digest` so the comparison does not leak the matching prefix length.
        """
        header = self.headers.get("Authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not presented:
            return False
        return secrets.compare_digest(presented, token)

    def _api(self, method: str, path: str) -> None:
        deps = self._deps
        if method == "GET":
            if _QUEUE.match(path):
                self._json(HTTPStatus.OK, self._read(queue_payload))
                return
            if (item := _QUEUE_ITEM.match(path)) is not None:
                self._detail(int(item.group(1)))
                return
            if (pdf := _PDF.match(path)) is not None:
                self._pdf(int(pdf.group(1)))
                return
            if path == "/api/answers":
                self._answers()
                return
            if path == "/api/runs":
                self._json(HTTPStatus.OK, self._read(lambda conn, _ctx: runs_payload(conn)))
                return
            if (run := _RUN.match(path)) is not None:
                payload = funnel_payload(deps.ctx, int(run.group(1)))
                if payload is None:
                    self._error(HTTPStatus.NOT_FOUND, "no funnel artifact for that run")
                    return
                self._json(HTTPStatus.OK, payload)
                return
        if method == "POST" and (action := _QUEUE_ACTION.match(path)) is not None:
            self._action(int(action.group(1)), action.group(2))
            return
        self._error(HTTPStatus.NOT_FOUND, f"{method} {path} is not a route")

    # -------------------------------------------------------------------------------- reading

    def _read(self, work: Any) -> dict[str, Any]:
        """Run one read-only unit of work on a per-request read-only connection.

        The engine is disposed on the way out. An engine holds a connection pool, and one per
        request that is never disposed is one leaked SQLite handle per page load.
        """
        deps = self._deps
        engine = get_readonly_engine(
            deps.ctx.settings.data_dir, busy_timeout_ms=READ_BUSY_TIMEOUT_MS
        )
        try:
            with engine.connect() as conn:
                result: dict[str, Any] = work(conn, deps.ctx)
                return result
        finally:
            engine.dispose()

    def _detail(self, posting_id: int) -> None:
        payload = self._read(
            lambda conn, ctx: {"detail": detail_payload(conn, ctx, posting_id)}
        )["detail"]
        if payload is None:
            self._error(HTTPStatus.NOT_FOUND, "no delivered lead for that posting")
            return
        self._json(HTTPStatus.OK, payload)

    def _answers(self) -> None:
        try:
            self._json(HTTPStatus.OK, self._read(answers_payload))
        except AnswersError as exc:
            # The typed refusal, named. `AnswersViolation` carries no VALUE by construction, so
            # this says which field is wrong without putting its content on the wire.
            self._json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {
                    "issue": str(exc.violation.issue),
                    "message": exc.violation.message,
                    "where": exc.violation.where,
                },
            )

    def _pdf(self, posting_id: int) -> None:
        resolved = self._resolve_pdf(posting_id)
        if isinstance(resolved, PdfIssue):
            status = (
                HTTPStatus.FORBIDDEN
                if resolved is PdfIssue.OUTSIDE_ROOT
                else HTTPStatus.NOT_FOUND
            )
            self._error(status, str(resolved))
            return
        try:
            body = resolved.path.read_bytes()
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, str(PdfIssue.MISSING_FILE))
            return
        self._send(
            HTTPStatus.OK,
            body,
            "application/pdf",
            extra={"Content-Disposition": _disposition(resolved.filename)},
        )

    def _resolve_pdf(self, posting_id: int) -> PdfFile | PdfIssue:
        deps = self._deps
        engine = get_readonly_engine(
            deps.ctx.settings.data_dir, busy_timeout_ms=READ_BUSY_TIMEOUT_MS
        )
        try:
            with engine.connect() as conn:
                return resolve_pdf(conn, deps.ctx, posting_id)
        finally:
            engine.dispose()

    # -------------------------------------------------------------------------------- writing

    def _action(self, posting_id: int, action: str) -> None:
        deps = self._deps
        if action == "reveal":
            self._json(HTTPStatus.OK, reveal(deps.ctx, posting_id))
            return
        if action in ("skipped", "unskip"):
            self._skip(posting_id, skip=action == "skipped")
            return
        result = self._write(
            lambda conn: (
                mark_job_applied(conn, posting_id=posting_id, source="web")
                if action == "applied"
                else mark_job_unapplied(conn, posting_id=posting_id, source="web")
            )
        )
        if result is None:
            return
        if result.outcome is MarkOutcome.NO_POSTING:
            self._error(HTTPStatus.NOT_FOUND, "no such posting")
            return
        if result.outcome is MarkOutcome.NO_JOB:
            self._error(HTTPStatus.CONFLICT, "that posting is not anchored to a job")
            return
        self._reconcile()
        self._json(HTTPStatus.OK, {"outcome": str(result.outcome), "job_id": result.job_id})

    def _skip(self, posting_id: int, *, skip: bool) -> None:
        """Skip state keys on the canonical `job_id`, matching `applications`, so a skip survives
        its posting being revised, closed or regrouped."""

        def work(conn: Connection) -> MarkResult:
            job_id = job_id_for_posting(conn, posting_id)
            if job_id is None:
                return MarkResult(MarkOutcome.NO_POSTING)
            if skip:
                mark_job_skipped(conn, job_id=job_id, at=utcnow())
            else:
                unmark_job_skipped(conn, job_id=job_id)
            return MarkResult(MarkOutcome.TRANSITIONED, job_id=job_id)

        result = self._write(work)
        if result is None:
            return
        if result.outcome is MarkOutcome.NO_POSTING:
            self._error(HTTPStatus.NOT_FOUND, "no such posting")
            return
        self._reconcile()
        self._json(HTTPStatus.OK, {"outcome": "skipped" if skip else "unskipped"})

    def _write(self, work: Any) -> MarkResult | None:
        """The only write path. A bounded retry on a busy store, then 503 — never a five-second
        stall ending in a traceback.

        Returns None when it has already answered the request, so a caller can tell "answered"
        from "here is your result" without an exception crossing the handler boundary. A failure
        that is NOT contention re-raises: a schema fault is not something a retry can fix, and
        collapsing it into 503 would tell the owner to try again forever.
        """
        deps = self._deps
        for _attempt in range(WRITE_ATTEMPTS):
            engine = get_engine(deps.ctx.settings.data_dir, busy_timeout_ms=WRITE_BUSY_TIMEOUT_MS)
            try:
                with engine.begin() as conn:
                    result: MarkResult = work(conn)
                    return result
            except OperationalError as exc:
                if not _is_locked(exc):
                    raise
            finally:
                engine.dispose()
        self._error(HTTPStatus.SERVICE_UNAVAILABLE, "the store is busy; try again")
        return None

    def _reconcile(self) -> None:
        """Move the lead's folder to the drain the database now says it belongs in.

        Reads the store only, so it runs on the read-only engine. Wrapped: the database is
        authoritative and the next sync fixes the filesystem, so a queue that cannot be reconciled
        must never turn a successful write into a failed request.
        """

        def work(conn: Connection, ctx: ApiContext) -> dict[str, Any]:
            return {"moved": reconcile_queue(conn, root=ctx.queue_root).moved}

        try:
            self._read(work)
        except Exception:  # noqa: BLE001 - a filesystem hiccup must not fail a recorded decision
            return

    # -------------------------------------------------------------------------- static bundle

    def _static(self, method: str, path: str) -> None:
        if method != "GET":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "the bundle is read-only")
            return
        root = static_root()
        if path in ("/", "/index.html"):
            self._file(root / "index.html", "text/html; charset=utf-8")
            return
        asset = _ASSET.match(path)
        # The name is matched against a closed character set with no separator in it, so no
        # traversal segment can be expressed; the containment assertion below is what catches a
        # future change to that pattern rather than trusting it forever.
        if asset is None or not _ASSET_NAME.match(asset.group(1)):
            self._error(HTTPStatus.NOT_FOUND, "not a route")
            return
        target = (root / "assets" / asset.group(1)).resolve()
        if not target.is_relative_to(root.resolve()):
            self._error(HTTPStatus.FORBIDDEN, "outside the bundle")
            return
        guessed, _encoding = mimetypes.guess_type(target.name)
        self._file(target, guessed or "application/octet-stream")

    def _file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "the web bundle is not built; run `make web` in a source checkout",
            )
            return
        self._send(HTTPStatus.OK, body, content_type)

    # ------------------------------------------------------------------------------ responding

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(payload, allow_nan=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, status: HTTPStatus, reason: str) -> None:
        """A JSON error, never `send_error`'s HTML page — which echoes the request path into a
        document and would be a reflection sink on a surface whose whole defence is that no
        untrusted page gets to make requests here."""
        self._json(status, {"error": reason})

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def _is_locked(exc: OperationalError) -> bool:
    """A busy or locked store, by SQLite result code rather than by message prose."""
    return getattr(exc.orig, "sqlite_errorcode", None) in (SQLITE_BUSY, SQLITE_LOCKED)


def _disposition(filename: str) -> str:
    """`inline` plus both filename forms.

    Slugging preserves non-ASCII letters, so a real title can produce a name no HTTP header can
    carry in a quoted string. RFC 5987's `filename*` carries the real one and the ASCII `filename`
    is the fallback for anything that does not implement it.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


def prime_queue(ctx: ApiContext) -> None:
    """Reconcile and then sync the queue once, at start-up (design §4.3).

    Both read the database and write only the queue root, so they run on the read-only engine.
    Reconcile first: a folder sitting in the wrong drain has to be classified before sync decides
    whether it needs creating, or sync would build a second folder beside the misplaced one.

    Every failure is swallowed, exactly as the run hook swallows it. The page reads the database,
    not the folders, so a queue that cannot be written is a degraded convenience and never a
    reason to refuse to serve.
    """
    engine: Engine | None = None
    try:
        engine = get_readonly_engine(ctx.settings.data_dir, busy_timeout_ms=READ_BUSY_TIMEOUT_MS)
        with engine.connect() as conn:
            reconcile_queue(conn, root=ctx.queue_root)
            sync_queue(conn, root=ctx.queue_root, owner_name=ctx.owner_name)
    except Exception:  # noqa: BLE001 - a queue failure must never stop the server from serving
        return
    finally:
        if engine is not None:
            engine.dispose()


def build_server(*, ctx: ApiContext, token: str, host: str, port: int) -> ReviewServer:
    """Bind the review server, or refuse. Raises `NonLoopbackBindError` for a non-loopback host."""
    if not static_root().is_dir():
        raise BundleMissingError(
            f"no web bundle at {static_root()}: run `make web` in a source checkout, or "
            "reinstall boardwatch"
        )
    return ReviewServer((host, port), ctx=ctx, token=token)


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "LOOPBACK_ADDRESSES",
    "TOKEN_FILENAME",
    "TOKEN_MODE",
    "BundleMissingError",
    "NonLoopbackBindError",
    "ReviewHandler",
    "ReviewServer",
    "ServerDeps",
    "build_server",
    "load_or_create_token",
    "prime_queue",
    "static_root",
]
