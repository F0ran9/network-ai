# -*- coding: utf-8 -*-
"""Playwright 实测: 登录平台 -> 模拟左侧设备拖放到画布 -> 截图验证节点是否有图标。"""
import sys
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
PASSWORD = 'U46e2ci16_MO'
SHOT_DIR = r'D:/network-ai/topology-config-tool/tools'


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 900})
        page.goto(URL, wait_until='networkidle')

        # ---- 登录 ----
        pw_input = page.locator('#login-password')
        pw_input.fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)

        # 等编辑器出现
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(1.5)

        # ---- 模拟 HTML5 拖放: 左侧第一个设备卡 -> 画布 ----
        result = page.evaluate('''() => {
            const card = document.querySelectorAll('.device-card')[0];
            const canvas = document.getElementById('topologyCanvas');
            if (!card || !canvas) return {ok:false, why:'no card/canvas'};
            const r = canvas.getBoundingClientRect();
            const dt = new DataTransfer();
            card.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true, cancelable: true}));
            canvas.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: r.x+400, clientY: r.y+250}));
            canvas.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: r.x+400, clientY: r.y+250}));
            canvas.dispatchEvent(new DragEvent('dragend', {dataTransfer: dt, bubbles: true}));
            return {ok:true, cardText: card.textContent.trim().slice(0,40)};
        }''')
        print('drag result:', result)
        time.sleep(1)

        # ---- 清空画布上的旧内容? 直接截图观察 ----
        canvas_el = page.locator('#topologyCanvas')
        canvas_el.screenshot(path=f'{SHOT_DIR}/pw_canvas_after_drop.png')

        # 再拖一个交换机 (第二组第一个) 和防火墙 (安全设备组)
        result2 = page.evaluate('''() => {
            const cards = document.querySelectorAll('.device-card');
            const canvas = document.getElementById('topologyCanvas');
            const r = canvas.getBoundingClientRect();
            const out = [];
            // 找到"核心交换机"和"安全设备"组的卡片
            let targets = [cards[9], cards[cards.length-1]];
            let i = 0;
            for (const card of targets) {
                if (!card) continue;
                const dt = new DataTransfer();
                card.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true, cancelable: true}));
                const x = r.x + 400 + i*250, y = r.y + 250;
                canvas.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: x, clientY: y}));
                canvas.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true, clientX: x, clientY: y}));
                canvas.dispatchEvent(new DragEvent('dragend', {dataTransfer: dt, bubbles: true}));
                out.push(card.textContent.trim().slice(0,30));
                i++;
            }
            return out;
        }''')
        print('drag2:', result2)
        time.sleep(1)
        canvas_el.screenshot(path=f'{SHOT_DIR}/pw_canvas_after_drop2.png')

        # 读取 GoJS 模型数据 (通过遍历 canvas 元素无法直接拿, 改为检查页面里有无 img 加载失败)
        browser.close()
        print('DONE, screenshots saved')


if __name__ == '__main__':
    main()
