# Contributing

Thanks for taking a look at Lattice. It is intentionally small: a single Python process, SQLite, and Markdown. Please keep that constraint intact.

## Development setup

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd ../frontend
pnpm install
pnpm dev
```

## Before opening a pull request

```bash
cd backend
uv run ruff check app tests
uv run pytest -q

cd ../frontend
pnpm build
```

If you change FTS schema, tokenization, or link extraction, run the live E2E suite against an isolated data directory and update `docs/E2E_REPORT.md`.

## Design constraints

- No login, no multi-user permissions, no public exposure by default.
- No vector database, embeddings, Redis, Celery, Nginx or Docker on the primary path.
- Markdown remains the source of truth for prose.
- Search uses SQLite FTS5/BM25; do not add a second search engine.
- Import, search, summary and export must work without an API key where possible. AI is optional, not a hidden dependency.
- Do not commit personal research data, `app.db`, PDFs, logs or API keys.

## Commit style

Small, focused commits are preferred. Examples:

```text
feat(search): add page-aware chunk grouping
fix(import): dedupe uploaded PDFs by normalized title
docs(readme): document the summary agent
```
