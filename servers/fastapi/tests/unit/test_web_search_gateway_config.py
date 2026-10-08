import json
import os

import pytest

from utils import user_config


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    # update_env_with_user_config() writes many variables; keep them local.
    monkeypatch.setattr(os, "environ", os.environ.copy())


def test_cleared_gateway_fields_stay_cleared(monkeypatch, tmp_path):
    config_path = tmp_path / "userConfig.json"
    monkeypatch.setenv("USER_CONFIG_PATH", str(config_path))
    # Values from an earlier save still live in the process environment.
    monkeypatch.setenv("GEMINI_SEARCH_BASE_URL", "https://arckep.example/api/v1")
    monkeypatch.setenv("GEMINI_SEARCH_MODEL", "google-ai-studio/gemini-3.8-flash")
    monkeypatch.setenv("PERPLEXITY_BASE_URL", "https://arckep.example/api/v1")

    config_path.write_text(
        json.dumps(
            {
                "WEB_SEARCH_PROVIDER": "gemini",
                "GEMINI_SEARCH_BASE_URL": "",
                "GEMINI_SEARCH_MODEL": "",
            }
        ),
        encoding="utf-8",
    )
    config = user_config.get_user_config()
    assert config.GEMINI_SEARCH_BASE_URL == ""
    assert config.GEMINI_SEARCH_MODEL == ""
    # Not saved at all: the environment value still applies.
    assert config.PERPLEXITY_BASE_URL == "https://arckep.example/api/v1"

    user_config.update_env_with_user_config()

    assert os.environ["GEMINI_SEARCH_BASE_URL"] == ""
    assert os.environ["GEMINI_SEARCH_MODEL"] == ""


def test_saved_gateway_fields_reach_the_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "userConfig.json"
    monkeypatch.setenv("USER_CONFIG_PATH", str(config_path))
    for key in (
        "GEMINI_SEARCH_API_KEY",
        "GEMINI_SEARCH_BASE_URL",
        "GEMINI_SEARCH_MODEL",
        "PERPLEXITY_BASE_URL",
        "PERPLEXITY_SEARCH_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    config_path.write_text(
        json.dumps(
            {
                "GEMINI_SEARCH_API_KEY": "ark-test-key",
                "GEMINI_SEARCH_BASE_URL": "https://arckep.example/api/v1",
                "PERPLEXITY_SEARCH_MODEL": "perplexity/sonar-pro",
            }
        ),
        encoding="utf-8",
    )

    user_config.update_env_with_user_config()

    assert os.environ["GEMINI_SEARCH_API_KEY"] == "ark-test-key"
    assert os.environ["GEMINI_SEARCH_BASE_URL"] == "https://arckep.example/api/v1"
    assert os.environ["PERPLEXITY_SEARCH_MODEL"] == "perplexity/sonar-pro"
