# -*- coding: utf-8 -*-
"""端到端: 上传原始拓扑图 -> AI 识图 -> 应用到画布 -> 打印节点/链路 -> 截图 + 导出 PNG。"""
import re
import os
import json
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env'),
        encoding='utf-8').read()).group(1).strip() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env')) else ''))
IMG = r'C:/Users/Lenovo/.workbuddy/clipboard-images/clipboard-2026-10-24T05-57-19-957Z-bf4f5d92.jpg'
OUT_PNG = r'D:/network-ai/topology-config-tool/tools/pw_ai_import_export.png'
OUT_CANVAS = r'D:/network-ai/topology-config-tool/tools/pw_ai_import_canvas.png'


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1700, 'height': 950})
        page.on('pageerror', lambda e: print('[PAGEERROR]', str(e)[:200]))
        page.goto(URL, wait_until='networkidle')
        page.locator('#login-password').fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)

        # 直接对隐藏的图片上传 input 设文件 (@change 会触发 AI 识图)
        page.wait_for_selector('#topologyCanvas', timeout=15000)
        page.set_input_files('input[type=file][accept*=".png"]', IMG)
        print('uploaded, waiting AI analysis...')

        # 等待识图完成: 分析报告 tab 出现应用按钮 (最长 3 分钟)
        page.wait_for_selector('text=应用拓扑到画布', timeout=180000)
        time.sleep(1)
        page.click('text=应用拓扑到画布')
        time.sleep(3)

        # 打印识别结果摘要: 节点(category/label/mgmtIp) + 链路(from→to, linkLabel)
        raw = page.evaluate("localStorage.getItem('topo-model')")
        if raw:
            m = json.loads(raw)
            labels = {n['key']: n.get('label', '') for n in m.get('nodeDataArray', [])}
            print('---- NODES ----')
            for n in m.get('nodeDataArray', []):
                if n.get('category') == 'zone':
                    print(f"[ZONE] {n.get('label')}")
                else:
                    print(f"{n.get('category','?'):10s} {n.get('label',''):24s} ip={n.get('mgmtIp','')}")
            print('---- LINKS ----')
            for l in m.get('linkDataArray', []):
                fl = labels.get(l.get('from'), l.get('from'))
                tl = labels.get(l.get('to'), l.get('to'))
                print(f"{fl} -> {tl}   [{l.get('linkLabel','')}]")
        page.locator('#topologyCanvas').screenshot(path=OUT_CANVAS)
        print('canvas screenshot saved')

        # 导出 PNG
        page.click('button:has-text("文件")')
        time.sleep(0.6)
        with page.expect_download() as dl_info:
            page.click('text=导出图片 PNG')
        dl_info.value.save_as(OUT_PNG)
        from PIL import Image
        print('export size:', Image.open(OUT_PNG).size)
        browser.close()


if __name__ == '__main__':
    main()
