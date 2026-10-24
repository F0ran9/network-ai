# -*- coding: utf-8 -*-
"""探测: Visio COM 是否可用, 能否打开 vss 并列出 masters。"""
import time
import win32com.client
import pythoncom

RPC_E_CALL_REJECTED = -2147418111


def retry(func, n=20, wait=0.5):
    last = None
    for _ in range(n):
        try:
            return func()
        except pythoncom.com_error as e:
            last = e
            if e.hresult == RPC_E_CALL_REJECTED:
                time.sleep(wait)
                continue
            raise
    raise last


app = retry(lambda: win32com.client.Dispatch('Visio.InvisibleApp'))
app.AlertResponse = 1
print('app ok')

vss = r'H:/网络拓扑/NetEquip/Cisco Systems Catalyst 3550 (US units).vss'
doc = retry(lambda: app.Documents.OpenEx(vss, 2))
print('opened, masters =', doc.Masters.Count)
for i in range(1, min(doc.Masters.Count, 5) + 1):
    print(' -', doc.Masters.Item(i).NameU)
doc.Close()
app.Quit()
print('OK')
