# -*- coding: utf-8 -*-
"""Shared Playwright helpers for forum scraping."""
from __future__ import annotations


def pass_age_gate(page) -> bool:
    """Click through the 18+ age verification landing page if present."""
    try:
        content = page.content()
    except Exception:
        return False
    if "满18岁" not in content and "If you are over 18" not in content:
        return False
    print("[info] age gate detected, clicking through...")
    for selector in [
        'text="满18岁，请点此进入"',
        'text="If you are over 18, please click here"',
        'a:has-text("满18岁")',
        'a:has-text("over 18")',
    ]:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                el.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                print("[info] age gate passed")
                return True
        except Exception:
            continue
    return False
