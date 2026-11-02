# PikPak vs GuangYa downloads audit (pending submit)

- **Generated (UTC)**: 2026-10-31T23:16:39.557801+00:00
- **GuangYa login**: True
- **PikPak folder**: `downloads` (requested `downloads`)
- **Diff baseline (GuangYa)**: `downloads`
- **Policy**: 
- **Action**: report only — no cloud submit until user approves in chat

## Counts

| Metric | Value |
| --- | ---: |
| PikPak complete files | 426 |
| PikPak deduped 番号 | 412 |
| PikPak file link rows | 426 |
| PikPak links with URL | 426 |
| GuangYa files (recursive) | 623 |
| GuangYa deduped 番号 | 428 |
| **Pending submit** | **1** |
| Pending with resolved link | 1 |
| Pending no link | 0 |
| Pending vs GuangYa union (downloads+jav…) | — |
| 番号 aligned (PikPak ⊆ GuangYa diff folder) | None |

## Link resolution policy

1. Prefer PikPak `GET /drive/v1/files/{id}` → `params.url` (task URL fallback).
2. Else JavDB magnets sorted by `javdb_client.sort_magnets` (rank 1 = best).

## Pending submit (sample first 30)

| 番号 | display name | link source | JavDB rank | has URI |
| --- | --- | --- | ---: | --- |
| SSIS-469 | ssis-469-C.mp4 | pikpak | — | yes |

## New GuangYa downloads (incremental log)

- **Last incremental (UTC)**: 2026-11-02T09:04:37.414748+00:00
- **New this run**: 0
- **Total logged**: 17

| added (UTC) | 番号 | name | link source | url |
| --- | --- | --- | --- | --- |
| 2026-11-02T09:03:52 | SSIS-469 | SSIS-469-U.mp4 | pikpak_report_cache | `magnet:?xt=urn:btih:c8da66e4b8b765cae53bdf34afd74badcfc13a63` |
| 2026-11-02T09:03:52 | START-141 | START-141-UC.mp4 | javdb | `magnet:?xt=urn:btih:6fb1372e7847c3faa40a8d52a7718a2ddaedfbb9` |
| 2026-11-02T09:03:52 | PPPE-301 | PPPE-301-C.mp4 | javdb | `magnet:?xt=urn:btih:c097836ae436e7204d53efd7bed0764fd6863203` |
| 2026-11-02T09:03:52 | PPPE-384 | 489155.com@PPPE-384-C.mp4 | javdb | `magnet:?xt=urn:btih:475ad67034a2a882b0a3f781fdfed2dc97a355f2` |
| 2026-11-02T09:03:52 | PRED-899 | 489155.com@PRED-899-C.mp4 | javdb | `magnet:?xt=urn:btih:c97c980f608ce82916c297b000d1d0dce3603fa6` |
| 2026-11-02T09:03:52 | PRED-384 | pred-384.mp4 | javdb | `magnet:?xt=urn:btih:5ec01ad9a9e157d266d3099d12b2024fabdfde38` |
| 2026-11-02T09:03:52 | PRED-891 | 489155.com@PRED-891.mp4 | javdb | `magnet:?xt=urn:btih:bb70ed1244cafd1f8e72ac240620f1b93f40c8ec` |
| 2026-11-02T09:03:52 | DLDSS-555 | 489155.com@DLDSS-555-C.mp4 | javdb | `magnet:?xt=urn:btih:c783c95f4f458404a7f2723a7819296261adeaef` |
| 2026-11-02T09:03:52 | CAWD-377 | [98t.tv]cawd-377-C.mp4 | javdb | `magnet:?xt=urn:btih:fe5d9b1fe420cef1cb178b7acf84ae22bf44fec2` |
| 2026-11-02T09:03:52 | DLDSS-505 | hhd800.com@DLDSS-505.mp4 | javdb | `magnet:?xt=urn:btih:bebcff0484a058382ab86cdbf0402af4c327f8b4` |
| 2026-11-02T09:03:52 | DLDSS-557 | 489155.com@DLDSS-557-C.mp4 | javdb | `magnet:?xt=urn:btih:bde2a6d672c33f42dbd66086e04335f2dbb5f104` |
| 2026-11-02T09:03:52 | JUR-640 | 489155.com@JUR-640-C.mp4 | javdb | `magnet:?xt=urn:btih:0b2a04e41ee93a4b3e5cbd26445ffd669eb2aa78` |
| 2026-11-02T09:03:52 | JUR-685 | 489155.com@JUR-685.mp4 | javdb | `magnet:?xt=urn:btih:4693fd6ee7571f82a8f9985687049814b236f669` |
| 2026-11-02T09:03:52 | JUR-801 | 489155.com@JUR-801-UC.mp4 | javdb | `magnet:?xt=urn:btih:21b7711b1eee52e35a7251aec674de5012c4ec45` |
| 2026-11-02T09:03:52 | YMDD-506 | 4k688.com@YMDD-506.mp4 | javdb | `magnet:?xt=urn:btih:a0c421ce5fd7234800bee0148441ca3425fa6763` |
| 2026-11-02T09:03:52 | YOCH-015 | yoch-015.mp4 | javdb | `magnet:?xt=urn:btih:f5037f111ea79f695c1d3679264f0e6a86139c35` |
| 2026-11-02T09:03:52 | MIAA-466 | 489155.com@MIAA-466-UC.mp4 | javdb | `magnet:?xt=urn:btih:22472dec9cdef35eb8e5189721bb68212640b711` |
