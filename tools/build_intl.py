#!/usr/bin/env python3
"""Ghép tools/intl_src.py + public/images/intl/geo.json -> public/data/intl.json (app đọc khi mở mục Quốc tế).
Chạy: python3 tools/build_intl.py
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intl_src import COUNTRIES, CITIES, UPDATED  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, 'public', 'images', 'intl', 'geo.json')
OUT = os.path.join(ROOT, 'public', 'data', 'intl.json')
CAT = {'f': 'food', 'c': 'check', 's': 'sight'}

geo = json.load(open(GEO, encoding='utf-8')) if os.path.exists(GEO) else {}


def img(g):
    return {'f': g['f'], 'page': g.get('page'), 'credit': g.get('credit')} if g and g.get('f') else None


cities, miss = [], []
for c in CITIES:
    g = geo.get('c-' + c['id'], {})
    places = []
    for i, p in enumerate(c['places']):
        pid = f"{c['id']}-{i + 1}"
        pg = geo.get(pid, {})
        extra = p[4] if len(p) > 4 else {}
        lat, lng = pg.get('lat'), pg.get('lng')
        if 'll' in extra:                      # tọa độ ghi tay (khi Wikipedia không có)
            lat, lng = extra['ll']
        if lat is None:
            miss.append(f'{pid} {p[1]}')
        places.append({'id': pid, 'cat': CAT[p[0]], 'name': p[1], 'why': p[3], 'price': extra.get('price', ''), 'tip': extra.get('tip', ''),
                       'lat': lat, 'lng': lng, 'wp': pg.get('wp'), 'img': img(pg)})
    pts = [p for p in places if p['lat'] is not None]
    clat = g.get('lat') if g.get('lat') is not None else (sum(p['lat'] for p in pts) / len(pts) if pts else None)
    clng = g.get('lng') if g.get('lng') is not None else (sum(p['lng'] for p in pts) / len(pts) if pts else None)
    cimg = img(g) or next((p['img'] for p in places if p['img']), None)
    cities.append({'id': c['id'], 'country': c['country'], 'name': c['name'], 'local': c.get('local', ''), 'intro': c['intro'],
                   'best': c['best'], 'days': c['days'], 'lat': clat, 'lng': clng, 'img': cimg, 'places': places})

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({'updated': UPDATED, 'countries': COUNTRIES, 'cities': cities}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
n = sum(len(c['places']) for c in cities)
print(f'Đã tạo {OUT}: {len(cities)} thành phố, {n} địa điểm, thiếu tọa độ {len(miss)}, '
      f'có ảnh {sum(1 for c in cities for p in c["places"] if p["img"])}/{n}')
for m in miss:
    print('  thiếu tọa độ:', m)
