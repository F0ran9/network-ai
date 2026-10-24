# -*- coding: utf-8 -*-
"""从转换后的 .vssx (OPC zip) 提取每个 Master 的图标 EMF 并渲染为高清 PNG。

映射链: visio/masters/masters.xml (Master ID -> NameU)
      -> visio/masters/_rels/masters.xml.rels (Master ID -> masterN.xml)
      -> visio/masters/_rels/masterN.xml.rels (-> ../media/imageX.emf)
"""
import os
import re
import sys
import zipfile
import io
import xml.etree.ElementTree as ET
from PIL import Image

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else r'D:/network-ai/topology-config-tool/tools/vss_converted'
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else r'D:/network-ai/topology-config-tool/frontend/src/assets/netequip/icons'
DPI = 384
NS = {'v': 'http://schemas.microsoft.com/office/visio/2012/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
os.makedirs(OUT_DIR, exist_ok=True)


def safe_name(s):
    for ch in '\\/:*?"<>| ()':
        s = s.replace(ch, '_')
    return s


def extract_one(vssx_path):
    base = safe_name(os.path.splitext(os.path.basename(vssx_path))[0])
    z = zipfile.ZipFile(vssx_path)

    # Master ID -> NameU
    masters_xml = ET.fromstring(z.read('visio/masters/masters.xml'))
    id2name = {}
    for m in masters_xml.findall('v:Master', NS):
        mid = m.get('ID')
        name = m.get('NameU') or m.get('Name') or f'master{mid}'
        id2name[mid] = name

    # Master ID N -> visio/masters/masterN.xml -> masterN.xml.rels -> media
    id2part = {mid: f'visio/masters/master{mid}.xml' for mid in id2name}

    count = 0
    for mid, name in id2name.items():
        part = id2part.get(mid)
        if not part or part not in z.namelist():
            continue
        # masterN.xml.rels -> media
        dirn, fn = os.path.split(part)
        relp = f'{dirn}/_rels/{fn}.rels'
        if relp not in z.namelist():
            continue
        rels = ET.fromstring(z.read(relp))
        RELNS = '{http://schemas.openxmlformats.org/package/2006/relationships}'
        img_target = None
        for r in rels.findall(f'{RELNS}Relationship'):
            if 'image' in r.get('Type', ''):
                img_target = r.get('Target')
                break
        if not img_target:
            continue
        media = os.path.normpath(os.path.join(dirn, img_target)).replace('\\', '/')
        if not media.startswith('visio/'):
            media = 'visio/' + media.lstrip('../')
        if media not in z.namelist():
            # 直接拼 ../media/xxx
            media = 'visio/media/' + os.path.basename(img_target)
        if media not in z.namelist():
            print(f'  [MISS] {name}: {img_target}')
            continue
        try:
            im = Image.open(io.BytesIO(z.read(media)))
            im.load(dpi=DPI)
            if im.mode != 'RGB':
                im = im.convert('RGB')
            out = os.path.join(OUT_DIR, f'{base}__{safe_name(name)}.png')
            im.save(out)
            count += 1
        except Exception as e:
            print(f'  [ERR] {name}: {e}')
    return count


def main():
    total = 0
    for f in sorted(os.listdir(SRC_DIR)):
        if not f.endswith('.vssx'):
            continue
        n = extract_one(os.path.join(SRC_DIR, f))
        print(f'{f}: {n} icons')
        total += n
    print(f'\nDONE: {total} icons -> {OUT_DIR}')


if __name__ == '__main__':
    main()
