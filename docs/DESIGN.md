# Design notes

## Scope

Single-user, local-only, one Python process. The product optimizes for a researcher's daily loop:

```text
read → note → hypothesize → experiment → write → export
```

Everything else (auth, cloud sync, vector retrieval, queues, containers) is deliberately out of scope.

## Non-goals

- Multi-user accounts / permissions
- Public network exposure
- Semantic embeddings or vector databases
- Redis / Celery / Nginx / Docker as primary-path dependencies
- SSR frontend
- Microservices

## Storage split

| Data | Home | Rationale |
| --- | --- | --- |
| Long-form notes / ideas / experiments / drafts | Markdown files under `~/research-data` | editable in Obsidian / VS Code, diffable, portable |
| Metadata, relationships, runs, metrics | SQLite WAL | relational queries, transactions |
| Search | SQLite FTS5 `search_fts` | BM25, trigram, no sidecar |
| PDFs | `papers/*.pdf` | durable originals |

The database never stores the only copy of prose unless the user chooses to. Every FTS row and link edge can be regenerated from Markdown plus PDFs.

## Search pipeline

`search_fts` columns:

```text
row_id UNINDEXED, entity_id UNINDEXED, type UNINDEXED, page UNINDEXED, title, body
tokenize = trigram
```

Why `entity_id` and `page` are duplicated from relational tables: chunk hits must be grouped back to the paper and retain the page for citation, without a second query per hit.

Index writes are centralized in `services/indexer.py`. No FTS triggers. This keeps API writes, watcher writes, and full rebuilds on the exact same code path.

Short-query policy:

```python
if len(query) < 3:
    LIKE fallback
else:
    MATCH with escaped quoted terms
```

BM25 weights are configurable. Default title 10 / body 1.

## Relationship pipeline

Sources of edges:

| Source | Relation |
| --- | --- |
| front matter `inspired_by` | `inspired_by` |
| front matter `derived_from` | `derived_from` |
| `[[P0001]]` / `[[I0001]]` / `[[E0001]]` / `[[D0001]]` | `related` |
| `[@bibkey]` in drafts | `cites` |
| `{{run:E0001-R01/...}}` | `uses` |

Edges are rebuilt per source document. The graph endpoint joins only IDs that still resolve to live entities.

Important detail: only canonical documents participate in link extraction (`notes/P0001.md`, `ideas/I0001.md`, `experiments/E0001/notes.md`, `drafts/D0001/main.md`). Export artifacts such as `drafts/D0001/.exports/main.expanded.md` and `README.md` must not overwrite the canonical links.

## Import pipeline

```text
arXiv / DOI / PDF / BibTeX
  → normalize source
  → metadata enrichment (arXiv Atom / Crossref)
  → optional PDF download
  → PyMuPDF text extraction
  → page-aware chunks (~1300 chars)
  → paper row + note template
  → FTS paper + note + chunks
  → background job progress
```

Import runs in a daemon thread. SQLite is WAL with `busy_timeout=5000`, short transactions, and `temp_store=MEMORY` (important on Windows sandboxed/low-integrity processes whose `%TEMP%` may not be writable).

## AI pipeline

No vector store. There are two distinct paths.

### Paper question

1. BM25 over `search_fts` constrained to `entity_id=P0001 AND type=paper_chunk`.
2. Top 8 chunks become the prompt context with page labels.
3. Anthropic SDK generates an answer with `(p.X)` citations.
4. Without an API key, return the BM25 evidence itself and label the mode `local-extractive`.

### Paper summary agent

`backend/app/agents/paper_summarizer.py`:

1. select page-aware evidence for problem / method / evidence / limitation;
2. if `ANTHROPIC_API_KEY` exists, run a strict summary prompt over that evidence;
3. otherwise run a deterministic extractive agent and label the result `local-extractive`;
4. persist every run to `summary_record` (mode, model, evidence JSON, prompt version).

The evidence chain is part of the product, not a debug detail. A summary without traceable pages is not treated as a trustworthy research note. Both API and UI expose the mode and evidence list, and the fallback never pretends to be a model-generated synthesis.

## Export pipeline

```text
draft main.md
  → expand {{run:...}} to local artifact paths
  → collect [@bibkey] into refs.bib
  → pandoc --citeproc
  → HTML / TeX / PDF (tectonic)
```

PDF uses XeTeX via tectonic and a platform CJK font. On this Windows machine `Microsoft YaHei` is used. Error logs are written to `drafts/<id>/.exports/export.log` so 503 responses can include actionable details.

## Concurrency model

- Uvicorn single worker.
- SQLite connection pool small (`pool_size=3`).
- All writes short transactions; no long-held write lock.
- Import jobs daemon threads; one job at a time in practice.
- watchfiles thread performs idempotent reindex only.
- APScheduler daily feed at 08:10 local time.

## Schema evolution

Current MVP bootstraps schema with `SQLModel.metadata.create_all` plus an idempotent FTS virtual table. This is intentional to get a working local baseline fast. Before changing table shapes:

1. add Alembic baseline (`0001_init`) and switch startup to migrations;
2. never hand-edit `app.db`;
3. reindex after FTS schema or tokenizer changes.

## Failure drills

- Delete `app.db` → run `scripts/reindex.py` → search and links restore from Markdown (PDF chunk rows require re-import; source PDFs remain).
- Stop backend → lab SDK writes JSONL → restart backend → next `Run` auto-syncs.
- Corrupt FTS5 → `POST /api/admin/reindex`.
- Backup: SQLite online backup + `PRAGMA integrity_check`; restore drill before trusting it.

## Next phases

1. PDF highlighter (`react-pdf-highlighter-extended`) with rect persistence.
2. Alembic baseline and migration checks in CI.
3. Real training templates and richer run/artifact visualizations.
4. GROBID optional sidecar for scholarly PDF structure.
5. More nuanced feed ranking (citation velocity, author affinity), still keyword-first.
