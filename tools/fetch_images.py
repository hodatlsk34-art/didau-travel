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


def article_files(lang, title):
    """Ảnh đại diện + các ảnh JPG khác trong bài viết (tối đa 8)."""
    u = (f'https://{lang}.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages|images'
         f'&piprop=name&imlimit=40&titles=' + urllib.parse.quote(title))
    j = get(u)
    out = []
    for pg in ((j or {}).get('query', {}).get('pages', {}) or {}).values():
        if 'missing' in pg:
            WHY.append('missing ' + title[:30]); return []
        if pg.get('pageimage'):
            out.append(pg['pageimage'])
        for im in pg.get('images', []) or []:
            n = im.get('title', '').split(':', 1)[-1].replace(' ', '_')
            if re.search(r'\.(jpe?g)$', n, re.I) and not BAD_NAME.search(n) and n not in out:
                out.append(n)
    return out[:8]


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


BAD_NAME = re.compile(r'(map|location|locator|logo|seal|flag|emblem|coat[_ ]of|huy[_ ]hi|b%E1%BA%A3n|bản[_ ]đồ|ban[_ ]do|plan|diagram|document|scan|stamp|tem[_ ]|signature|chu[_ ]ky|portrait|chan[_ ]dung|chân[_ ]dung|banknote|icon)', re.I)


def photo_ok(im, name):
    if BAD_NAME.search(name or ''):
        return 'bad-name'
    if im.width / im.height < 0.75:
        return 'portrait'
    hsv = im.convert('HSV').resize((64, 64))
    sat = sum(px[1] for px in hsv.getdata()) / (64 * 64 * 255)
    if sat < 0.16:
        return f'dull {sat:.2f}'
    return None


def save(ii, rel, width, strict=True):
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
    if im.width < 400:
        WHY.append('small'); return None
    if strict:
        bad = photo_ok(im, urllib.parse.unquote(ii.get('descriptionurl') or src))
        if bad:
            WHY.append(bad + ' ' + urllib.parse.unquote(src.split('/')[-1])[:40]); return None
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


def grade_bright(im):
    """Làm ảnh tươi sáng: tăng màu, tương phản, phủ xanh trời vùng trời nhạt."""
    from PIL import ImageEnhance
    im = ImageEnhance.Color(im).enhance(1.35); im = ImageEnhance.Contrast(im).enhance(1.08); im = ImageEnhance.Brightness(im).enhance(1.05)
    w, h = im.size; sky = Image.new('RGB', (w, h), (58, 150, 235)); mask = Image.new('L', (w, h), 0)
    px = mask.load(); hsv = im.convert('HSV').load(); src = im.load(); lim = int(h * .5)
    for y in range(lim):
        a = 1 - y / lim
        for x in range(w):
            r, g, b = src[x, y]; _, sat, v = hsv[x, y]
            if v > 150 and (sat < 90 or (b > r and b > g)):
                px[x, y] = int(150 * a)
    return Image.composite(sky, im, mask)

def hero_candidates(queries):
    """Tải ảnh xem trước (480px) cho các ảnh nền ứng viên để chọn ảnh tươi sáng."""
    outdir = os.path.join(ROOT, 'tools', 'hero_cand'); os.makedirs(outdir, exist_ok=True)
    meta = []; seen = set()
    for q in queries:
        u = ('https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6'
             '&gsrlimit=14&prop=imageinfo&iiprop=url|mime|size|extmetadata&iiurlwidth=500&gsrsearch=' + urllib.parse.quote(q))
        j = get(u)
        for pg in ((j or {}).get('query', {}).get('pages', {}) or {}).values():
            ii = (pg.get('imageinfo') or [None])[0]; t = pg.get('title', '')
            if not ii or t in seen or ii.get('mime') != 'image/jpeg': continue
            if ii.get('width', 0) < 2400 or ii['width'] / max(1, ii.get('height', 1)) < 1.3: continue
            if BAD_NAME.search(t): continue
            data = get(ii.get('thumburl'), binary=True)
            if not data: continue
            seen.add(t); k = len(meta)
            Image.open(io.BytesIO(data)).convert('RGB').save(os.path.join(outdir, f'{k:02d}.jpg'), quality=80)
            md = ii.get('extmetadata') or {}
            meta.append({'k': k, 'title': t, 'w': ii['width'], 'h': ii['height'], 'q': q, 'page': ii.get('descriptionurl'),
                         'credit': ' · '.join(x for x in (strip_html((md.get('Artist') or {}).get('value')), strip_html((md.get('LicenseShortName') or {}).get('value'))) if x)})
            print('CAND', k, t)
    json.dump(meta, open(os.path.join(outdir, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)


def main():
    targets = json.load(open(os.path.join(ROOT, 'tools', 'image_targets.json'), encoding='utf-8'))
    cred = json.load(open(CRED_PATH, encoding='utf-8')) if os.path.exists(CRED_PATH) else {}
    only = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if os.path.exists(os.path.join(ROOT, 'tools', 'only_hero')):
        only = 'hero'
    hq = os.path.join(ROOT, 'tools', 'hero_queries.json')
    if os.path.exists(hq):
        hero_candidates(json.load(open(hq, encoding='utf-8'))); return
    got = miss = 0

    if only in ('all', 'hero'):
        # Ảnh nền lớn cho trang chủ (1920px + bản dọc cho điện thoại)
        HERO = {'halong': 'File:Ha_Long_Bay_in_2019.jpg', 'halong2': 'File:Ha_Long_Bay_on_a_sunny_day.jpg'}
        for name, ft in HERO.items():
            out = os.path.join(PUB, 'images', 'hero', name + '-1920.webp')
            if os.path.exists(out):
                continue
            host = 'commons.wikimedia.org'
            j = get(f'https://{host}/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=1920&titles=' + urllib.parse.quote(ft))
            ii = None
            for pg in ((j or {}).get('query', {}).get('pages', {}) or {}).values():
                ii = (pg.get('imageinfo') or [None])[0]
            data = ii and get(ii.get('thumburl') or ii['url'], binary=True)
            if not data:
                print('HERO MISS', name); continue
            im = Image.open(io.BytesIO(data)).convert('RGB')
            if im.width > 1920:
                im = im.resize((1920, round(im.height * 1920 / im.width)), Image.LANCZOS)
            if name == 'halong2':
                im = grade_bright(im)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            im.save(out, 'WEBP', quality=78, method=6)
            # bản điện thoại: cắt dọc phần giữa, rộng 900
            w, h = im.size; cw = min(w, round(h * 0.72)); x0 = (w - cw) // 2
            m = im.crop((x0, 0, x0 + cw, h)); m = m.resize((900, round(m.height * 900 / m.width)), Image.LANCZOS)
            m.save(os.path.join(PUB, 'images', 'hero', name + '-900.webp'), 'WEBP', quality=76, method=6)
            md = ii.get('extmetadata') or {}
            cred['hero:' + name] = {'f': f'/images/hero/{name}-1920.webp', 'page': ii.get('descriptionurl', 'https://commons.wikimedia.org'),
                                    'credit': ' · '.join(x for x in (strip_html((md.get('Artist') or {}).get('value')), strip_html((md.get('LicenseShortName') or {}).get('value'))) if x)}
            print('HERO OK', name, im.size)

    if only in ('all', 'dest'):
        marks = json.load(open(os.path.join(ROOT, 'tools', 'dest_landmarks.json'), encoding='utf-8'))
        for d in targets['dests']:
            key = d['key']
            if key in cred and cred[key]['f'].startswith('/images/dest2/'):
                continue
            WHY.clear()
            slug = hashlib.md5(key.encode()).hexdigest()[:10]
            rel = f'images/dest2/{slug}.webp'
            res = None
            for spec in marks.get(key, []) + ['en:' + t.replace('_', ' ') for t in d['titles']]:
                lang, title = spec.split(':', 1)
                for f in article_files(lang, title):
                    ii = file_info('File:' + f, 'commons') or file_info('File:' + f, lang)
                    res = save(ii, rel, 960)
                    if res:
                        break
                if res:
                    break
            if not res:
                q = (marks.get(key) or ['x:' + d['name']])[0].split(':', 1)[1]
                for title, ii in commons_search(q):
                    res = save(ii, rel, 960)
                    if res:
                        break
            if res:
                cred[key] = res; got += 1; print('OK  ', key, res['credit'])
            else:
                miss += 1; print('MISS', key, WHY[:5])
            json.dump(cred, open(CRED_PATH, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

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
