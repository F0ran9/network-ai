# -*- coding: utf-8 -*-
"""网络发现拓扑预览图测试: 演示扫描 -> 截图拓扑预览区 -> 应用到画布仍正常"""
import os
import re
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
OUT = r'D:/network-ai/topology-config-tool/tools/pw_discover_preview.png'

BASE = os.path.dirname(os.path.abspath(__file__))
PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(BASE, '..', 'backend', '.env'), encoding='utf-8').read()).group(1).strip()
        if os.path.exists(os.path.join(BASE, '..', 'backend', '.env')) else ''))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=2)
    page.goto(URL, wait_until='networkidle')
    page.locator('#login-password').fill(PASSWORD)
    page.locator('.login-btn').click()
    time.sleep(2)
    page.wait_for_selector('#topologyCanvas', timeout=10000)

    # 打开网络发现对话框, 演示模式扫描
    page.click('button:has-text("网络发现")')
    time.sleep(1)
    page.click('.el-dialog .el-switch')
    page.click('.el-dialog button:has-text("开始扫描")')
    page.wait_for_selector('.stats-row', timeout=30000)

    # 拓扑预览: SVG 节点/边数量断言
    page.wait_for_selector('.topo-preview svg', timeout=5000)
    n_svg_nodes = page.locator('.topo-preview svg g').count()
    n_svg_edges = page.locator('.topo-preview svg line').count()
    print(f'拓扑预览: {n_svg_nodes} 节点 / {n_svg_edges} 边')
    assert n_svg_nodes == 10, f'预览节点数不符: {n_svg_nodes}'
    assert n_svg_edges == 9, f'预览边数不符: {n_svg_edges}'
    assert page.locator('.preview-legend').is_visible()

    # 截图整个对话框 (含拓扑预览)
    page.locator('.el-dialog').screenshot(path=OUT)

    # 应用到画布流程仍正常
    page.click('.el-dialog button:has-text("应用拓扑到画布")')
    time.sleep(3)
    n_nodes = page.evaluate("() => window.__topoDiagram.model.nodeDataArray.filter(n => n.category !== 'zone').length")
    n_links = page.evaluate("() => window.__topoDiagram.model.linkDataArray.length")
    assert n_nodes == 10 and n_links == 9, f'画布应用异常: {n_nodes}/{n_links}'
    print(f'PASS: 画布 {n_nodes} 设备 / {n_links} 链路 ->', OUT)
    browser.close()
