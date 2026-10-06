#!/usr/bin/env python3
"""Ghép tools/intl_src.py + public/images/intl/geo.json -> public/data/intl.json (app đọc khi mở mục Quốc tế).
Chạy: python3 tools/build_intl.py
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intl_src import COUNTRIES, CITIES, UPDATED  # noqa: E402
from intl_plan import CITY as PLAN_CITY, LOCAL  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, 'public', 'images', 'intl', 'geo.json')
OUT = os.path.join(ROOT, 'public', 'data', 'intl.json')
CAT = {'f': 'food', 'c': 'check', 's': 'sight'}

geo = json.load(open(GEO, encoding='utf-8')) if os.path.exists(GEO) else {}


TAG = {'h': 'history', 'n': 'nature', 'b': 'beach', 'p': 'photo', 's': 'street', 'c': 'cafe', 'r': 'relax', 'k': 'classic', 'm': 'cool'}
MEAL = {'th': 150, 'cn': 150, 'kr': 250, 'jp': 300, 'sg': 200, 'my': 120, 'tw': 150, 'id': 150}
IO = {'i': 'in', 'o': 'out', 'm': 'mixed'}


def plan_fields(cat, extra, country, multi):
    """Thông tin cho bộ máy lập lịch trình (giống dữ liệu trong nước)."""
    k = [x for x in (extra.get('k') or '').split(',') if x]
    if cat == 'food':
        kinds = k or ['trua', 'toi']
    else:
        kinds = ([cat] if cat not in k else []) + k
    if extra.get('ev') and 'evening' not in kinds:
        kinds.append('evening')
    if extra.get('trip'):
        kinds = ['trip']
    tags = [TAG[x] for x in extra.get('t', '') if x in TAG]
    if cat == 'food' and 'street' not in tags:
        tags.append('street')
    if 'cafe' in kinds and 'cafe' not in tags:
        tags.append('cafe')
    if 'v' in extra:
        cost = int(extra['v']) * 1000
    else:
        cost = (MEAL.get(country) or (LOCAL.get(country) or {}).get('meal', 400)) * 1000 if cat == 'food' else 0
    if 'd' in extra:
        dur = int(extra['d'])
    elif extra.get('trip'):
        dur = 360
    elif cat == 'food':
        dur = 60 if 'cafe' in kinds else 75 if 'toi' in kinds else 60 if 'trua' in kinds else 45
    else:
        dur = 60 if cat == 'check' else 120
    io = IO.get(extra.get('io')) or ('in' if cat == 'food' else 'out' if cat == 'check' else 'mixed')
    f = extra.get('f')
    out = {'kinds': kinds, 'tags': tags, 'cost': cost, 'dur': dur, 'io': io, 'fit': {'kid': f != 'x', 'old': f not in ('x', 'o')}}
    if extra.get('h'): out['hours'] = extra['h']
    if extra.get('ss'): out['sunset'] = True
    if extra.get('ev'): out['evening'] = extra['ev']
    if extra.get('eo'): out['eveningOnly'] = True
    if extra.get('mo'): out['morningOnly'] = True
    if extra.get('cl'): out['closed'] = extra['cl']
    if extra.get('trip'): out['trip'] = True
    if multi: out['area'] = extra.get('a') or multi[0]
    return out


def img(g):
    return {'f': g['f'], 'page': g.get('page'), 'credit': g.get('credit')} if g and g.get('f') else None


cities, miss = [], []
for c in CITIES:
    g = geo.get('c-' + c['id'], {})
    places = []
    pc = PLAN_CITY.get(c['id'], {})
    for i, p in enumerate(c['places']):
        pid = f"{c['id']}-{i + 1}"
        pg = geo.get(pid, {})
        extra = p[4] if len(p) > 4 else {}
        if extra.get('hide'):                  # chưa có tọa độ tin cậy: tạm ẩn
            continue
        lat, lng = pg.get('lat'), pg.get('lng')
        if 'll' in extra:                      # tọa độ ghi tay (khi Wikipedia không có)
            lat, lng = extra['ll']
        if lat is None:
            miss.append(f'{pid} {p[1]}')
        rec = {'id': pid, 'cat': CAT[p[0]], 'name': p[1], 'why': p[3], 'price': extra.get('price', ''), 'tip': extra.get('tip', ''),
               'lat': lat, 'lng': lng, 'wp': pg.get('wp'), 'img': img(pg)}
        rec.update(plan_fields(CAT[p[0]], extra, c['country'], PLAN_CITY.get(c['id'], {}).get('areas')))
        places.append(rec)
    pts = [p for p in places if p['lat'] is not None]
    clat = g.get('lat') if g.get('lat') is not None else (sum(p['lat'] for p in pts) / len(pts) if pts else None)
    clng = g.get('lng') if g.get('lng') is not None else (sum(p['lng'] for p in pts) / len(pts) if pts else None)
    bad = lambda x: not x or re.search(r'Flag_of|_map|marker|Locator|\.svg', x.get('page') or '', re.I)   # cờ, bản đồ: không dùng làm ảnh bìa
    cover = {'singapore': 'singapore-2', 'bali': 'bali-1', 'penang': 'penang-1', 'swiss': 'swiss-9', 'vienna': 'vienna-1'}.get(c['id'])
    cimg = img(g) if not bad(img(g)) and c['id'] not in ('swiss', 'vienna') else None
    cimg = cimg or next((p['img'] for p in places if p['id'] == cover and p['img']), None) or next((p['img'] for p in places if p['img'] and not bad(p['img'])), None)
    cities.append({'id': c['id'], 'country': c['country'], 'name': c['name'], 'local': c.get('local', ''), 'intro': c['intro'],
                   'best': c['best'], 'days': c['days'], 'lat': clat, 'lng': clng, 'img': cimg, 'places': places,
                   'plan': dict(pc, en=c['wiki'].replace(' province', '').replace(' Island', ''))})

os.makedirs(os.path.dirname(OUT), exist_ok=True)
countries = [dict(k, local=LOCAL.get(k['id'])) for k in COUNTRIES]
json.dump({'updated': UPDATED, 'countries': countries, 'cities': cities}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
n = sum(len(c['places']) for c in cities)
print(f'Đã tạo {OUT}: {len(cities)} thành phố, {n} địa điểm, thiếu tọa độ {len(miss)}, '
      f'có ảnh {sum(1 for c in cities for p in c["places"] if p["img"])}/{n}')
for m in miss:
    print('  thiếu tọa độ:', m)
