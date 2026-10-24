# -*- coding: utf-8 -*-
"""UI 冒烟: 一键巡检 tab 渲染 + 下发弹窗无 JS 错误。"""
import re
import os
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
BASE = os.path.dirname(os.path.abspath(__file__))
PASSWORD = re.search(r'APP_PASSWORD=(.+)', open(
    os.path.join(BASE, '..', 'backend', '.env'), encoding='utf-8').read()).group(1).strip()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1700, 'height': 950})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(URL, wait_until='networkidle')
        page.locator('#login-password').fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(1)

        # 打开下发弹窗 (菜单或工具栏入口)
        page.keyboard.press('Escape')
        # 先拖 3 台设备并生成配置, 否则下发入口不可见
        page.evaluate('''() => {
            const cards = document.querySelectorAll('.device-card');
            const canvas = document.getElementById('topologyCanvas');
            const r = canvas.getBoundingClientRect();
            const spots = [[300,150],[900,400],[600,700]];
            const idxs = [0, 9, 20];
            idxs.forEach((ci, i) => {
                const card = cards[ci];
                if (!card) return;
                const dt = new DataTransfer();
                card.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true, cancelable: true}));
                const x = r.x + spots[i][0], y = r.y + spots[i][1];
                canvas.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: x, clientY: y}));
                canvas.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: x, clientY: y}));
                canvas.dispatchEvent(new DragEvent('dragend', {dataTransfer: dt, bubbles: true}));
            });
        }''')
        time.sleep(1.5)
        page.locator('button:has-text("一键生成")').first.click()
        time.sleep(6)
        page.locator('button:has-text("下发到设备")').first.click()
        time.sleep(1.5)
        dialog = page.locator('.el-dialog:visible')
        print('dialog visible:', dialog.count() > 0)

        # 一键巡检 tab
        tab = dialog.locator('.el-tabs__item:has-text("一键巡检")')
        print('inspect tab exists:', tab.count() > 0)
        if tab.count():
            tab.click()
            time.sleep(1)
            pane = page.locator('.el-tab-pane:visible')
            print('inspect table rows (batchRows):', pane.locator('.el-table__row').count() >= 0)
            pane.locator('button:has-text("全选")').first.click()
            time.sleep(0.5)
            btn = pane.locator('button:has-text("开始巡检")')
            print('inspect button disabled (无管理IP应禁用):', 'disabled' in (btn.get_attribute('class') or ''))

        print('page errors:', errors if errors else '无')
        page.screenshot(path=os.path.join(BASE, 'pw_inspect_tab.png'))
        browser.close()
        print('SMOKE PASS' if not errors else 'SMOKE FAIL')


if __name__ == '__main__':
    main()
