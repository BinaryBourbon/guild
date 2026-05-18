"""Tests for 12-factor config loading (operator item #9)."""
import pytest

from guild.config import Config, load_config


def test_load_config_raises_on_all_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GUILD_WORKER_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GUILD_WORKER_ID", raising=False)
    monkeypatch.delenv("GUILD_REPO", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load_config()


def test_load_config_error_names_all_missing(monkeypatch):
    """Error message lists every missing var so the operator fixes all gaps at once."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.delenv("GUILD_WORKER_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GUILD_WORKER_ID", raising=False)
    monkeypatch.delenv("GUILD_REPO", raising=False)
    with pytest.raises(RuntimeError) as exc:
        load_config()
    msg = str(exc.value)
    assert "GUILD_WORKER_GITHUB_TOKEN" in msg
    assert "ANTHROPIC_API_KEY" in msg


def test_load_config_succeeds_with_all_required(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("GUILD_WORKER_ID", "worker-1")
    monkeypatch.setenv("GUILD_REPO", "owner/repo")
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.database_url == "postgresql+psycopg://user:pass@localhost/db"
    assert cfg.github_token == "ghp_testtoken"
    assert cfg.anthropic_api_key == "sk-ant-test"
    assert cfg.port == 8000  # default
    assert cfg.worker_id == "worker-1"
    assert cfg.guild_repo == "owner/repo"
    assert cfg.poll_interval == 120
    assert cfg.claim_interval == 300


def test_load_config_port_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("GUILD_WORKER_ID", "worker-1")
    monkeypatch.setenv("GUILD_REPO", "owner/repo")
    monkeypatch.setenv("PORT", "9000")
    cfg = load_config()
    assert cfg.port == 9000


def test_load_config_poll_and_claim_intervals(monkeypatch):
    """GUILD_POLL_INTERVAL_SECONDS and GUILD_CLAIM_INTERVAL_SECONDS are configurable."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("GUILD_WORKER_ID", "worker-1")
    monkeypatch.setenv("GUILD_REPO", "owner/repo")
    monkeypatch.setenv("GUILD_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("GUILD_CLAIM_INTERVAL_SECONDS", "180")
    cfg = load_config()
    assert cfg.poll_interval == 60
    assert cfg.claim_interval == 180


def test_load_config_missing_worker_id_and_repo(monkeypatch):
    """GUILD_WORKER_ID and GUILD_REPO are required."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GUILD_WORKER_ID", raising=False)
    monkeypatch.delenv("GUILD_REPO", raising=False)
    with pytest.raises(RuntimeError) as exc:
        load_config()
    msg = str(exc.value)
    assert "GUILD_WORKER_ID" in msg
    assert "GUILD_REPO" in msg
