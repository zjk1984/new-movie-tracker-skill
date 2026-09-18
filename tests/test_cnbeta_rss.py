# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from datetime import datetime, timezone

from cnbeta_rss import (  # noqa: E402
    NewsItem,
    build_interactive_card,
    build_text_message,
    build_update_markdown,
    filter_by_lookback,
    find_latest_dedup_md,
    find_latest_update_md,
    load_seen_ids,
    parse_feed,
    parse_item_ids_from_update_md,
    resolve_auth_mode,
    resolve_lookback_days,
    resolve_max_items,
    save_state,
    select_new_items,
    write_update_markdown,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cnbeta_sample.rss"


class CnbetaRssTests(unittest.TestCase):
    def test_parse_feed_reads_items(self):
        xml_text = FIXTURE.read_text(encoding="utf-8")
        items = parse_feed(xml_text, feed_url="https://rss.cnbeta.com.tw")
        self.assertGreaterEqual(len(items), 100)
        first = items[0]
        self.assertTrue(first.title)
        self.assertIn("cnbeta.com.tw", first.link)
        self.assertEqual(first.category, "tech")

    def test_select_new_items_skips_seen(self):
        items = [
            NewsItem(
                item_id="a",
                title="A",
                link="https://example.com/a",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
            NewsItem(
                item_id="b",
                title="B",
                link="https://example.com/b",
                published="2026-09-18T11:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
        ]
        fresh = select_new_items(items, {"a"})
        self.assertEqual([item.item_id for item in fresh], ["b"])

    def test_build_messages_include_titles(self):
        item = NewsItem(
            item_id="https://www.cnbeta.com.tw/articles/tech/1.htm",
            title="测试标题",
            link="https://www.cnbeta.com.tw/articles/tech/1.htm",
            published="Fri, 18 Sep 2026 14:17:41 GMT",
            category="tech",
            summary="摘要内容",
            feed_url="https://rss.cnbeta.com.tw",
        )
        text = build_text_message([item], feed_count=1)
        card = build_interactive_card([item], feed_count=1)
        self.assertIn("测试标题", text)
        self.assertIn("测试标题", card["elements"][0]["text"]["content"])

    @patch.dict(
        "os.environ",
        {
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.com/hook",
        },
        clear=False,
    )
    def test_resolve_auth_mode_prefers_app(self):
        self.assertEqual(resolve_auth_mode(), "app")

    @patch.dict(
        "os.environ",
        {"FEISHU_WEBHOOK_URL": "https://example.com/hook"},
        clear=True,
    )
    def test_resolve_auth_mode_webhook_only(self):
        self.assertEqual(resolve_auth_mode(), "webhook")

    @patch("cnbeta_rss.fetch_feed")
    def test_run_fetch_only(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import run

        result = run(
            max_items=3,
            dry_run=False,
            fetch_only=True,
            reset_state=True,
            use_card=True,
        )
        self.assertGreaterEqual(result["fetched_total"], 100)
        self.assertLessEqual(result["new_count"], 3)
        self.assertFalse(result["sent"])
        json.dumps(result)

    def test_resolve_max_items_defaults_to_20(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_max_items(), 20)

    def test_resolve_lookback_days_defaults_to_2(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_lookback_days(), 2)

    def test_filter_by_lookback_keeps_recent_items(self):
        now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        items = [
            NewsItem(
                item_id="recent",
                title="Recent",
                link="https://example.com/recent",
                published="2026-09-17T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
            NewsItem(
                item_id="old",
                title="Old",
                link="https://example.com/old",
                published="2026-09-10T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://rss.cnbeta.com.tw",
            ),
        ]
        filtered = filter_by_lookback(items, lookback_days=2, now=now)
        self.assertEqual([item.item_id for item in filtered], ["recent"])

    def test_parse_item_ids_from_update_md(self):
        md = """# CNBeta 新闻更新

<!-- item-id: https://example.com/a -->
## 1. [科技] A

- **链接**: https://example.com/a
- **时间**: 2026-09-18 10:00:00
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20250918-150000.md"
            path.write_text(md, encoding="utf-8")
            ids = parse_item_ids_from_update_md(path)
        self.assertEqual(ids, {"https://example.com/a"})

    def test_write_update_markdown_archives_previous(self):
        item = NewsItem(
            item_id="https://www.cnbeta.com.tw/articles/tech/2.htm",
            title="新标题",
            link="https://www.cnbeta.com.tw/articles/tech/2.htm",
            published="2026-09-18T12:00:00+00:00",
            category="tech",
            summary="摘要",
            feed_url="https://rss.cnbeta.com.tw",
        )
        previous_content = build_update_markdown(
            [
                NewsItem(
                    item_id="https://www.cnbeta.com.tw/articles/tech/1.htm",
                    title="旧标题",
                    link="https://www.cnbeta.com.tw/articles/tech/1.htm",
                    published="2026-09-18T11:00:00+00:00",
                    category="tech",
                    summary="",
                    feed_url="https://rss.cnbeta.com.tw",
                )
            ],
            feed_count=1,
            previous_filename=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            previous = update_dir / "20250918-140000.md"
            previous.write_text(previous_content, encoding="utf-8")

            with patch("cnbeta_rss.update_filename_for_now", return_value="20250918-150000.md"):
                new_path, archived = write_update_markdown(
                    [item],
                    update_dir=update_dir,
                    previous=previous,
                    feed_count=1,
                )
            self.assertIsNotNone(new_path)
            self.assertTrue(new_path.exists())
            self.assertFalse(previous.exists())
            self.assertIsNotNone(archived)
            self.assertTrue(archived.exists())
            self.assertEqual(find_latest_update_md(update_dir), new_path)
            text = new_path.read_text(encoding="utf-8")
            self.assertIn("新标题", text)
            self.assertIn("上一批: [20250918-140000.md](backup/20250918-140000.md)", text)
            self.assertIn("- **链接**: https://www.cnbeta.com.tw/articles/tech/2.htm", text)

    def test_find_latest_dedup_md_falls_back_to_backup(self):
        item = NewsItem(
            item_id="https://www.cnbeta.com.tw/articles/tech/9.htm",
            title="备份条目",
            link="https://www.cnbeta.com.tw/articles/tech/9.htm",
            published="2026-09-18T12:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            backup_dir = update_dir / "backup"
            backup_dir.mkdir()
            backup_md = backup_dir / "20250918-140000.md"
            backup_md.write_text(
                build_update_markdown([item], feed_count=1, previous_filename=None),
                encoding="utf-8",
            )
            self.assertIsNone(find_latest_update_md(update_dir))
            self.assertEqual(find_latest_dedup_md(update_dir), backup_md)

    def test_load_seen_ids_merges_state_and_markdown(self):
        item = NewsItem(
            item_id="https://example.com/state-only",
            title="State",
            link="https://example.com/state-only",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        md_item = NewsItem(
            item_id="https://example.com/md-only",
            title="MD",
            link="https://example.com/md-only",
            published="2026-09-18T11:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            md_path = update_dir / "20250918-150000.md"
            md_path.write_text(
                build_update_markdown([md_item], feed_count=1, previous_filename=None),
                encoding="utf-8",
            )
            save_state(state_path, [item.item_id])
            seen_ids, previous_md, dedup_md = load_seen_ids(
                update_dir=update_dir,
                state_path=state_path,
                reset_state=False,
            )
        self.assertEqual(previous_md, md_path)
        self.assertEqual(dedup_md, md_path)
        self.assertEqual(
            seen_ids,
            {"https://example.com/state-only", "https://example.com/md-only"},
        )

    @patch("cnbeta_rss.fetch_feed")
    def test_run_dedupes_against_previous_update_md(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import parse_feed, run

        items = parse_feed(mock_fetch.return_value, feed_url="https://rss.cnbeta.com.tw")
        first_id = items[0].item_id
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            previous = update_dir / "20250918-140000.md"
            previous.write_text(
                build_update_markdown([items[0]], feed_count=1, previous_filename=None),
                encoding="utf-8",
            )
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path") as mock_state:
                    state_path = Path(tmp) / "state.json"
                    mock_state.return_value = state_path
                    result = run(
                        max_items=20,
                        dry_run=True,
                        fetch_only=False,
                        reset_state=False,
                        use_card=True,
                        skip_update_md=False,
                    )
        self.assertNotIn(first_id, [item["item_id"] for item in result["items"]])

    @patch("cnbeta_rss.fetch_feed")
    def test_run_second_pass_has_no_overlap_with_first(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import parse_feed, run

        items = parse_feed(mock_fetch.return_value, feed_url="https://rss.cnbeta.com.tw")
        first_batch = items[:20]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.send_items_to_feishu"):
                        with patch(
                            "cnbeta_rss.update_filename_for_now",
                            return_value="20250918-140000.md",
                        ):
                            first = run(
                                max_items=20,
                                dry_run=False,
                                fetch_only=False,
                                reset_state=True,
                                use_card=True,
                            )
                        with patch(
                            "cnbeta_rss.update_filename_for_now",
                            return_value="20250918-150000.md",
                        ):
                            second = run(
                                max_items=20,
                                dry_run=False,
                                fetch_only=False,
                                reset_state=False,
                                use_card=True,
                            )
        first_ids = {item["item_id"] for item in first["items"]}
        second_ids = {item["item_id"] for item in second["items"]}
        self.assertEqual(len(first_ids), 20)
        self.assertGreater(len(second_ids), 0)
        self.assertFalse(first_ids & second_ids)

    @patch("cnbeta_rss.beijing_now")
    @patch("cnbeta_rss.fetch_feed")
    def test_run_all_items_older_than_lookback_pushes_zero(
        self, mock_fetch, mock_beijing_now
    ):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        mock_beijing_now.return_value = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
        from cnbeta_rss import run

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.send_items_to_feishu") as mock_send:
                        result = run(
                            max_items=20,
                            dry_run=False,
                            fetch_only=False,
                            reset_state=True,
                            use_card=True,
                        )
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["within_window_total"], 0)
        self.assertFalse(result["sent"])
        mock_send.assert_not_called()

    @patch("cnbeta_rss.fetch_all_feeds")
    def test_run_mix_old_and_new_only_pushes_recent_unseen(self, mock_fetch_all):
        now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        recent_unseen = NewsItem(
            item_id="https://example.com/recent-unseen",
            title="Recent unseen",
            link="https://example.com/recent-unseen",
            published="2026-09-18T08:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        recent_seen = NewsItem(
            item_id="https://example.com/recent-seen",
            title="Recent seen",
            link="https://example.com/recent-seen",
            published="2026-09-18T07:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        old_unseen = NewsItem(
            item_id="https://example.com/old-unseen",
            title="Old unseen",
            link="https://example.com/old-unseen",
            published="2026-09-01T08:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://rss.cnbeta.com.tw",
        )
        mock_fetch_all.return_value = [recent_unseen, recent_seen, old_unseen]
        from cnbeta_rss import run

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            save_state(state_path, [recent_seen.item_id])
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.beijing_now", return_value=now):
                        with patch("cnbeta_rss.send_items_to_feishu") as mock_send:
                            result = run(
                                max_items=20,
                                dry_run=False,
                                fetch_only=False,
                                reset_state=False,
                                use_card=True,
                            )
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["items"][0]["item_id"], recent_unseen.item_id)
        self.assertTrue(result["sent"])
        mock_send.assert_called_once()
        sent_items = mock_send.call_args.args[0]
        self.assertEqual([item.item_id for item in sent_items], [recent_unseen.item_id])

    @patch("cnbeta_rss.fetch_feed")
    def test_run_dedupes_when_only_backup_md_exists(self, mock_fetch):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        from cnbeta_rss import parse_feed, run

        items = parse_feed(mock_fetch.return_value, feed_url="https://rss.cnbeta.com.tw")
        first_batch = items[:20]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            backup_dir = update_dir / "backup"
            backup_dir.mkdir(parents=True)
            backup_md = backup_dir / "20250918-140000.md"
            backup_md.write_text(
                build_update_markdown(first_batch, feed_count=1, previous_filename=None),
                encoding="utf-8",
            )
            save_state(state_path, [item.item_id for item in first_batch])
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    result = run(
                        max_items=20,
                        dry_run=False,
                        fetch_only=True,
                        reset_state=False,
                        use_card=True,
                    )
        overlap = {item["item_id"] for item in result["items"]} & {
            item.item_id for item in first_batch
        }
        self.assertFalse(overlap)
        self.assertEqual(result["dedup_source"], backup_md.name)


if __name__ == "__main__":
    unittest.main()
