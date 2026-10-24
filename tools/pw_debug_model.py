# -*- coding: utf-8 -*-
"""诊断: 拖放后读取 localStorage 里保存的模型 JSON, 查看节点 category。"""
import re
import os
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env'),
        encoding='utf-8').read()).group(1).strip() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env')) else ''))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 900})
        msgs = []
        page.on('console', lambda m: msgs.append(f'[{m.type}] {m.text}'))
        page.on('pageerror', lambda e: msgs.append(f'[PAGEERROR] {e}'))
        page.goto(URL, wait_until='networkidle')

        page.locator('#login-password').fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(1.5)

        # 清掉旧画布数据(保留登录态)再测
        page.evaluate("""Object.keys(localStorage).filter(k => k.toLowerCase().includes('topo') || k==='topo-counters').forEach(k => localStorage.removeItem(k))""")
        page.reload(wait_until='networkidle')
        time.sleep(2)
        # reload 后可能回到登录页, 需要时再登录一次
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(1)

        r = page.evaluate('''() => {
            const card = document.querySelectorAll('.device-card')[0];
            const canvas = document.getElementById('topologyCanvas');
            const rc = canvas.getBoundingClientRect();
            const dt = new DataTransfer();
            card.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true, cancelable: true}));
            canvas.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: rc.x+400, clientY: rc.y+250}));
            canvas.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: rc.x+400, clientY: rc.y+250}));
            canvas.dispatchEvent(new DragEvent('dragend', {dataTransfer: dt, bubbles: true}));
            return card.textContent.trim().slice(0,30);
        }''')
        print('dragged:', r)
        time.sleep(1.5)

        data = page.evaluate('''() => {
            const keys = Object.keys(localStorage);
            const out = {};
            for (const k of keys) {
                if (k.toLowerCase().includes('topo')) out[k] = localStorage.getItem(k);
            }
            return out;
        }''')
        for k, v in data.items():
            print('KEY:', k)
            print('VALUE:', v[:1500])

        print('---- console ----')
        for m in msgs[-25:]:
            print(m)
        browser.close()


if __name__ == '__main__':
    main()
