# GuangYa downloads scrape progress (2026-11-01)

**Stopped (UTC):** 2026-11-01T12:57:00Z — user requested pause; manual scrape to resume later.

## Completed work

| Batch | uploaded_nfo | uploaded_poster | skipped_existing | javdb_errors |
|------:|-------------:|----------------:|-----------------:|-------------:|
| 1 | 50 | 50 | 45 | 0 |

**Totals uploaded:** 50 NFO + 50 poster (1 apply batch).

## Last dry-run (before batch 1 on resume)

- `planned_nfo`: **360**
- `planned_poster`: **360**
- `skipped_existing`: **64**

After batch 1 (~50 uploads), roughly **~310** titles may still need sidecars — confirm with a fresh dry-run before resuming.

## Logs

- `/tmp/jp_downloads_scrape.log`
- `/tmp/jp_downloads_scrape.out`
- `/tmp/jp_scrape_batch_1.json`

## Resume (when ready)

```bash
export PATH="/exec-daemon:$PATH" GUANGYAPAN_DRIVE_LOGIN_MODE=device PYTHONPATH=/workspace/scripts
python3 scripts/guangya_downloads_jav_scrape.py --no-translate --json   # check planned_*
python3 scripts/guangya_downloads_jav_scrape.py --apply --no-translate --limit 30
```

Use tmux session `jp-downloads-scrape` for long batch loops; **do not** use `--force` unless sidecars are missing only (`skip_existing` default).

## Cron

**06:45 Beijing:** GuangYa dedupe + incremental audit remain enabled; **automatic chained scrape disabled** (`GUANGYA_JAV_SCRAPE_CRON=0`).
