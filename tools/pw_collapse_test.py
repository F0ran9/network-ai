# -*- coding: utf-8 -*-
"""验证左右面板可折叠/展开"""
import re
import os
import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:5732"
PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env'),
        encoding='utf-8').read()).group(1).strip() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env')) else ''))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(URL)
        await page.wait_for_selector("#login-password", timeout=10000)
        await page.fill("#login-password", PASSWORD)
        await page.click(".login-btn")
        await page.wait_for_timeout(2500)

        async def aside_width(idx):
            return await page.eval_on_selector_all("aside.el-aside",
                "(els, i) => Math.round(els[i].getBoundingClientRect().width)", idx)

        lw0, rw0 = await aside_width(0), await aside_width(1)
        toggles = page.locator(".panel-toggle")
        n = await toggles.count()
        print(f"初始: 左={lw0}px 右={rw0}px 手柄数={n}")
        assert n == 2, "应有 2 个折叠手柄"

        # 收起左侧
        await toggles.nth(0).click()
        await page.wait_for_timeout(500)
        lw1, rw1 = await aside_width(0), await aside_width(1)
        print(f"点左手柄后: 左={lw1}px (应≈0) 右={rw1}px (不变)")
        assert lw1 < 5 and abs(rw1 - rw0) < 3

        # 展开左侧
        await toggles.nth(0).click()
        await page.wait_for_timeout(500)
        lw2 = await aside_width(0)
        print(f"再点左手柄: 左={lw2}px (应≈{lw0})")
        assert abs(lw2 - lw0) < 5

        # 收起右侧
        await toggles.nth(1).click()
        await page.wait_for_timeout(500)
        rw2 = await aside_width(1)
        print(f"点右手柄后: 右={rw2}px (应≈0)")
        assert rw2 < 5

        # 展开右侧
        await toggles.nth(1).click()
        await page.wait_for_timeout(500)
        rw3 = await aside_width(1)
        print(f"再点右手柄: 右={rw3}px (应≈{rw0})")
        assert abs(rw3 - rw0) < 5

        await page.screenshot(path="tools/pw_collapse_test.png")
        print("PASS: 左右面板折叠/展开全部正常")
        await browser.close()

asyncio.run(main())
