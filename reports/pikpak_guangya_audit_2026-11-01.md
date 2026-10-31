# PikPak vs GuangYa downloads audit (pending submit)

- **Generated (UTC)**: 2026-10-31T23:16:39.557801+00:00
- **GuangYa login**: True
- **Action**: report only — no cloud submit until user approves in chat

## Counts

| Metric | Value |
| --- | ---: |
| PikPak complete files | 426 |
| PikPak deduped 番号 | 412 |
| PikPak file link rows | 426 |
| PikPak links with URL | 426 |
| GuangYa files (recursive) | 418 |
| GuangYa deduped 番号 | 411 |
| **Pending submit** | **1** |
| Pending with resolved link | 1 |
| Pending no link | 0 |

## Link resolution policy

1. Prefer PikPak `GET /drive/v1/files/{id}` → `params.url` (task URL fallback).
2. Else JavDB magnets sorted by `javdb_client.sort_magnets` (rank 1 = best).

## Pending submit (sample first 30)

| 番号 | display name | link source | JavDB rank | has URI |
| --- | --- | --- | ---: | --- |
| SSIS-469 | ssis-469-C.mp4 | pikpak | — | yes |
