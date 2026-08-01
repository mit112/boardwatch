# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Dependencies come from uv.lock, never from a fresh resolve: two builds of the same tag
# must yield the same dependency tree. `uv export` renders the locked graph as a
# hash-pinned requirements file, and --require-hashes makes pip refuse anything that does
# not match. The package itself is then installed with --no-deps so pip cannot re-resolve
# behind the lock's back.
COPY --from=ghcr.io/astral-sh/uv:0.10.5 /uv /usr/local/bin/uv
COPY . /tmp/boardwatch
RUN uv export --directory /tmp/boardwatch --frozen --no-dev --no-emit-project \
        -o /tmp/requirements.txt \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps /tmp/boardwatch \
    && rm -rf /tmp/boardwatch /tmp/requirements.txt /usr/local/bin/uv

# Run as a non-root user; persist the local SQLite DB under /data (mount a volume
# here and pass `--data-dir /data`).
RUN useradd --create-home --uid 10001 boardwatch \
    && mkdir -p /data && chown boardwatch:boardwatch /data
USER boardwatch
WORKDIR /data
VOLUME ["/data"]

ENTRYPOINT ["boardwatch"]
