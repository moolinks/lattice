# Testing

Lattice has three layers of verification. The live E2E suite runs against a **separate data directory** and never touches `~/research-data`.

## 1. Unit / API tests

```bash
cd backend
uv run pytest -q
uv run ruff check app tests
```

The suite uses a temporary data directory and covers:

- health and FTS initialization;
- paper list/detail, note save, annotation create/delete;
- BM25 search, note indexing and the 1–2 character LIKE fallback;
- idea creation, Markdown file, front matter and links;
- experiment → run → metrics → finish → compare;
- draft save and HTML export;
- settings and full reindex.

## 2. Live end-to-end suite

Start an isolated instance:

```powershell
$env:RESEARCH_DATA_DIR = "$PWD\..\e2e-data"
$env:RESEARCH_HUB_SCHEDULER = "0"
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Run:

```powershell
cd ..
uv run --project backend python scripts/e2e_live.py --base-url http://127.0.0.1:8765
```

The suite performs 54 assertions, including real network operations:

| Area | Checks |
| --- | --- |
| Import / download | arXiv import, job polling, PDF bytes, content-type, page chunks |
| Search | BM25 hit, page-aware result, short-query fallback, note reindex |
| Summary agent | structured output, page evidence, history, `summary_record` persistence |
| Reading | annotations, note save, question fallback |
| Research loop | idea create, promote, run, metrics, artifact, finish, compare |
| Writing | draft save, citation render, HTML export, PDF export |
| Discovery | feed refresh, accept (import), ignore |
| Files | PDF upload, duplicate detection |
| Ops | settings patch, reindex, stats, backup, backup listing |

A report is written to [`E2E_REPORT.md`](E2E_REPORT.md) on every run.

## 3. Browser smoke test

The frontend was checked through Chrome DevTools Protocol at `1600×1100` and `390×844`:

- Today, Library, Import modal, Paper detail, PDF tab, Ideas drawer, Experiment chart, Draft preview, Graph, Settings and command palette all render;
- no `console.error` or uncaught exception on any checked page;
- command palette returns grouped BM25 results;
- mobile layout has no horizontal overflow and the sidebar opens/closes.

## Test data policy

- `backend/tests` uses `tempfile.mkdtemp`.
- `scripts/e2e_live.py` defaults to the `RESEARCH_DATA_DIR` of the isolated instance.
- No research data, PDFs, databases, logs or API keys are committed.
