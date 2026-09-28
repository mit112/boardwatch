# syntax=docker/dockerfile:1
FROM python:3.12-slim

# curl is needed to fetch the tectonic release below (tar/gzip ship with the base image);
# poppler-utils provides pdfinfo (page-count gate). python:3.12-slim ships with neither.
RUN apt-get update && apt-get install -y --no-install-recommends curl poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# tectonic — required for the résumé PDF gate (Increment-1). Auto-fetches LaTeX packages on
# demand, so it is pinned to a binary release but not to an exact package snapshot.
ARG TECTONIC_VERSION=0.17.0
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64) t=x86_64-unknown-linux-musl ;; arm64) t=aarch64-unknown-linux-musl ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac; \
    curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${t}.tar.gz" -o /tmp/tectonic.tar.gz; \
    tar -xzf /tmp/tectonic.tar.gz -C /tmp; \
    install -m 0755 /tmp/tectonic /usr/local/bin/tectonic; \
    rm -rf /tmp/tectonic*; \
    tectonic --version; \
    pdfinfo -v

# The runtime user exists before the warm-up below, so the warm-up can run as it.
RUN useradd --create-home --uid 10001 boardwatch

# Warm tectonic's package bundle at build time with a throwaway compile — otherwise the
# first real render in a network-restricted runtime would be forced to fetch hundreds of
# MB of LaTeX packages on demand and fail.
#
# It runs AS `boardwatch`, because tectonic caches under the invoking user's home: warmed as
# root, the bundle sat in /root/.cache, which the runtime user cannot enter. And it compiles
# the résumé template's own preamble, not a bare `article`, which fetches almost none of the
# packages a render needs — the same warm-up the CI typesetting action runs (D-269).
COPY --chown=boardwatch:boardwatch src/boardwatch/tailor/render/templates/resume_base.tex /tmp/resume_base.tex
USER boardwatch
RUN set -eux; \
    cd /tmp; \
    awk '/\\begin\{document\}/{exit} {print}' resume_base.tex > warmup.tex; \
    printf '\\begin{document}x\\end{document}\n' >> warmup.tex; \
    grep -q 'fontspec' warmup.tex; \
    tectonic warmup.tex; \
    pdfinfo warmup.pdf | grep -q '^Pages:'; \
    rm -f resume_base.tex warmup.tex warmup.pdf
USER root

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
RUN mkdir -p /data && chown boardwatch:boardwatch /data
USER boardwatch
WORKDIR /data
VOLUME ["/data"]
# The config dir (config.toml, the role taxonomy `init` writes, résumé files) lives in the same
# volume. Left at its default it sits in the container's home, which `docker run --rm` discards,
# so every setting was lost and the next container ranked without the role filter.
ENV BOARDWATCH_CONFIG_DIR=/data/config

ENTRYPOINT ["boardwatch"]
