import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    github_token: str
    anthropic_api_key: str
    port: int


_REQUIRED = ("DATABASE_URL", "GUILD_WORKER_GITHUB_TOKEN", "ANTHROPIC_API_KEY")


def load_config() -> Config:
    """Load configuration from environment variables (12-factor).

    Raises RuntimeError naming ALL missing required variables at once so the
    operator can fix every gap in a single pass rather than discovering them
    one at a time.
    """
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return Config(
        database_url=os.environ["DATABASE_URL"],
        github_token=os.environ["GUILD_WORKER_GITHUB_TOKEN"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        port=int(os.environ.get("PORT", "8000")),
    )
