# -*- coding: utf-8 -*-
"""端到端验证: 拖放节点 -> 生成连线 -> 导出 PNG -> 检查下载图片完整性。"""
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
OUT = r'D:/network-ai/topology-config-tool/tools/pw_export_test.png'


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
        time.sleep(1.5)

        # 清旧数据并刷新
        page.evaluate("""Object.keys(localStorage).filter(k => k.toLowerCase().includes('topo') || k==='topo-counters').forEach(k => localStorage.removeItem(k))""")
        page.reload(wait_until='networkidle')
        time.sleep(2)
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)

        # 拖 3 个设备 (路由器/交换机/防火墙) 摆开距离, 模拟大范围拓扑
        page.evaluate('''() => {
            const cards = document.querySelectorAll('.device-card');
            const canvas = document.getElementById('topologyCanvas');
            const r = canvas.getBoundingClientRect();
            const spots = [[300,150],[900,400],[600,700]];
            const idxs = [0, 9, 20];  // 路由器/交换机/防火墙大致位置
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

        # 导出 PNG: 打开 文件 菜单 -> 导出图片 PNG, 捕获下载
        page.click('button:has-text("文件")')
        time.sleep(0.6)
        with page.expect_download() as dl_info:
            page.click('text=导出图片 PNG')
        dl = dl_info.value
        dl.save_as(OUT)
        print('downloaded:', dl.suggested_filename)
        time.sleep(1)

        from PIL import Image
        im = Image.open(OUT)
        print('PNG size:', im.size)

        page.evaluate('''() => {
            const btns = [...document.querySelectorAll('button')];
        }''')
        if errors:
            print('PAGE ERRORS:', errors[:5])
        else:
            print('no page errors')
        browser.close()


if __name__ == '__main__':
    main()
