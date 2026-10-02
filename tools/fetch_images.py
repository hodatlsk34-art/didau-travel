#!/usr/bin/env python3
"""Tải ảnh miễn phí (Wikipedia / Wikimedia Commons) cho mọi điểm đến và địa điểm,
lưu thẳng vào public/images để web tự phục vụ (nhanh, không phụ thuộc API lúc chạy).

Chạy trên GitHub Actions (xem .github/workflows/images.yml). Kết quả:
  public/images/dest/<slug>.webp, public/images/place/<id>.webp
  public/images/credits.json  -> {key: {"f": đường dẫn, "page": link nguồn, "credit": tác giả · giấy phép}}
Đã có ảnh thì bỏ qua (chạy lại chỉ tải phần còn thiếu). Muốn đổi ảnh: xoá file + mục tương ứng rồi chạy lại.
"""
import hashlib, io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, 'public')
CRED_PATH = os.path.join(PUB, 'images', 'credits.json')
UA = 'DiDauTravelImageBot/1.0 (https://didautravel.id.vn/; static site image prefetch)'
STOPW = set('cho pho quan nha chua den bai bien ho nui ca phe tp thanh khu di tich va cau dong doi'.split())


def norm(s):
    s = unicodedata.normalize('NFD', s.lower()).replace('đ', 'd')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def toks(name):
    n = re.sub(r'\(.*?\)', ' ', norm(name))
    return [w for w in re.split(r'[^a-z0-9]+', n) if len(w) >= 3 and w not in STOPW]


def ok_title(title, name):
    t, nt = toks(name), norm(title)
    if not t:
        return norm(name) in nt
    return sum(1 for w in t if w in nt) >= min(2, len(t))


STATS = {}
WHY = []


def get(url, binary=False, tries=5):
    host = urllib.parse.urlparse(url).hostname
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Api-User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                time.sleep(0.6)
                return data if binary else json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as e:
            STATS[f'{host} {e.code}'] = STATS.get(f'{host} {e.code}', 0) + 1
            if e.code == 404:
                return None
            if e.code in (429, 503, 403):
                wait = int(e.headers.get('Retry-After') or 0) or 10 * (i + 1)
                time.sleep(min(wait, 90))
                continue
            return None
        except Exception as e:
            k = f'{host} {type(e).__name__}: {str(e)[:60]}'
            STATS[k] = STATS.get(k, 0) + 1
            time.sleep(3)
    return None


def strip_html(v):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', str(v or ''))).strip()[:70]


def file_info(file_title, lang='commons'):
    """imageinfo (url thu nhỏ + tác giả + giấy phép) cho 1 file."""
    host = 'commons.wikimedia.org' if lang == 'commons' else f'{lang}.wikipedia.org'
    u = (f'https://{host}/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|mime|extmetadata'
         f'&iiurlwidth=960&titles=' + urllib.parse.quote(file_title))
    j = get(u)
    if not j:
        return None
    for pg in (j.get('query', {}).get('pages', {}) or {}).values():
        ii = (pg.get('imageinfo') or [None])[0]
        if ii:
            return ii
    return None


def summary(lang, title):
    """Trả về {'title','file','lang'} của ảnh đại diện bài viết (pageimages), hoặc None."""
    u = (f'https://{lang}.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages'
         f'&piprop=name&titles=' + urllib.parse.quote(title.replace('_', ' ')))
    j = get(u)
    for pg in ((j or {}).get('query', {}).get('pages', {}) or {}).values():
        if 'missing' in pg:
            return None
        return {'title': pg.get('title', ''), 'file': pg.get('pageimage'), 'lang': lang}
    return None


def from_summary(j):
    if not j:
        WHY.append('no-summary'); return None
    f = j.get('file')
    if not f or f.lower().endswith('.svg'):
        WHY.append('no-pageimage'); return None
    ii = file_info('File:' + f, 'commons') or file_info('File:' + f, j['lang'])
    if not ii:
        WHY.append('no-imageinfo ' + f[:40])
    return ii


def commons_search(q):
    u = ('https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6'
         '&gsrlimit=8&prop=imageinfo&iiprop=url|mime|extmetadata&iiurlwidth=960&gsrsearch='
         + urllib.parse.quote(q + ' filetype:bitmap'))
    j = get(u)
    pages = sorted(((j or {}).get('query', {}).get('pages', {}) or {}).values(), key=lambda p: p.get('index', 0))
    return [(p.get('title', ''), (p.get('imageinfo') or [None])[0]) for p in pages]


def save(ii, rel, width):
    if not ii:
        WHY.append('no-imageinfo'); return None
    if not re.match(r'image/(jpeg|png|webp)', ii.get('mime', '')):
        WHY.append('mime=' + str(ii.get('mime'))); return None
    src = ii.get('thumburl') or ii.get('url')
    if not src or not re.match(r'https://(upload|thumb)\.wikimedia\.org/', src):
        WHY.append('src=' + str(src)[:60]); return None
    data = get(src, binary=True)
    if not data:
        WHY.append('download-fail ' + src[-50:]); return None
    try:
        im = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception as e:
        WHY.append('pil ' + type(e).__name__ + ' ' + str(len(data))); return None
    if im.width < 300:
        WHY.append('small'); return None
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    path = os.path.join(PUB, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, 'WEBP', quality=72, method=6)
    md = ii.get('extmetadata') or {}
    au = strip_html((md.get('Artist') or {}).get('value'))
    lic = strip_html((md.get('LicenseShortName') or {}).get('value'))
    page = ii.get('descriptionurl') or 'https://commons.wikimedia.org'
    if not re.match(r'https://[a-z.]*(wikipedia|wikimedia)\.org/', page):
        page = 'https://commons.wikimedia.org'
    return {'f': '/' + rel.replace(os.sep, '/'), 'page': page, 'credit': ' · '.join(x for x in (au, lic or 'Wikimedia') if x)}


def main():
    targets = json.load(open(os.path.join(ROOT, 'tools', 'image_targets.json'), encoding='utf-8'))
    cred = json.load(open(CRED_PATH, encoding='utf-8')) if os.path.exists(CRED_PATH) else {}
    only = sys.argv[1] if len(sys.argv) > 1 else 'all'
    got = miss = 0

    if only in ('all', 'dest'):
        for d in targets['dests']:
            key = d['key']
            if key in cred:
                continue
            WHY.clear()
            slug = hashlib.md5(key.encode()).hexdigest()[:10]
            res = None
            nm = re.sub(r'^TP ', '', d['name'])
            segs = [x.strip() for x in nm.split(' – ')] if ' – ' in nm else []
            cands = [('en', t) for t in d['titles']] + [('vi', nm)] + [(l, x) for x in segs for l in ('vi', 'en')]
            for lang, t in cands:
                res = save(from_summary(summary(lang, t)), f'images/dest/{slug}.webp', 960)
                time.sleep(0.4)
                if res:
                    break
            if not res:
                for title, ii in commons_search(d['name'] + ' ' + d['prov']):
                    if ok_title(title, d['name']):
                        res = save(ii, f'images/dest/{slug}.webp', 960)
                        if res:
                            break
            if res:
                cred[key] = res; got += 1; print('OK  ', key, res['credit'])
            else:
                miss += 1; print('MISS', key, WHY[:4])

    if only in ('all', 'place'):
        for p in targets['places']:
            key = 'p:' + str(p['id'])
            if key in cred:
                continue
            WHY.clear()
            name = re.split(r'\s[–&-]\s', re.sub(r'\s*\(.*?\)\s*', ' ', p['name']))[0].strip()
            res = None
            if p['cat'] != 'food':
                j = summary('vi', name)
                if j and ok_title(j.get('title', ''), name):
                    res = save(from_summary(j), f'images/place/{p["id"]}.webp', 640)
                time.sleep(0.3)
            if not res:
                where = p['prov'] if p['area'] == 'Nội thành' else p['area'].split(' – ')[0]
                for title, ii in commons_search(name + ' ' + where):
                    if ok_title(title, name):
                        res = save(ii, f'images/place/{p["id"]}.webp', 640)
                        if res:
                            break
                time.sleep(0.3)
            if res:
                cred[key] = res; got += 1; print('OK  ', key, name)
            else:
                miss += 1; print('MISS', key, name, WHY[:3])
            if got and got % 25 == 0:
                json.dump(cred, open(CRED_PATH, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    json.dump(cred, open(CRED_PATH, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'\nTải mới: {got} · Không tìm được: {miss} · Tổng đã có: {len(cred)}')
    print('Lỗi mạng:', STATS)


if __name__ == '__main__':
    main()
