#!/usr/bin/env python3
"""Lấy TỌA ĐỘ + ẢNH (giấy phép tự do) từ Wikipedia/Wikimedia Commons cho các điểm quốc tế trong tools/intl_src.py.

Chạy trên GitHub Actions (.github/workflows/intl.yml). Kết quả:
  public/images/intl/<id>.webp        ảnh tự lưu trữ
  public/images/intl/geo.json         {id: {lat, lng, wp, f, page, credit}}
  tools/intl_last.log                 báo cáo mục thiếu tọa độ/ảnh để sửa tên bài Wikipedia
Đã có thì bỏ qua; muốn lấy lại một mục: xóa mục đó trong geo.json (và file ảnh) rồi chạy lại.
"""
import io, json, os, re, sys, time, urllib.parse, urllib.request
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intl_src import CITIES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'public', 'images', 'intl')
GEO = os.path.join(OUT, 'geo.json')
UA = 'DiDauTravelIntlBot/1.0 (https://didautravel.id.vn/; coordinates and free images for travel guide)'
LOG = []


def get(url, binary=False, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Api-User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
            time.sleep(0.5)
            return data if binary else json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(min(int(e.headers.get('Retry-After') or 0) or 8 * (i + 1), 90))
        except Exception:
            time.sleep(4)
    return None


def strip(v, n=80):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', str(v or ''))).strip()[:n]


def items():
    for c in CITIES:
        yield 'c-' + c['id'], c['wiki'], 1280
        for i, p in enumerate(c['places']):
            yield f"{c['id']}-{i + 1}", p[2], 800


def wiki_batch(titles):
    """titles -> {title_gốc: {lat,lng,wp,img}}"""
    out = {}
    for k in range(0, len(titles), 40):
        chunk = titles[k:k + 40]
        u = ('https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1'
             '&prop=coordinates|pageimages|info&inprop=url&piprop=name&pilicense=free&colimit=max&titles='
             + urllib.parse.quote('|'.join(chunk)))
        j = get(u) or {}
        q = j.get('query', {})
        back = {}
        for n in q.get('normalized', []):
            back[n['to']] = back.get(n['from'], n['from'])
        for r in q.get('redirects', []):
            back[r['to']] = back.get(r['from'], r['from'])
        for pg in q.get('pages', []):
            orig = back.get(pg.get('title'), pg.get('title'))
            if pg.get('missing'):
                out[orig] = None; continue
            co = (pg.get('coordinates') or [None])[0]
            out[orig] = {'lat': round(co['lat'], 5) if co else None, 'lng': round(co['lon'], 5) if co else None,
                         'wp': pg.get('fullurl'), 'img': pg.get('pageimage')}
    return out


def image_info(fname, width):
    for host in ('commons.wikimedia.org', 'en.wikipedia.org'):
        u = (f'https://{host}/w/api.php?action=query&format=json&formatversion=2&prop=imageinfo'
             f'&iiprop=url|extmetadata|mime&iiurlwidth={width}&titles=' + urllib.parse.quote('File:' + fname))
        j = get(u) or {}
        for pg in j.get('query', {}).get('pages', []):
            ii = (pg.get('imageinfo') or [None])[0]
            if not ii:
                continue
            md = ii.get('extmetadata', {})
            lic = strip(md.get('LicenseShortName', {}).get('value'), 40)
            if not lic or re.search(r'non-free|fair use', lic, re.I):
                return None
            artist = strip(md.get('Artist', {}).get('value'), 50) or 'Wikimedia Commons'
            return {'thumb': ii.get('thumburl') or ii.get('url'), 'page': ii.get('descriptionurl'), 'credit': f'{artist} · {lic}'}
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    geo = json.load(open(GEO, encoding='utf-8')) if os.path.exists(GEO) else {}
    all_items = list(items())
    need = [(i, t, w) for i, t, w in all_items if i not in geo or geo[i].get('wiki') != t]
    print(f'Tổng {len(all_items)} mục, cần lấy {len(need)}')
    info = wiki_batch(sorted({t for _, t, _ in need}))
    for iid, title, width in need:
        w = info.get(title)
        if not w:
            LOG.append(f'KHÔNG CÓ BÀI: {iid} "{title}"'); continue
        rec = {'wiki': title, 'lat': w['lat'], 'lng': w['lng'], 'wp': w['wp']}
        if w['lat'] is None:
            LOG.append(f'THIẾU TỌA ĐỘ: {iid} "{title}"')
        if w['img']:
            im = image_info(w['img'], width)
            if im and im['thumb']:
                data = get(im['thumb'], binary=True)
                if data:
                    try:
                        pic = Image.open(io.BytesIO(data)).convert('RGB')
                        pic.thumbnail((width, width))
                        fn = f'{iid}.webp'
                        pic.save(os.path.join(OUT, fn), 'WEBP', quality=80, method=6)
                        rec.update({'f': f'/images/intl/{fn}', 'page': im['page'], 'credit': im['credit']})
                    except Exception as e:
                        LOG.append(f'LỖI ẢNH: {iid} {e}')
        if 'f' not in rec:
            LOG.append(f'THIẾU ẢNH: {iid} "{title}"')
        geo[iid] = rec
    keep = {i for i, _, _ in all_items}
    geo = {k: v for k, v in geo.items() if k in keep}
    json.dump(geo, open(GEO, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)
    ok_ll = sum(1 for v in geo.values() if v.get('lat') is not None)
    ok_im = sum(1 for v in geo.values() if v.get('f'))
    summary = f'Có tọa độ: {ok_ll}/{len(all_items)} · Có ảnh: {ok_im}/{len(all_items)}'
    print(summary); print('\n'.join(LOG))
    open(os.path.join(ROOT, 'tools', 'intl_last.log'), 'w', encoding='utf-8').write(summary + '\n' + '\n'.join(LOG) + '\n')


if __name__ == '__main__':
    main()
