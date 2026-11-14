# Live end-to-end test

- Timestamp: 2026-11-14 20:52:31
- Base URL: `http://127.0.0.1:8765`
- Checks: **54 passed**
- Duration: 13.6s

| Check | Result | Detail |
| --- | --- | --- |
| health | PASS |  |
| toolchain | PASS | pandoc + tectonic available |
| settings | PASS |  |
| import job complete | PASS | 导入完成 |
| arxiv import | PASS | P0001 |
| paper metadata | PASS | metadata ok |
| pdf chunks | PASS | 38 chunks |
| download PDF | PASS | 2,215,244 bytes |
| PDF content-type | PASS |  |
| paper list | PASS |  |
| FTS search | PASS | 1 hits |
| short query fallback | PASS | 1 hits |
| search result page | PASS | page-aware |
| summary generated | PASS | local-extractive |
| summary evidence | PASS | 4 evidence items |
| summary page citations | PASS |  |
| summary history | PASS |  |
| summary persisted | PASS |  |
| paper ask fallback | PASS | local-extractive |
| annotation create | PASS |  |
| annotation delete | PASS |  |
| note save | PASS |  |
| note indexed | PASS |  |
| idea create | PASS |  |
| idea markdown | PASS |  |
| idea promote | PASS |  |
| run create | PASS | E0001-R01 |
| metrics | PASS |  |
| artifact | PASS |  |
| run compare | PASS |  |
| artifact download | PASS |  |
| draft save | PASS | 21 words |
| draft HTML export | PASS |  |
| draft citation rendered | PASS |  |
| draft PDF export | PASS | 20,512 bytes |
| links | PASS |  |
| graph | PASS |  |
| inbox create | PASS |  |
| inbox list | PASS |  |
| inbox process | PASS |  |
| feed refresh | PASS | {'fetched': 10, 'added': 10, 'updated': 0} |
| feed accept | PASS |  |
| import job complete | PASS | 导入完成 |
| feed ignore | PASS |  |
| import job complete | PASS | 导入完成 |
| PDF upload | PASS | P0003 |
| synthetic summary | PASS | local-extractive |
| import job complete | PASS | 导入完成 |
| PDF duplicate detection | PASS | P0003 |
| settings patch | PASS |  |
| reindex | PASS | 104 rows |
| stats | PASS |  |
| backup | PASS |  |
| backups list | PASS |  |
