"""Asyncio entry point for the Guild worker process.

Starts two background loops concurrently:
- PollingEventSource: polls GitHub for updates to active threads
- ClaimingLoop: polls GitHub for new issues labelled guild-claim

Both loops call handle_event when they detect something new.
handle_event opens a fresh session and calls run_event, which assembles
context, asks the decision layer for an action, and dispatches it.
"""
import asyncio
import anthropic

from guild.config import load_config
from guild.db import make_engine, make_session_factory
from guild.github_client import GitHubClient
from guild.event_source import PollingEventSource
from guild.claiming import ClaimingLoop
from guild.worker import run_event


async def main():
    config = load_config()
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)
    github = GitHubClient(token_provider=lambda: config.github_token)
    anthropic_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def handle_event(thread_id: str, event: dict) -> None:
        with session_factory() as session:
            run_event(session, thread_id, event, github, anthropic_client)

    source = PollingEventSource(github, session_factory, config.poll_interval)
    source.on_event(handle_event)

    claiming = ClaimingLoop(github, session_factory, config, handle_event)

    # Run both loops concurrently
    await asyncio.gather(
        asyncio.to_thread(source.start),
        asyncio.to_thread(claiming.start),
    )


def cli_main():  # pragma: no cover
    asyncio.run(main())


# Keep the console script entry point as `guild.main:main` pointing to cli_main
# but also expose main for `python -c "from guild.main import main"` import checks.
def main() -> None:  # type: ignore[misc]
    """Console script entry point."""
    cli_main()
