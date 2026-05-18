"""Tests for 12-factor config loading (operator item #9)."""
import pytest

from guild.config import Config, load_config


def test_load_config_raises_on_all_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GUILD_WORKER_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load_config()


def test_load_config_error_names_all_missing(monkeypatch):
    """Error message lists every missing var so the operator fixes all gaps at once."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.delenv("GUILD_WORKER_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        load_config()
    msg = str(exc.value)
    assert "GUILD_WORKER_GITHUB_TOKEN" in msg
    assert "ANTHROPIC_API_KEY" in msg


def test_load_config_succeeds_with_all_required(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.database_url == "postgresql+psycopg://user:pass@localhost/db"
    assert cfg.github_token == "ghp_testtoken"
    assert cfg.anthropic_api_key == "sk-ant-test"
    assert cfg.port == 8000  # default


def test_load_config_port_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.setenv("GUILD_WORKER_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PORT", "9000")
    cfg = load_config()
    assert cfg.port == 9000
