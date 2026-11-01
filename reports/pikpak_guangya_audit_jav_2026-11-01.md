# PikPak `JAV` vs GuangYa audit

- **Generated (UTC)**: 2026-11-01T01:06:41.615613+00:00
- **GuangYa login**: True
- **PikPak folder**: `JAV` (requested `jav`)
- **Diff baseline (GuangYa)**: `downloads`
- **Policy**: PikPak `JAV` 番号 pending vs GuangYa `downloads` (recursive paginated). Extra GuangYa folders listed for inventory only.
- **Action**: report only — no cloud submit until user approves in chat

## GuangYa extra folders (inventory)

- **JAV**: 0 files, 0 deduped 番号

## Counts

| Metric | Value |
| --- | ---: |
| PikPak complete files | 1170 |
| PikPak deduped 番号 | 1130 |
| PikPak file link rows | 1170 |
| PikPak links with URL | 1143 |
| GuangYa files (recursive) | 419 |
| GuangYa deduped 番号 | 412 |
| **Pending submit** | **1126** |
| Pending with resolved link | 1125 |
| Pending no link | 1 |
| Pending vs GuangYa union (downloads+jav…) | 1126 |
| 番号 aligned (PikPak ⊆ GuangYa diff folder) | False |

## Link resolution policy

1. Prefer PikPak `GET /drive/v1/files/{id}` → `params.url` (task URL fallback).
2. Else JavDB magnets sorted by `javdb_client.sort_magnets` (rank 1 = best).

## Pending submit (sample first 30)

| 番号 | display name | link source | JavDB rank | has URI |
| --- | --- | --- | ---: | --- |
| AARM-372 | 489155.com@AARM-372.mp4 | pikpak | — | yes |
| ABF-161 | abf-161.mp4 | pikpak | — | yes |
| ABF-175 | ABF-175-uncensored-nyap2p.com.mp4 | pikpak | — | yes |
| ABF-215 | abf-215.mp4 | pikpak | — | yes |
| ABF-362 | 489155.com@ABF-362.mp4 | pikpak | — | yes |
| ABF-364 | 489155.com@ABF-364.mp4 | pikpak | — | yes |
| ABF-382 | 489155.com@ABF-382-UC.mp4 | pikpak | — | yes |
| ABF-390 | 489155.com@ABF-390.mp4 | pikpak | — | yes |
| ABF-395 | 489155.com@ABF-395.mp4 | pikpak | — | yes |
| ADN-060 | ADN-060-C.mp4 | pikpak | — | yes |
| ADN-124 | adn-124-C.mp4 | pikpak | — | yes |
| ADN-142 | adn-142-C.mp4 | pikpak | — | yes |
| ADN-143 | adn-143-C.mp4 | pikpak | — | yes |
| ADN-145 | adn-145-C.mp4 | pikpak | — | yes |
| ADN-194 | adn-194-C.mp4 | pikpak | — | yes |
| ADN-265 | adn-265-C.mp4 | pikpak | — | yes |
| ADN-362 | adn-362-C.mp4 | pikpak | — | yes |
| ADN-529 | gg5.co@ADN-529-C_GG5.mp4 | pikpak | — | yes |
| ADN-531 | gg5.co@ADN-531-C_GG5.mp4 | pikpak | — | yes |
| ADN-533 | gg5.co@ADN-533-C_GG5.mp4 | pikpak | — | yes |
| ADN-536 | ADN-536-C.mp4 | pikpak | — | yes |
| ADN-538 | ADN-538-C.mp4 | pikpak | — | yes |
| ADN-540 | gg5.co@ADN-540-C_GG5.mp4 | pikpak | — | yes |
| ADN-544 | ADN-544-C.mp4 | pikpak | — | yes |
| ADN-545 | ADN-545-UC.mp4 | pikpak | — | yes |
| ADN-546 | ADN-546-C.mp4 | pikpak | — | yes |
| ADN-547 | ADN-547-C.mp4 | pikpak | — | yes |
| ADN-550 | ADN-550-C.mp4 | pikpak | — | yes |
| ADN-555 | ADN-555-C.mp4 | pikpak | — | yes |
| ADN-566 | adn-566.mp4 | pikpak | — | yes |

*(+ 1096 more rows in JSON)*
