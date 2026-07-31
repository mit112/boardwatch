import hashlib
import os
import tempfile
from pathlib import Path


class ResponseCache:
    """File-backed response cache for LLM calls keyed by content, prompt version, and model."""

    def __init__(self, dir: Path) -> None:
        """Initialize cache with directory (created if missing).

        Args:
            dir: Cache directory path.
        """
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def key(self, content_hash: str, prompt_version: str, model: str) -> str:
        """Generate stable cache key from three parts.

        Args:
            content_hash: SHA256 of job description text.
            prompt_version: Version identifier for the prompt template.
            model: Model identifier (e.g., 'claude-3-5-sonnet-20241022').

        Returns:
            Stable cache key suitable for use as a filename.
        """
        combined = f"{content_hash}|{prompt_version}|{model}"
        digest = hashlib.sha256(combined.encode()).hexdigest()
        return digest

    def get(self, key: str) -> str | None:
        """Retrieve cached response by key.

        Args:
            key: Cache key returned by key() method.

        Returns:
            Raw response text if found, None on miss.
        """
        cache_path = self.dir / key
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")
        return None

    def put(self, key: str, raw: str) -> None:
        """Store response atomically to avoid partial writes.

        Writes to a temporary file in the cache directory and replaces
        the final key to ensure atomic storage. Uses os.replace for
        cross-platform compatibility with existing keys.

        Args:
            key: Cache key returned by key() method.
            raw: Raw response text to cache.
        """
        cache_path = self.dir / key
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.dir,
                encoding="utf-8",
                delete=False,
            ) as tmp:
                tmp.write(raw)
                tmp_path = Path(tmp.name)
            os.replace(str(tmp_path), str(cache_path))
        except Exception:
            try:
                os.unlink(str(tmp_path))
            except (FileNotFoundError, NameError):
                pass
            raise
