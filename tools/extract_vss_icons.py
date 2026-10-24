# -*- coding: utf-8 -*-
"""从 Visio .vss 模具文件提取每个 Master 图形为 SVG + PNG 图标。

用法:
    python extract_vss_icons.py [源目录] [输出目录]
"""
import os
import sys
import glob
import json
import time
import win32com.client
import pythoncom

RPC_E_CALL_REJECTED = -2147418111

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else r'H:/网络拓扑/NetEquip'
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else r'D:/network-ai/topology-config-tool/frontend/src/assets/netequip'
os.makedirs(OUT_DIR, exist_ok=True)

SCALE = 4  # 放大倍数保证 PNG 清晰度


def retry(func, n=40, wait=0.5):
    """COM server 未就绪时返回 RPC_E_CALL_REJECTED / 动态派发失败, 循环重试。"""
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
            # 动态派发在 Visio 忙时可能抛 AttributeError, 重试
            last = None
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
    manifest = []
    try:
        stencil_files = sorted(
            glob.glob(os.path.join(SRC_DIR, '*.vss')) +
            glob.glob(os.path.join(SRC_DIR, '*.vssx')))
        for vss in stencil_files:
            base = safe_name(os.path.splitext(os.path.basename(vss))[0])
            p = os.path.normpath(vss)
            try:
                doc = retry(lambda p=p: app.Documents.OpenEx(p, 64))  # visOpenHidden
            except pythoncom.com_error as e:
                desc = e.excepinfo[2] if e.excepinfo else str(e)
                print(f'[SKIP] {base}: {desc}')
                continue
            cnt = retry(lambda: doc.Masters.Count)
            print(f'== {base}: {cnt} masters ==')
            for i in range(1, cnt + 1):
                try:
                    m = retry(lambda i=i: doc.Masters.Item(i))
                    name = safe_name(m.NameU)
                    tmpdoc = retry(lambda: app.Documents.Add(''))
                    page = retry(lambda: tmpdoc.Pages.Item(1))
                    retry(lambda: page.Drop(m, 2, 2))

                    bb = retry(lambda: shape_bbox(page))
                    x1, y1, x2, y2 = bb
                    w, h = (x2 - x1) or 1.0, (y2 - y1) or 1.0

                    def scale_shape():
                        shape = page.Shapes.Item(1)
                        shape.CellsU('Width').FormulaU = f'{w * SCALE} in'
                        shape.CellsU('Height').FormulaU = f'{h * SCALE} in'
                        shape.CellsU('PinX').FormulaU = f'{(w * SCALE) / 2} in'
                        shape.CellsU('PinY').FormulaU = f'{(h * SCALE) / 2} in'

                    try:
                        retry(scale_shape)
                        pw, ph = w * SCALE + 0.1, h * SCALE + 0.1
                    except Exception:
                        pw, ph = w + 0.1, h + 0.1

                    def resize_page():
                        page.PageSheet.CellsU('PageWidth').FormulaU = f'{pw} in'
                        page.PageSheet.CellsU('PageHeight').FormulaU = f'{ph} in'
                    retry(resize_page)

                    svg_path = os.path.join(OUT_DIR, f'{base}__{name}.svg')
                    png_path = os.path.join(OUT_DIR, f'{base}__{name}.png')
                    try:
                        retry(lambda s=svg_path: page.Export(s))
                    except Exception as e:
                        print(f'  svg fail {name}: {e}')
                    try:
                        retry(lambda s=png_path: page.Export(s))
                    except Exception as e:
                        print(f'  png fail {name}: {e}')
                    manifest.append({
                        'vss': base, 'master': m.NameU, 'index': i,
                        'svg': os.path.basename(svg_path) if os.path.exists(svg_path) else None,
                        'png': os.path.basename(png_path) if os.path.exists(png_path) else None,
                    })
                    print(f'  [{i}] {m.NameU}')
                    retry(lambda: tmpdoc.Close())
                except Exception as e:
                    print(f'  [ERR] master {i}: {e}')
            retry(lambda: doc.Close())
    finally:
        try:
            app.Quit()
        except Exception:
            pass
    with open(os.path.join(OUT_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f'\nDONE: {len(manifest)} masters -> {OUT_DIR}')


def shape_bbox(page):
    """返回页面第一个形状的包围盒 (drawing units)。"""
    shape = page.Shapes.Item(1)
    bb = shape.BoundingBox(0, 0)
    # pywin32 返回 (x1, y1, x2, y2) 或 (retval, x1, y1, x2, y2)
    vals = [v for v in bb if isinstance(v, float)]
    return vals[-4:]


if __name__ == '__main__':
    main()
