# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Build + install from source (hatchling builds the wheel); .dockerignore keeps
# the build context lean.
COPY . /tmp/boardwatch
RUN pip install --no-cache-dir /tmp/boardwatch && rm -rf /tmp/boardwatch

# Run as a non-root user; persist the local SQLite DB under /data (mount a volume
# here and pass `--data-dir /data`).
RUN useradd --create-home --uid 10001 boardwatch \
    && mkdir -p /data && chown boardwatch:boardwatch /data
USER boardwatch
WORKDIR /data
VOLUME ["/data"]

ENTRYPOINT ["boardwatch"]
