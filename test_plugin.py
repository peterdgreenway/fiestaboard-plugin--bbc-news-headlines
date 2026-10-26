"""Tests for bbc_news plugin."""

from unittest.mock import patch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# Minimal stubs so the module can load without full FiestaBoard
fake_base = ModuleType("src.plugins.base")


class PluginBase:
    def __init__(self, manifest=None):
        self.manifest = manifest or {}
        self.config = {}

    def clear_cache(self):
        pass


class PluginResult:
    def __init__(self, available=True, data=None, error=None):
        self.available = available
        self.data = data or {}
        self.error = error


fake_base.PluginBase = PluginBase
fake_base.PluginResult = PluginResult
sys.modules.setdefault("src", ModuleType("src"))
sys.modules.setdefault("src.plugins", ModuleType("src.plugins"))
sys.modules["src.plugins.base"] = fake_base

PLUGIN_PATH = Path(__file__).resolve().parent.parent / "__init__.py"
spec = importlib.util.spec_from_file_location("bbc_news_plugin", PLUGIN_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_wrap_words = mod._wrap_words
_note_block = mod._note_block
_vestaboard_safe = mod._vestaboard_safe
BbcNewsPlugin = mod.BbcNewsPlugin


def test_plugin_id():
    p = BbcNewsPlugin({"id": "bbc_news"})
    assert p.plugin_id == "bbc_news"


def test_wrap_note_width():
    lines = _wrap_words("INDEPENDENT REVIEW ANNOUNCED INTO MURDER", 15, 3)
    assert len(lines) == 3
    assert all(len(line) == 15 for line in lines)
    assert lines[0].strip().startswith("INDEPENDENT")


def test_note_block_three_rows():
    block, r1, r2, r3 = _note_block(
        "Independent review announced into murder of student Henry Nowak"
    )
    assert len(r1) == 15
    assert len(r2) == 15
    assert len(r3) == 15
    assert block.count("\n") == 2
    assert "INDEPENDENT" in r1 or "INDEPENDENT" in r2


def test_vestaboard_safe_upper():
    assert _vestaboard_safe("Hello, World!") == "HELLO, WORLD!"


def test_validate_config_ok(sample_config):
    p = BbcNewsPlugin({})
    assert p.validate_config(sample_config) == []


def test_validate_config_bad_feed():
    p = BbcNewsPlugin({})
    errs = p.validate_config({"feed": "nope", "refresh_seconds": 300, "headline_index": 0})
    assert any("feed" in e for e in errs)


def test_fetch_data_success(sample_config, mock_response):
    p = BbcNewsPlugin({})
    p.config = sample_config
    with patch.object(mod.requests, "get", return_value=mock_response):
        result = p.fetch_data()
    assert result.available is True
    assert "note_row1" in result.data
    assert len(result.data["note_row1"]) == 15
    assert len(result.data["note_row2"]) == 15
    assert len(result.data["note_row3"]) == 15
    assert "INDEPENDENT" in result.data["note_block"]
    assert result.data["source"] == "BBC"
    assert len(result.data["headlines"]) >= 1


def test_fetch_data_network_error(sample_config):
    p = BbcNewsPlugin({})
    p.config = sample_config
    with patch.object(mod.requests, "get", side_effect=Exception("Connection refused")):
        result = p.fetch_data()
    assert result.available is False
    assert result.error
