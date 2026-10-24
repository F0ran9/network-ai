# -*- coding: utf-8 -*-
"""验证标签优化: 预置带长标签的拓扑 -> 截图画布 -> 导出 PNG 查看。"""
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
OUT_PNG = r'D:/network-ai/topology-config-tool/tools/pw_label_test_export.png'


MODEL = {
    "class": "go.GraphLinksModel",
    "nodeCategoryProperty": "category",
    "linkKeyProperty": "__gohashid",
    "nodeDataArray": [
        {"key": "isp_dx", "category": "cloud", "label": "电信接入", "role": "cloud", "model": "cloud", "loc": "300 60"},
        {"key": "isp_lt", "category": "cloud", "label": "联通100M", "role": "cloud", "model": "cloud", "loc": "600 60"},
        {"key": "fw_out", "category": "firewall", "label": "外网防火墙", "role": "security", "model": "USG6000", "loc": "450 260"},
        {"key": "core_a", "category": "switch", "label": "中控室核心交换机", "role": "core", "model": "S7700", "loc": "330 470"},
        {"key": "core_b", "category": "switch", "label": "商业核心交换机", "role": "core", "model": "S7700", "loc": "700 470"},
        {"key": "acc_a", "category": "switch", "label": "弱电间接入交换机", "role": "access", "model": "S5700", "loc": "200 680"},
        {"key": "acc_b", "category": "switch", "label": "商业接入交换机", "role": "access", "model": "S5700", "loc": "760 680"},
        {"key": "ac", "category": "ac", "label": "无线控制器", "role": "controller", "model": "AC6605", "loc": "480 890"},
        {"key": "ap", "category": "ap", "label": "无线AP", "role": "access-point", "model": "AP6050DN", "loc": "200 890"},
    ],
    "linkDataArray": [
        {"from": "isp_dx", "to": "fw_out", "linkLabel": "电信接入至外网防火墙", "fromPort": "body", "toPort": "body"},
        {"from": "isp_lt", "to": "fw_out", "linkLabel": "联通100M接入至外网防火墙", "fromPort": "body", "toPort": "body"},
        {"from": "fw_out", "to": "core_a", "linkLabel": "外网防火墙至中控室核心交换机 10.94.89.254", "fromPort": "body", "toPort": "body"},
        {"from": "fw_out", "to": "core_b", "linkLabel": "外网防火墙至商业核心交换机", "fromPort": "body", "toPort": "body"},
        {"from": "core_a", "to": "acc_a", "linkLabel": "中控室核心至弱电间接入交换机", "fromPort": "body", "toPort": "body"},
        {"from": "core_b", "to": "acc_b", "linkLabel": "商业核心至商业接入交换机", "fromPort": "body", "toPort": "body"},
        {"from": "core_a", "to": "ac", "linkLabel": "办公无线网段 10.94.88.0/24", "fromPort": "body", "toPort": "body"},
        {"from": "ac", "to": "ap", "linkLabel": "CAPWAP隧道", "fromPort": "body", "toPort": "body"},
    ],
}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1700, 'height': 950})
        page.goto(URL, wait_until='networkidle')
        page.locator('#login-password').fill(PASSWORD)
        page.locator('.login-btn').click()
        time.sleep(2)

        # 预置拓扑模型
        page.evaluate("""(m) => {
            Object.keys(localStorage).filter(k => k.toLowerCase().includes('topo') || k==='topo-counters').forEach(k => localStorage.removeItem(k));
            localStorage.setItem('topo-model', JSON.stringify(m));
        }""", MODEL)
        page.reload(wait_until='networkidle')
        time.sleep(2)
        if page.locator('#login-password').count() > 0:
            page.locator('#login-password').fill(PASSWORD)
            page.locator('.login-btn').click()
            time.sleep(2)
        page.wait_for_selector('#topologyCanvas', timeout=10000)
        time.sleep(2)

        page.locator('#topologyCanvas').screenshot(path=r'D:/network-ai/topology-config-tool/tools/pw_label_test_canvas.png')

        # 导出 PNG
        page.click('button:has-text("文件")')
        time.sleep(0.6)
        with page.expect_download() as dl_info:
            page.click('text=导出图片 PNG')
        dl_info.value.save_as(OUT_PNG)
        time.sleep(1)
        from PIL import Image
        print('export size:', Image.open(OUT_PNG).size)
        browser.close()


if __name__ == '__main__':
    main()
