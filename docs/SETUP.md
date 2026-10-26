# BBC News Headlines — Setup

Display the latest BBC News headline on your Vestaboard, formatted for a **Note** (15×3).

## Enable

1. Open **http://localhost:4420** → **Integrations**
2. Enable **BBC News**
3. Choose a feed (Top, UK, World, Business, Politics, Technology, Science)
4. Optionally set which headline index to show (0 = top story)
5. Click **Save Changes**

No API key is required. Data comes from public BBC RSS feeds.

## Headline length (max 45) & paraphrase

Under **Integrations → BBC News Headlines**:

- **Max headline characters** (default **45**, range 10–45)
- **Shorten mode**: `paraphrase` (default) reworks the line with abbreviations
  and filler removal; `truncate` only cuts at a word boundary
- Hard limit **45** = full Vestaboard Note (15 × 3)

## Headline length (max 45)

Under **Integrations → BBC News Headlines**:

- **Max headline characters** (default **45**, range 10–45)
- 45 characters = full Vestaboard Note capacity (15 × 3)
- Longer BBC titles are abbreviated on a word boundary, then wrapped into three rows

Variables:

| Variable | Meaning |
|----------|---------|
| `headline` | Full original title |
| `headline_truncated` | Uppercase, max 45 chars |
| `headline_short` | Same as truncated (single line) |
| `note_row1` … `note_row3` | Wrapped Note rows (15 each) |

## Note layout (15×3)

Use these variables on a **Note** page:

```
{{bbc_news.note_row1}}
{{bbc_news.note_row2}}
{{bbc_news.note_row3}}
```

Or a single multi-line variable if your page supports it:

```
{{bbc_news.note_block}}
```

The plugin uppercases the headline, strips unsupported characters, and word-wraps into three rows of 15 characters.

### Example (Note)

```
┌───────────────┐
│INDEPENDENT    │
│REVIEW ANNOUNCE│
│INTO MURDER OF │
└───────────────┘
```

## Flagship / longer lines

| Variable | Description |
|----------|-------------|
| `{{bbc_news.headline}}` | Full headline (up to 80 chars) |
| `{{bbc_news.headline_short}}` | Short uppercase line (~45 chars) |
| `{{bbc_news.headline_line1}}` … `line3` | Same wrap as the Note |
| `{{bbc_news.published_short}}` | e.g. `26 Oct 16:15` |
| `{{bbc_news.feed_name}}` | TOP / UK / WORLD / … |

## Install from GitHub

```bash
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/petergreenway/fiestaboard-plugin--bbc-news"}'
```

## Force refresh

**Integrations** → **BBC News** → **Save Changes** (clears cache).

## Feeds

| Setting | RSS URL |
|---------|---------|
| top | https://feeds.bbci.co.uk/news/rss.xml |
| uk | https://feeds.bbci.co.uk/news/uk/rss.xml |
| world | https://feeds.bbci.co.uk/news/world/rss.xml |
| business | https://feeds.bbci.co.uk/news/business/rss.xml |
| politics | https://feeds.bbci.co.uk/news/politics/rss.xml |
| technology | https://feeds.bbci.co.uk/news/technology/rss.xml |
| science | https://feeds.bbci.co.uk/news/science_and_environment/rss.xml |

BBC content remains subject to [BBC terms](https://www.bbc.co.uk/usingthebbc/terms-of-use/).
