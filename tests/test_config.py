import pytest

from pei import config


def test_gitignore_excludes_env_but_keeps_example():
    lines = (config.ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in lines
    assert "!.env.example" in lines


def test_env_example_has_blank_secrets():
    text = (config.ROOT / ".env.example").read_text()
    for key in ("ANTHROPIC_API_KEY", "CONGRESS_API_KEY", "EIA_API_KEY"):
        assert f"{key}=\n" in text


def test_missing_key_error_names_key_only(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EIA_API_KEY"):
        config.api_key("EIA_API_KEY")


def test_keyword_pillars_match_taxonomy():
    keywords = config.load_yaml("keywords.yaml")["pillars"]
    pillars = config.load_yaml("pillars.yaml")["pillars"]
    assert set(keywords) == set(pillars)
