# syntax=docker/dockerfile:1
FROM python:3.12-slim

# curl + xz-utils are needed to fetch and unpack the typst release below; python:3.12-slim
# ships with neither.
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

# typst — required for the résumé PDF gate (P1a). Pinned to match the page-count query syntax.
ARG TYPST_VERSION=0.15.1
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64) t=x86_64-unknown-linux-musl ;; arm64) t=aarch64-unknown-linux-musl ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac; \
    curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${t}.tar.xz" -o /tmp/typst.tar.xz; \
    tar -xJf /tmp/typst.tar.xz -C /tmp; \
    install -m 0755 "/tmp/typst-${t}/typst" /usr/local/bin/typst; \
    rm -rf /tmp/typst*; \
    typst --version

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
