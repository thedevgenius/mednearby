"""Select the Django settings module from the configured environment."""

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting real environment variables."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "development":
    from .development import *  # noqa: F403
elif ENVIRONMENT == "production":
    from .production import *  # noqa: F403
else:
    raise RuntimeError(
        f"Unsupported ENVIRONMENT={ENVIRONMENT!r}. "
        "Expected 'development' or 'production'."
    )
