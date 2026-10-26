# FiestaBoard plugin: BBC News Headlines

Latest BBC News headlines from public RSS feeds, with a **Vestaboard Note** (15×3) formatted block for the top story.

## Install from Git

```bash
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/petergreenway/fiestaboard-plugin--bbc-news"}'
```

Repository naming follows the FiestaBoard registry convention:

```
fiestaboard-plugin--bbc-news  →  plugin id: bbc_news
```

## Note block (15×3)

| Variable | Use |
|----------|-----|
| `{{bbc_news.note_row1}}` | Row 1 |
| `{{bbc_news.note_row2}}` | Row 2 |
| `{{bbc_news.note_row3}}` | Row 3 |
| `{{bbc_news.note_block}}` | All three rows (`\n`-separated) |

Headlines are uppercased, sanitised for board characters, and word-wrapped to 15 columns × 3 rows.

## Other variables

- `headline` / `headline_short` — full and shortened title  
- `published` / `published_short` — publish time  
- `feed_name` — TOP, UK, WORLD, …  
- `headlines` — array of recent items  

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| feed | top | BBC section |
| refresh_seconds | 300 | Min 120 |
| headline_index | 0 | Which item (0 = top) |

## Development layout

```
fiestaboard-plugin--bbc-news/
├── __init__.py
├── manifest.json
├── README.md
├── LICENSE
├── docs/SETUP.md
└── tests/
```

## License

MIT
