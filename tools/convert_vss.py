# -*- coding: utf-8 -*-
"""把老格式 .vss 模具批量另存为 .vssx（触发 Visio 内部格式转换，使 Page.Drop 可用）。"""
import os
import sys
import glob
import time
import win32com.client
import pythoncom

RPC_E_CALL_REJECTED = -2147418111

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else r'H:/网络拓扑/NetEquip'
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else r'D:/network-ai/topology-config-tool/tools/vss_converted'
os.makedirs(OUT_DIR, exist_ok=True)


def retry(func, n=40, wait=0.5):
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
        except AttributeError:
            time.sleep(wait)
            continue
    if last:
        raise last
    raise RuntimeError('retry exhausted')


def safe_name(s):
    for ch in '\\/:*?"<>| ()':
        s = s.replace(ch, '_')
    return s


def main():
    app = retry(lambda: win32com.client.Dispatch('Visio.InvisibleApp'))
    app.AlertResponse = 1
    ok, fail = 0, []
    try:
        for vss in sorted(glob.glob(os.path.join(SRC_DIR, '*.vss'))):
            base = safe_name(os.path.splitext(os.path.basename(vss))[0])
            p = os.path.normpath(vss)
            out = os.path.normpath(os.path.join(OUT_DIR, base + '.vssx'))
            if os.path.exists(out) and os.path.getsize(out) > 10000:
                print(f'[SKIP exists] {base}')
                ok += 1
                continue
            try:
                doc = retry(lambda p=p: app.Documents.OpenEx(p, 64))
                retry(lambda o=out: doc.SaveAs(o))
                retry(lambda: doc.Close())
                print(f'[OK] {base} -> {os.path.getsize(out)} bytes')
                ok += 1
            except Exception as e:
                desc = e.excepinfo[2] if isinstance(e, pythoncom.com_error) and e.excepinfo else str(e)
                print(f'[FAIL] {base}: {desc}')
                fail.append(base)
    finally:
        try:
            app.Quit()
        except Exception:
            pass
    print(f'\nDONE: {ok} converted, {len(fail)} failed: {fail}')


if __name__ == '__main__':
    main()
