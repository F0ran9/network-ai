# -*- coding: utf-8 -*-
"""为 README 截取平台界面截图 -> docs/screenshots/"""
import os
import re
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
OUT = r'D:/network-ai/topology-config-tool/docs/screenshots'
os.makedirs(OUT, exist_ok=True)

PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env'),
        encoding='utf-8').read()).group(1).strip() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env')) else ''))

MODEL = {
    "class": "go.GraphLinksModel", "nodeCategoryProperty": "category", "linkKeyProperty": "__gohashid",
    "nodeDataArray": [
        {"key": "isp_dx", "category": "cloud", "label": "电信200M", "role": "cloud", "model": "cloud", "loc": "300 60"},
        {"key": "isp_lt", "category": "cloud", "label": "联通100M", "role": "cloud", "model": "cloud", "loc": "620 60"},
        {"key": "isp_mpls", "category": "cloud", "label": "MPLS专线", "role": "cloud", "model": "cloud", "loc": "900 60"},
        {"key": "lb", "category": "lb", "label": "负载均衡", "role": "router", "model": "F5-BIG-IP", "mgmtIp": "10.94.89.254", "loc": "450 260"},
        {"key": "sdwan", "category": "sdwan", "label": "SDWAN路由器", "role": "router", "model": "SDWAN-Edge", "loc": "880 260"},
        {"key": "fw_out", "category": "firewall", "label": "外网防火墙", "role": "security", "model": "USG6000E", "mgmtIp": "10.94.89.246", "loc": "450 460"},
        {"key": "behavior", "category": "behavior", "label": "上网行为管理", "role": "security", "model": "AC-6000", "mgmtIp": "10.94.89.238", "loc": "450 660"},
        {"key": "core_a", "category": "switch", "label": "商业核心交换机", "role": "core", "model": "S12700E", "mgmtIp": "10.94.89.1", "loc": "350 870"},
        {"key": "core_b", "category": "switch", "label": "消控核心交换机", "role": "core", "model": "S12700E", "mgmtIp": "10.94.89.2", "loc": "700 870"},
        {"key": "acc_a", "category": "switch", "label": "商业接入交换机", "role": "access", "model": "S5735", "loc": "220 1080"},
        {"key": "acc_b", "category": "switch", "label": "弱电间接入交换机", "role": "access", "model": "S5735", "loc": "700 1080"},
        {"key": "ac", "category": "ac", "label": "无线控制器", "role": "wireless", "model": "AC6605", "loc": "480 1080"},
        {"key": "ap", "category": "ap", "label": "无线AP", "role": "wireless", "model": "AP6050DN", "loc": "180 1280"},
        {"key": "server", "category": "server", "label": "虚拟化服务器", "role": "endpoint", "model": "DL380", "loc": "900 1280"},
    ],
    "linkDataArray": [
        {"from": "isp_dx", "to": "lb", "fromPort": "body", "toPort": "body", "linkLabel": "电信200M互联网"},
        {"from": "isp_lt", "to": "lb", "fromPort": "body", "toPort": "body", "linkLabel": "联通100M互联网"},
        {"from": "isp_mpls", "to": "sdwan", "fromPort": "body", "toPort": "body", "linkLabel": "电信MPLS专线"},
        {"from": "lb", "to": "fw_out", "fromPort": "body", "toPort": "body", "linkLabel": "三层互联"},
        {"from": "sdwan", "to": "core_a", "fromPort": "body", "toPort": "body", "linkLabel": "SDWAN隧道"},
        {"from": "fw_out", "to": "behavior", "fromPort": "body", "toPort": "body", "linkLabel": "Trunk"},
        {"from": "behavior", "to": "core_a", "fromPort": "body", "toPort": "body", "linkLabel": "Trunk"},
        {"from": "core_a", "to": "core_b", "fromPort": "body", "toPort": "body", "linkLabel": "横向互联"},
        {"from": "core_a", "to": "acc_a", "fromPort": "body", "toPort": "body", "linkLabel": "Trunk"},
        {"from": "core_b", "to": "acc_b", "fromPort": "body", "toPort": "body", "linkLabel": "Trunk"},
        {"from": "core_a", "to": "ac", "fromPort": "body", "toPort": "body", "linkLabel": "Trunk"},
        {"from": "ac", "to": "ap", "fromPort": "body", "toPort": "body", "linkLabel": "CAPWAP"},
        {"from": "core_b", "to": "server", "fromPort": "body", "toPort": "body", "linkLabel": "Access"},
    ],
}


def login(page):
    page.goto(URL, wait_until='networkidle')
    page.locator('#login-password').fill(PASSWORD)
    page.locator('.login-btn').click()
    time.sleep(2)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=2)

        # 1. 登录页
        page.goto(URL, wait_until='networkidle')
        page.wait_for_selector('#login-password', timeout=10000)
        page.screenshot(path=os.path.join(OUT, 'login.png'))
        print('1 login.png')

        login(page)
        page.evaluate("(m) => localStorage.setItem('topo-model', JSON.stringify(m))", MODEL)
        page.reload(wait_until='networkidle')
        time.sleep(2)
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(3)

        # 2. 拓扑编辑器全景
        page.screenshot(path=os.path.join(OUT, 'editor.png'))
        print('2 editor.png')

        # 3. 设备属性抽屉: 单击外网防火墙
        pos = page.evaluate("""() => {
            const d = window.__topoDiagram
            const n = d.findNodeForKey('fw_out')
            const vp = d.transformDocToView(n.actualBounds.center)
            const r = document.getElementById('topologyCanvas').getBoundingClientRect()
            return { x: r.left + vp.x, y: r.top + vp.y }
        }""")
        page.mouse.click(pos['x'], pos['y'])
        time.sleep(1.5)
        page.screenshot(path=os.path.join(OUT, 'device-properties.png'))
        print('3 device-properties.png')
        page.keyboard.press('Escape')
        time.sleep(0.8)

        # 4. 全局设置 (含平台登录密码修改区)
        page.click('button:has-text("设置")')
        time.sleep(1.2)
        page.screenshot(path=os.path.join(OUT, 'settings.png'))
        print('4 settings.png')
        page.keyboard.press('Escape')
        time.sleep(0.8)

        # 5. 右侧配置面板 (配置 tab)
        page.click('.el-tabs__item:has-text("AI助手")')
        time.sleep(2)
        page.screenshot(path=os.path.join(OUT, 'ai-assistant.png'))
        print('5 ai-assistant.png')

        browser.close()
        print('DONE ->', OUT)


if __name__ == '__main__':
    main()
