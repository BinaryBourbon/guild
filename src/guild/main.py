"""Entry point stub — wired in Slice 5 (asyncio process model).

Declared in pyproject.toml so `pip install -e .` resolves the console script
without errors.  The real implementation (three asyncio coroutines:
PollingEventSource, claiming loop, decision cycle) ships in g2-slice-5-e2e.
"""


def main() -> None:  # pragma: no cover
    raise NotImplementedError("Entry point not yet implemented — see g2-slice-5-e2e")
