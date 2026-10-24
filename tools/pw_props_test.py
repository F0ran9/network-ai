# -*- coding: utf-8 -*-
"""验证设备属性抽屉扩充字段: 打开详情 -> 编辑型号/厂商/位置等 -> 应用 -> 刷新后仍在。"""
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
PASSWORD = 'U46e2ci16_MO'

MODEL = {
    "class": "go.GraphLinksModel",
    "nodeCategoryProperty": "category",
    "linkKeyProperty": "__gohashid",
    "nodeDataArray": [
        {"key": "fw_out", "category": "firewall", "label": "外网防火墙", "role": "security",
         "model": "USG6000", "mgmtIp": "10.94.89.246", "loc": "450 260"},
    ],
    "linkDataArray": [],
}


def open_drawer(page):
    # 通过调试出口精确定位节点屏幕坐标, 双击打开属性抽屉
    pos = page.evaluate("""() => {
        const d = window.__topoDiagram
        const n = d.findNodeForKey('fw_out')
        const vp = d.transformDocToView(n.actualBounds.center)
        const rect = document.getElementById('topologyCanvas').getBoundingClientRect()
        return { x: rect.left + vp.x, y: rect.top + vp.y }
    }""")
    # 单击节点即打开属性抽屉 (App 监听 selectedNodeData)
    page.mouse.click(pos['x'], pos['y'])
    time.sleep(1)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1700, 'height': 950})
        page.goto(URL, wait_until='networkidle')
        page.locator('#login-password').fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)
        page.evaluate("(m) => localStorage.setItem('topo-model', JSON.stringify(m))", MODEL)
        page.reload(wait_until='networkidle')
        time.sleep(2)
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(2)

        open_drawer(page)
        assert page.locator('.el-drawer').is_visible(), '详情抽屉未打开'

        # 字段齐全性
        required = ['设备标签', '设备类型', '厂商', '设备型号', '网络角色', '描述',
                    '主机名', '管理 IP', '管理 VLAN', '软件版本',
                    '所在位置', '资产编号', '序列号', '设备状态', '维护人']
        text = page.locator('.el-drawer').inner_text()
        missing = [f for f in required if f not in text]
        assert not missing, f'缺少字段: {missing}'
        print('字段齐全: 15 项全部呈现')

        # 编辑: 型号 / 位置 / 序列号 / 软件版本
        page.fill('.el-drawer input[placeholder*="USG6000E"]', 'USG6000E-AC')
        page.fill('.el-drawer input[placeholder*="机柜"]', '核心机房 A02')
        page.fill('.el-drawer input[placeholder*="SN"]', '2102351AXX10P3000123')
        page.fill('.el-drawer input[placeholder*="V500"]', 'V500R005C20')
        page.click('.el-drawer button:has-text("应用")')
        time.sleep(1)

        # 刷新验证持久化
        page.reload(wait_until='networkidle')
        time.sleep(2)
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(2)
        saved = page.evaluate("() => localStorage.getItem('topo-model')")
        import json as _json
        node = _json.loads(saved)['nodeDataArray'][0]
        for k, v in [('model', 'USG6000E-AC'), ('location', '核心机房 A02'),
                     ('serialNumber', '2102351AXX10P3000123'), ('softwareVersion', 'V500R005C20')]:
            assert node.get(k) == v, f'刷新后丢失 {k}: 期望 {v}, 实际 {node.get(k)}'
        print('持久化验证: 型号/位置/序列号/软件版本 刷新后全部保留')

        open_drawer(page)
        page.locator('.el-drawer').screenshot(path=r'D:/network-ai/topology-config-tool/tools/pw_props_test.png')
        print('PASS: 设备属性扩充字段全部生效')
        browser.close()


if __name__ == '__main__':
    main()
