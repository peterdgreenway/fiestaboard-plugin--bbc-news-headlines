"""Shared fixtures for BBC News plugin tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_config():
    return {
        "feed": "top",
        "refresh_seconds": 300,
        "headline_index": 0,
        "max_headline_chars": 45,
    }


@pytest.fixture
def sample_rss():
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>BBC News</title>
    <item>
      <title><![CDATA[Independent review announced into murder of student Henry Nowak]]></title>
      <description><![CDATA[Home secretary announces review.]]></description>
      <link>https://www.bbc.co.uk/news/articles/example</link>
      <pubDate>Mon, 26 Oct 2026 16:15:16 GMT</pubDate>
    </item>
    <item>
      <title>Second headline about world events today</title>
      <description>Desc</description>
      <link>https://www.bbc.co.uk/news/articles/two</link>
      <pubDate>Mon, 26 Oct 2026 15:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def mock_response(sample_rss):
    resp = MagicMock()
    resp.content = sample_rss
    resp.raise_for_status = MagicMock()
    return resp
