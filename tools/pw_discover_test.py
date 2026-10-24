# -*- coding: utf-8 -*-
"""网络自动发现 UI 全流程: 打开对话框 -> 演示扫描 -> 应用拓扑 -> 画布渲染"""
import os
import re
import time
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:5732'
OUT = r'D:/network-ai/topology-config-tool/tools/pw_discover_test.png'

PASSWORD = (os.environ.get('TCT_PASSWORD')
    or (re.search(r'APP_PASSWORD=(.+)', open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env'),
        encoding='utf-8').read()).group(1).strip() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', '.env')) else ''))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    page.goto(URL, wait_until='networkidle')
    page.locator('#login-password').fill(PASSWORD)
    page.locator('.login-btn').click()
    time.sleep(2)
    page.wait_for_selector('#topologyCanvas', timeout=10000)

    # 打开网络发现对话框
    page.click('button:has-text("网络发现")')
    time.sleep(1)
    assert page.locator('.el-dialog:has-text("网络自动发现")').is_visible()

    # 演示模式 + 开始扫描
    page.click('.el-dialog .el-switch')
    page.click('.el-dialog button:has-text("开始扫描")')
    # 等扫描完成 (结果区出现统计)
    page.wait_for_selector('.stats-row', timeout=30000)
    assert page.locator('.diag-item').count() >= 4, '诊断条目不足'
    print('扫描完成: 诊断', page.locator('.diag-item').count(), '条')
    time.sleep(0.5)

    # 应用到画布
    page.click('.el-dialog button:has-text("应用拓扑到画布")')
    time.sleep(3)

    # 验证画布节点数
    n_nodes = page.evaluate("() => window.__topoDiagram.model.nodeDataArray.filter(n => n.category !== 'zone').length")
    n_links = page.evaluate("() => window.__topoDiagram.model.linkDataArray.length")
    print(f'画布: {n_nodes} 设备 / {n_links} 链路')
    assert n_nodes == 10, f'设备数不符: {n_nodes}'
    assert n_links == 9, f'链路数不符: {n_links}'

    # 自动布局后截图
    page.click('button:has-text("布局")')
    time.sleep(2)
    page.screenshot(path=OUT)
    print('PASS: 网络发现 UI 全流程通过 ->', OUT)
    browser.close()
