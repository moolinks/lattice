# Security

Lattice is designed to run on `127.0.0.1` for a single user. It has **no authentication** and must not be exposed directly to a public network.

## Reporting

If you find a vulnerability, please open a private security advisory on GitHub rather than a public issue.

## Local data

- The SQLite database, PDFs, Markdown notes and logs live in `~/research-data` by default.
- API keys in the Settings page are stored in `~/research-data/config.json`; the file is never committed.
- The application does not send research content anywhere unless you explicitly call the optional Anthropic summary/ask feature.
- Backups include your research data; treat them as sensitive.
