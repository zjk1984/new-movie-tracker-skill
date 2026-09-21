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
    FeedSource,
    FetchAllResult,
    NewsItem,
    SourceFetchOutcome,
    _canonical_url,
    apply_item_limits,
    build_collapsible_interactive_card,
    build_feishu_card_payload,
    build_feishu_card_payloads,
    build_interactive_card,
    chunk_items_for_collapsible_card,
    count_collapsible_card_elements,
    build_text_message,
    build_update_markdown,
    enrich_item_summary,
    fetch_all_feeds,
    fetch_outcomes_to_dict,
    filter_by_lookback,
    find_latest_dedup_md,
    find_latest_update_md,
    format_fetch_status_summary,
    group_items_by_category,
    load_feed_sources,
    load_seen_ids,
    parse_feed,
    parse_item_ids_from_update_md,
    resolve_auth_mode,
    resolve_lookback_days,
    resolve_max_items,
    resolve_max_items_per_category,
    save_state,
    select_new_items,
    should_use_collapsible_card,
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

        single = [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url="https://rss.cnbeta.com.tw",
                category="tech_cn",
            )
        ]
        with patch("cnbeta_rss.resolve_active_sources", return_value=single):
            result = run(
                max_items=3,
                max_items_per_category=5,
                dry_run=False,
                fetch_only=True,
                reset_state=True,
                use_card=True,
            )
        self.assertGreaterEqual(result["fetched_total"], 100)
        self.assertLessEqual(result["new_count"], 3)
        self.assertFalse(result["sent"])
        json.dumps(result)

    def test_resolve_max_items_defaults_to_50(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_max_items(), 50)

    def test_resolve_max_items_per_category_defaults_to_7(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_max_items_per_category(), 7)

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

        single = [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url="https://rss.cnbeta.com.tw",
                category="tech_cn",
            )
        ]
        items = parse_feed(
            mock_fetch.return_value,
            feed_url="https://rss.cnbeta.com.tw",
            source=single[0],
        )
        first_id = items[0].item_id
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "update"
            update_dir.mkdir()
            previous = update_dir / "20250918-140000.md"
            previous.write_text(
                build_update_markdown([items[0]], feed_count=1, previous_filename=None),
                encoding="utf-8",
            )
            with patch("cnbeta_rss.resolve_active_sources", return_value=single):
                with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                    with patch("cnbeta_rss.resolve_state_path") as mock_state:
                        state_path = Path(tmp) / "state.json"
                        mock_state.return_value = state_path
                        result = run(
                            max_items=20,
                            max_items_per_category=20,
                            dry_run=True,
                            fetch_only=False,
                            reset_state=False,
                            use_card=True,
                            skip_update_md=False,
                        )
        self.assertNotIn(first_id, [item["item_id"] for item in result["items"]])

    @patch("cnbeta_rss.beijing_now")
    @patch("cnbeta_rss.fetch_feed")
    def test_run_second_pass_has_no_overlap_with_first(self, mock_fetch, mock_beijing_now):
        mock_fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        mock_beijing_now.return_value = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        from cnbeta_rss import parse_feed, run

        single = [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url="https://rss.cnbeta.com.tw",
                category="tech_cn",
            )
        ]
        items = parse_feed(
            mock_fetch.return_value,
            feed_url="https://rss.cnbeta.com.tw",
            source=single[0],
        )
        first_batch = items[:20]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_active_sources", return_value=single):
                with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                    with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                        with patch("cnbeta_rss.send_items_to_feishu"):
                            with patch(
                                "cnbeta_rss.update_filename_for_now",
                                return_value="20250918-140000.md",
                            ):
                                first = run(
                                    max_items=20,
                                    max_items_per_category=20,
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
                                    max_items_per_category=20,
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

        single = [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url="https://rss.cnbeta.com.tw",
                category="tech_cn",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_active_sources", return_value=single):
                with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                    with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                        with patch("cnbeta_rss.send_items_to_feishu") as mock_send:
                            result = run(
                                max_items=20,
                                max_items_per_category=5,
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
        mock_fetch_all.return_value = FetchAllResult(
            items=[recent_unseen, recent_seen, old_unseen],
            outcomes=[],
        )
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
                                max_items_per_category=5,
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

        single = [
            FeedSource(
                id="cnbeta",
                name="CNBeta",
                url="https://rss.cnbeta.com.tw",
                category="tech_cn",
            )
        ]
        items = parse_feed(
            mock_fetch.return_value,
            feed_url="https://rss.cnbeta.com.tw",
            source=single[0],
        )
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
            with patch("cnbeta_rss.resolve_active_sources", return_value=single):
                with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                    with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                        result = run(
                            max_items=20,
                            max_items_per_category=20,
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

    def test_load_feed_sources_reads_catalog(self):
        sources = load_feed_sources()
        self.assertGreaterEqual(len(sources), 20)
        categories = {source.category for source in sources}
        self.assertIn("tech_cn", categories)
        self.assertIn("ai", categories)
        self.assertIn("finance_cn", categories)
        self.assertIn("finance_intl", categories)

    @patch.dict(
        "os.environ",
        {"RSS_ENABLED_CATEGORIES": "tech_cn,ai"},
        clear=False,
    )
    def test_load_feed_sources_respects_enabled_categories(self):
        sources = load_feed_sources()
        categories = {source.category for source in sources}
        self.assertTrue(categories.issubset({"tech_cn", "ai"}))
        self.assertIn("tech_cn", categories)

    def test_apply_item_limits_per_category(self):
        items = [
            NewsItem(
                item_id=f"tech-{i}",
                title=f"T{i}",
                link=f"https://example.com/t{i}",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://example.com/feed",
                source_category="tech_cn",
                source_name="A",
            )
            for i in range(8)
        ] + [
            NewsItem(
                item_id=f"ai-{i}",
                title=f"A{i}",
                link=f"https://example.com/a{i}",
                published="2026-09-18T09:00:00+00:00",
                category="ai",
                summary="",
                feed_url="https://example.com/ai",
                source_category="ai",
                source_name="B",
            )
            for i in range(8)
        ]
        limited = apply_item_limits(items, max_items=30, max_items_per_category=3)
        tech_count = sum(1 for item in limited if item.source_category == "tech_cn")
        ai_count = sum(1 for item in limited if item.source_category == "ai")
        self.assertEqual(tech_count, 3)
        self.assertEqual(ai_count, 3)

    def test_apply_item_limits_default_caps_allow_50_total(self):
        categories = [
            "tech_cn",
            "tech_en",
            "politics_econ_cn",
            "politics_econ_intl",
            "finance_cn",
            "finance_intl",
            "ai",
            "insights",
        ]
        items: list[NewsItem] = []
        for cat in categories:
            for i in range(10):
                items.append(
                    NewsItem(
                        item_id=f"{cat}-{i}",
                        title=f"{cat} {i}",
                        link=f"https://example.com/{cat}/{i}",
                        published=f"2026-09-18T{10 - i:02d}:00:00+00:00",
                        category="tech",
                        summary="",
                        feed_url="https://example.com/feed",
                        source_category=cat,
                        source_name="Test",
                    )
                )
        limited = apply_item_limits(
            items,
            max_items=50,
            max_items_per_category=7,
        )
        self.assertEqual(len(limited), 50)

    def test_group_items_by_category_preserves_order(self):
        items = [
            NewsItem(
                item_id="1",
                title="One",
                link="https://example.com/1",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://example.com",
                source_category="tech_cn",
            ),
            NewsItem(
                item_id="2",
                title="Two",
                link="https://example.com/2",
                published="2026-09-18T09:00:00+00:00",
                category="ai",
                summary="",
                feed_url="https://example.com",
                source_category="ai",
            ),
        ]
        grouped = group_items_by_category(items)
        self.assertEqual([label for label, _ in grouped], ["中文科技", "AI"])

    def test_build_update_markdown_includes_category_tags(self):
        item = NewsItem(
            item_id="https://example.com/x",
            title="Tagged",
            link="https://example.com/x",
            published="2026-09-18T12:00:00+00:00",
            category="tech",
            summary="summary",
            feed_url="https://example.com/feed",
            source_category="tech_cn",
            source_name="IT之家",
        )
        md = build_update_markdown([item], feed_count=1, previous_filename=None)
        self.assertIn("<!-- category: tech_cn -->", md)
        self.assertIn("- **分类**: tech_cn", md)
        self.assertIn("### 中文科技", md)

    @patch("cnbeta_rss.fetch_feed")
    def test_fetch_all_feeds_continues_on_single_failure(self, mock_fetch):
        xml_text = FIXTURE.read_text(encoding="utf-8")

        def side_effect(url, **kwargs):
            if "broken" in url:
                raise RuntimeError("boom")
            return xml_text

        mock_fetch.side_effect = side_effect
        sources = [
            FeedSource(id="ok", name="OK", url="https://rss.cnbeta.com.tw", category="tech_cn"),
            FeedSource(id="bad", name="Bad", url="https://broken.example/feed", category="ai"),
        ]
        result = fetch_all_feeds(sources)
        self.assertGreaterEqual(len(result.items), 100)
        self.assertEqual(len(result.outcomes), 2)
        self.assertEqual(result.outcomes[0].status, "success")
        self.assertEqual(result.outcomes[1].status, "failure")

    @patch("cnbeta_rss.fetch_all_feeds")
    def test_run_multi_source_dedupes_across_categories(self, mock_fetch_all):
        now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        shared_link = "https://example.com/shared"
        mock_fetch_all.return_value = FetchAllResult(
            items=[
                NewsItem(
                    item_id=shared_link,
                    title="Shared",
                    link=shared_link,
                    published="2026-09-18T08:00:00+00:00",
                    category="tech",
                    summary="",
                    feed_url="https://example.com/a",
                    source_category="tech_cn",
                    source_name="A",
                ),
                NewsItem(
                    item_id="https://example.com/unique",
                    title="Unique",
                    link="https://example.com/unique",
                    published="2026-09-18T07:00:00+00:00",
                    category="ai",
                    summary="",
                    feed_url="https://example.com/b",
                    source_category="ai",
                    source_name="B",
                ),
            ],
            outcomes=[],
        )
        from cnbeta_rss import run

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            save_state(state_path, [shared_link])
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.beijing_now", return_value=now):
                        with patch("cnbeta_rss.send_items_to_feishu") as mock_send:
                            result = run(
                                max_items=20,
                                max_items_per_category=5,
                                dry_run=False,
                                fetch_only=False,
                                reset_state=False,
                                use_card=True,
                            )
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["items"][0]["item_id"], "https://example.com/unique")
        mock_send.assert_called_once()

    @patch("cnbeta_rss.translate_items_for_output")
    @patch("cnbeta_rss.fetch_all_feeds")
    def test_run_translates_before_send(self, mock_fetch_all, mock_translate):
        now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        english = NewsItem(
            item_id="https://example.com/en",
            title="Fed hike",
            link="https://example.com/en",
            published="2026-09-18T08:00:00+00:00",
            category="finance",
            summary="Markets react",
            feed_url="https://example.com/feed",
            source_category="finance_intl",
        )
        translated = NewsItem(
            item_id=english.item_id,
            title=english.title,
            link=english.link,
            published=english.published,
            category=english.category,
            summary=english.summary,
            feed_url=english.feed_url,
            source_category=english.source_category,
            title_zh="美联储加息",
            summary_zh="市场反应",
        )
        mock_fetch_all.return_value = FetchAllResult(items=[english], outcomes=[])
        mock_translate.return_value = [translated]
        from cnbeta_rss import run

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.beijing_now", return_value=now):
                        with patch("cnbeta_rss.send_items_to_feishu") as mock_send:
                            result = run(
                                max_items=20,
                                max_items_per_category=5,
                                dry_run=False,
                                fetch_only=False,
                                reset_state=True,
                                use_card=True,
                            )
        mock_translate.assert_called_once()
        mock_send.assert_called_once()
        sent_items = mock_send.call_args.args[0]
        self.assertEqual(sent_items[0].title_zh, "美联储加息")
        self.assertEqual(result["items"][0]["title_zh"], "美联储加息")

    def test_canonical_url_strips_tracking_params(self):
        raw = (
            "https://Example.com/path/article?utm_source=twitter&fbclid=abc123"
            "&gclid=track&keep=1"
        )
        canonical = _canonical_url(raw)
        self.assertEqual(canonical, "https://example.com/path/article?keep=1")

    def test_fetch_all_feeds_dedupes_same_article_different_tracking_urls(self):
        base = "https://example.com/news/1"
        sources = [
            FeedSource(id="a", name="A", url="https://feed-a.example/rss", category="tech_cn"),
            FeedSource(id="b", name="B", url="https://feed-b.example/rss", category="tech_en"),
        ]
        item_a = NewsItem(
            item_id=f"{base}?utm_source=a",
            title="Same story",
            link=f"{base}?utm_source=a",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="",
            feed_url=sources[0].url,
            source_category="tech_cn",
        )
        item_b = NewsItem(
            item_id=f"{base}?fbclid=xyz",
            title="Same story",
            link=f"{base}?fbclid=xyz",
            published="2026-09-18T09:00:00+00:00",
            category="tech",
            summary="",
            feed_url=sources[1].url,
            source_category="tech_en",
        )

        def side_effect(url, **kwargs):
            if "feed-a" in url:
                return "<rss/>"
            if "feed-b" in url:
                return "<rss/>"
            raise AssertionError(url)

        with patch("cnbeta_rss.fetch_feed", side_effect=side_effect):
            with patch("cnbeta_rss.parse_feed") as mock_parse:
                mock_parse.side_effect = [[item_a], [item_b]]
                result = fetch_all_feeds(sources)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].published, item_a.published)

    def test_select_new_items_skips_canonical_url_seen(self):
        link = "https://example.com/article/1?utm_source=old"
        seen = {_canonical_url(link)}
        items = [
            NewsItem(
                item_id="https://example.com/article/1?fbclid=new",
                title="Dup",
                link="https://example.com/article/1?fbclid=new",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="",
                feed_url="https://example.com/feed",
            )
        ]
        fresh = select_new_items(items, seen)
        self.assertEqual(fresh, [])

    def test_format_fetch_status_summary(self):
        outcomes = [
            SourceFetchOutcome(
                id="ok",
                name="OK",
                url="https://ok.example/rss",
                status="success",
                item_count=5,
            ),
            SourceFetchOutcome(
                id="bad",
                name="Bad Feed",
                url="https://bad.example/rss",
                status="failure",
                item_count=0,
                error="403",
            ),
            SourceFetchOutcome(
                id="slow",
                name="Slow Feed",
                url="https://slow.example/rss",
                status="timeout",
                item_count=0,
                error="timed out",
            ),
        ]
        summary = format_fetch_status_summary(outcomes)
        self.assertIn("2 feeds failed", summary)
        self.assertIn("Bad Feed", summary)
        self.assertIn("Slow Feed", summary)
        payload = fetch_outcomes_to_dict(outcomes)
        self.assertEqual(payload[1]["status"], "failure")

    @patch("cnbeta_rss.fetch_all_feeds")
    def test_run_includes_fetch_report_in_json(self, mock_fetch_all):
        now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        item = NewsItem(
            item_id="https://example.com/new",
            title="New",
            link="https://example.com/new",
            published="2026-09-18T08:00:00+00:00",
            category="tech",
            summary="",
            feed_url="https://example.com/feed",
            source_category="tech_cn",
        )
        mock_fetch_all.return_value = FetchAllResult(
            items=[item],
            outcomes=[
                SourceFetchOutcome(
                    id="ok",
                    name="OK",
                    url="https://example.com/feed",
                    status="success",
                    item_count=1,
                )
            ],
        )
        from cnbeta_rss import run

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            update_dir = tmp_path / "update"
            state_path = tmp_path / "state.json"
            update_dir.mkdir()
            with patch("cnbeta_rss.resolve_update_dir", return_value=update_dir):
                with patch("cnbeta_rss.resolve_state_path", return_value=state_path):
                    with patch("cnbeta_rss.beijing_now", return_value=now):
                        result = run(
                            max_items=20,
                            max_items_per_category=5,
                            dry_run=False,
                            fetch_only=True,
                            reset_state=True,
                            use_card=True,
                        )
        self.assertEqual(len(result["fetch_report"]), 1)
        self.assertEqual(result["fetch_report"][0]["status"], "success")
        self.assertIn("成功", result["fetch_status_summary"])

    @patch.dict("os.environ", {"FEISHU_COLLAPSIBLE": "1"}, clear=False)
    def test_should_use_collapsible_card_env_toggle(self):
        self.assertTrue(should_use_collapsible_card(1))

    def test_build_feishu_card_payload_uses_collapsible_for_large_batch(self):
        items = [
            NewsItem(
                item_id=f"https://example.com/{i}",
                title=f"Title {i}",
                link=f"https://example.com/{i}",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="summary",
                feed_url="https://example.com/feed",
                source_category="tech_cn",
            )
            for i in range(12)
        ]
        card = build_feishu_card_payload(items, feed_count=3, fetch_footer="1 feeds failed: X")
        self.assertEqual(card.get("schema"), "2.0")
        panel_tags = [
            element["tag"]
            for element in card["body"]["elements"]
            if element.get("tag") == "collapsible_panel"
        ]
        self.assertEqual(len(panel_tags), 12)

    def test_build_feishu_card_payload_compact_for_small_batch(self):
        item = NewsItem(
            item_id="https://example.com/1",
            title="One",
            link="https://example.com/1",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="summary",
            feed_url="https://example.com/feed",
            source_category="tech_cn",
        )
        card = build_feishu_card_payload([item], feed_count=1)
        self.assertNotIn("schema", card)
        self.assertIn("elements", card)

    def test_build_collapsible_interactive_card_includes_footer(self):
        items = [
            NewsItem(
                item_id=f"https://example.com/{i}",
                title=f"Title {i}",
                link=f"https://example.com/{i}",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="summary",
                feed_url="https://example.com/feed",
                source_category="tech_cn",
            )
            for i in range(2)
        ]
        card = build_collapsible_interactive_card(
            items,
            feed_count=1,
            fetch_footer="2 feeds failed: Bad",
        )
        overview = card["body"]["elements"][0]["content"]
        self.assertIn("2 feeds failed: Bad", overview)

    def _sample_news_items(self, count: int, *, categories: list[str] | None = None) -> list[NewsItem]:
        categories = categories or ["tech_cn"]
        return [
            NewsItem(
                item_id=f"https://example.com/{i}",
                title=f"Title {i}",
                link=f"https://example.com/{i}",
                published="2026-09-18T10:00:00+00:00",
                category="tech",
                summary="summary",
                feed_url="https://example.com/feed",
                source_category=categories[i % len(categories)],
            )
            for i in range(count)
        ]

    def test_count_collapsible_card_elements_matches_layout(self):
        items = self._sample_news_items(3, categories=["tech_cn", "ai"])
        self.assertEqual(count_collapsible_card_elements(items), 1 + 2 + 3)

    def test_chunk_items_for_collapsible_card_splits_large_batch(self):
        categories = [
            "finance_cn",
            "insights",
            "politics_econ_intl",
            "tech_cn",
            "finance_intl",
            "tech_en",
            "politics_econ_cn",
            "ai",
        ]
        items = self._sample_news_items(50, categories=categories)
        self.assertEqual(count_collapsible_card_elements(items), 59)

        chunks = chunk_items_for_collapsible_card(items, max_elements=45)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(len(chunk) for chunk in chunks), 50)
        for chunk in chunks:
            self.assertLessEqual(count_collapsible_card_elements(chunk), 45)

    def test_build_feishu_card_payloads_chunks_50_items_under_element_limit(self):
        categories = [
            "finance_cn",
            "insights",
            "politics_econ_intl",
            "tech_cn",
            "finance_intl",
            "tech_en",
            "politics_econ_cn",
            "ai",
        ]
        items = self._sample_news_items(50, categories=categories)
        cards = build_feishu_card_payloads(
            items,
            feed_count=44,
            fetch_footer="采集: 44 成功, 1 空, 0 失败",
        )
        self.assertGreater(len(cards), 1)
        for card in cards:
            self.assertEqual(card.get("schema"), "2.0")
            self.assertLessEqual(len(card["body"]["elements"]), 45)
        footer_cards = [
            card
            for card in cards
            if "采集: 44 成功, 1 空, 0 失败" in card["body"]["elements"][0]["content"]
        ]
        self.assertEqual(len(footer_cards), 1)
        self.assertIn("(2/", cards[-1]["header"]["title"]["content"])

    @patch("cnbeta_rss._fetch_page_excerpt")
    def test_enrich_item_summary_fallback_when_fetch_fails(self, mock_excerpt):
        mock_excerpt.return_value = ""
        item = NewsItem(
            item_id="https://example.com/en",
            title="Short",
            link="https://example.com/en",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="tiny",
            feed_url="https://example.com/feed",
            source_category="tech_en",
        )
        enriched = enrich_item_summary(item)
        self.assertEqual(enriched.summary, "tiny")

    @patch("cnbeta_rss._fetch_page_excerpt")
    def test_enrich_item_summary_replaces_short_summary(self, mock_excerpt):
        mock_excerpt.return_value = "Full article body text " * 20
        item = NewsItem(
            item_id="https://example.com/en",
            title="Short",
            link="https://example.com/en",
            published="2026-09-18T10:00:00+00:00",
            category="tech",
            summary="tiny",
            feed_url="https://example.com/feed",
            source_category="tech_en",
        )
        enriched = enrich_item_summary(item)
        self.assertGreater(len(enriched.summary), 80)
        self.assertIn("Full article body", enriched.summary)


if __name__ == "__main__":
    unittest.main()
