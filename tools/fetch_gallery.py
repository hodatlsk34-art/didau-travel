#!/usr/bin/env python3
"""Thêm 3 ảnh mới (ưu tiên ảnh chụp gần đây) cho mỗi địa điểm, lấy từ Wikimedia Commons (giấy phép tự do).

Đầu vào : tools/gallery_targets.json  [{id, name, cat, lat, lng, wiki?, main?}]
Đầu ra  : public/images/gallery/<id>-<n>.webp, public/images/gallery/gallery.json
          {id: [{f, page, credit, date}]}  ·  tools/gallery_last.log
Chạy trên GitHub Actions (.github/workflows/gallery.yml). Mục đã có thì bỏ qua (xóa khỏi gallery.json để lấy lại).

Cách chọn ảnh để tránh ảnh sai chỗ:
  1. Ảnh trong thư mục Commons của bài Wikipedia (nếu có) – chắc chắn đúng địa danh.
  2. Ảnh chụp trong bán kính nhỏ quanh tọa độ VÀ tên file có chứa tên địa điểm.
  Lọc: ảnh ngang, đủ lớn, không phải bản đồ/logo/sơ đồ; sắp theo ngày chụp mới nhất.
"""
import io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'public', 'images', 'gallery')
GJ = os.path.join(OUT, 'gallery.json')
UA = 'DiDauTravelGalleryBot/1.0 (https://didautravel.id.vn/; free-licensed travel photos)'
PER = 3
BAD = re.compile(r'map|bản đồ|ban do|logo|plan|diagram|sơ đồ|so do|flag|coat of arms|seal|emblem|ticket|menu|document|scan|stamp|banknote|poster|sign\b|\.svg|\.gif|\.tif', re.I)
STOP = set('cho pho quan nha chua den bai bien ho nui ca phe tp thanh khu di tich va cau dong doi the of and temple park street market beach road'.split())
LOG, STATS = [], {'ok': 0, 'none': 0}


def get(url, binary=False, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Api-User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
            time.sleep(0.35)
            return data if binary else json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(min(int(e.headers.get('Retry-After') or 0) or 8 * (i + 1), 90))
        except Exception:
            time.sleep(4)
    return None


def norm(s):
    s = unicodedata.normalize('NFD', str(s).lower()).replace('đ', 'd')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def toks(*names):
    out = set()
    for n in names:
        if not n:
            continue
        n = re.sub(r'\(.*?\)', ' ', norm(n))
        out |= {w for w in re.split(r'[^a-z0-9]+', n) if len(w) >= 3 and w not in STOP}
    return out


def strip(v, n=60):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', str(v or ''))).strip()[:n]


def vi_article(name):
    """Tìm bài Wikipedia tiếng Việt khớp tên địa điểm (dùng cho điểm trong nước chưa có tên bài)."""
    q = re.sub(r'\(.*?\)', ' ', name).strip()
    j = get('https://vi.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&list=search&srlimit=3&srnamespace=0&srsearch='
            + urllib.parse.quote(q)) or {}
    tk = toks(name)
    for r in j.get('query', {}).get('search', []):
        tt = toks(r['title'])
        if tk and len(tk & tt) >= min(2, len(tk)):
            return r['title']
    return None


def commons_category(wiki, lang='en'):
    if not wiki:
        return None
    j = get(f'https://{lang}.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1&prop=pageprops&ppprop=wikibase_item&titles='
            + urllib.parse.quote(wiki)) or {}
    pg = (j.get('query', {}).get('pages') or [{}])[0]
    q = (pg.get('pageprops') or {}).get('wikibase_item')
    if not q:
        return None
    j = get(f'https://www.wikidata.org/w/api.php?action=wbgetclaims&format=json&property=P373&entity={q}') or {}
    cl = j.get('claims', {}).get('P373') or []
    try:
        return cl[0]['mainsnak']['datavalue']['value']
    except Exception:
        return None


def files_in_category(cat):
    j = get('https://commons.wikimedia.org/w/api.php?action=query&format=json&formatversion=2&list=categorymembers&cmtype=file&cmlimit=200&cmsort=timestamp&cmdir=desc&cmtitle='
            + urllib.parse.quote('Category:' + cat)) or {}
    return [m['title'] for m in j.get('query', {}).get('categorymembers', [])]


def files_near(lat, lng, radius):
    j = get(f'https://commons.wikimedia.org/w/api.php?action=query&format=json&formatversion=2&list=geosearch&gsnamespace=6&gslimit=100&gsradius={radius}&gscoord={lat}|{lng}') or {}
    return [g['title'] for g in j.get('query', {}).get('geosearch', [])]


def infos(titles):
    out = {}
    for k in range(0, len(titles), 40):
        ch = titles[k:k + 40]
        j = get('https://commons.wikimedia.org/w/api.php?action=query&format=json&formatversion=2&prop=imageinfo&iiprop=url|size|mime|extmetadata|timestamp&iiurlwidth=720&titles='
                + urllib.parse.quote('|'.join(ch))) or {}
        for pg in j.get('query', {}).get('pages', []):
            ii = (pg.get('imageinfo') or [None])[0]
            if ii:
                out[pg['title']] = ii
    return out


def date_of(ii):
    md = ii.get('extmetadata', {})
    raw = strip(md.get('DateTimeOriginal', {}).get('value'), 40)
    m = re.search(r'(19|20)\d{2}(-\d{2})?(-\d{2})?', raw) or re.search(r'(19|20)\d{2}-\d{2}-\d{2}', ii.get('timestamp', ''))
    return m.group(0) if m else (ii.get('timestamp', '')[:10])


def good(title, ii):
    if BAD.search(title) or ii.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
        return False
    w, h = ii.get('width', 0), ii.get('height', 0)
    if w < 1000 or h < 560 or not (1.15 <= w / max(h, 1) <= 2.2):
        return False
    lic = strip(ii.get('extmetadata', {}).get('LicenseShortName', {}).get('value'), 40)
    return bool(lic) and not re.search(r'non-free|fair use', lic, re.I)


def pick(t):
    tk = toks(t['name'], t.get('wiki'))
    cands = {}
    cat = commons_category(t.get('wiki'))
    if not cat and not t.get('wiki') and t['cat'] != 'food':
        vt = vi_article(t['name'])
        if vt:
            cat = commons_category(vt, 'vi')
    if cat:
        for f in files_in_category(cat):
            cands[f] = 'cat'
    if t.get('lat') is not None:
        radius = {'food': 120, 'check': 400, 'sight': 400}[t['cat']]
        for f in files_near(t['lat'], t['lng'], radius):
            if f not in cands and len(tk & toks(f[5:])) >= min(2, len(tk) or 1):
                cands[f] = 'near'
    if not cands:
        return []
    inf = infos(list(cands)[:160])
    rows = []
    for f, src in cands.items():
        ii = inf.get(f)
        if not ii or not good(f, ii) or ii.get('descriptionurl') == t.get('main'):
            continue
        rows.append((date_of(ii), src, f, ii))
    rows.sort(key=lambda r: r[0], reverse=True)          # ảnh chụp mới nhất trước
    return rows[:PER]


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = json.load(open(os.path.join(ROOT, 'tools', 'gallery_targets.json'), encoding='utf-8'))
    gal = json.load(open(GJ, encoding='utf-8')) if os.path.exists(GJ) else {}
    # chưa làm, hoặc lần trước chưa tìm được ảnh (thử lại – có thể đã có ảnh mới trên Commons)
    todo = [t for t in targets if t['id'] not in gal] + [t for t in targets if gal.get(t['id']) == [] and t['cat'] != 'food']
    print(f'{len(targets)} điểm, cần lấy {len(todo)}')
    t0 = time.time()
    for n, t in enumerate(todo):
        if time.time() - t0 > 50 * 60:          # giới hạn thời gian; lần chạy sau làm tiếp
            LOG.append('Dừng vì hết thời gian, chạy lại để làm tiếp'); break
        rows, items = pick(t), []
        safe = re.sub(r'[^a-z0-9-]', '-', t['id'].replace('i:', 'i-').lower())
        for k, (d, src, f, ii) in enumerate(rows):
            data = get(ii.get('thumburl') or ii['url'], binary=True)
            if not data:
                continue
            try:
                im = Image.open(io.BytesIO(data)).convert('RGB'); im.thumbnail((720, 720))
                fn = f'{safe}-{k + 1}.webp'; im.save(os.path.join(OUT, fn), 'WEBP', quality=72, method=6)
            except Exception as e:
                LOG.append(f'Lỗi ảnh {t["id"]}: {e}'); continue
            artist = strip(ii.get('extmetadata', {}).get('Artist', {}).get('value'), 50) or 'Wikimedia Commons'
            lic = strip(ii.get('extmetadata', {}).get('LicenseShortName', {}).get('value'), 30)
            items.append({'f': f'/images/gallery/{fn}', 'page': ii.get('descriptionurl'), 'credit': f'{artist} · {lic}', 'date': d[:10]})
        gal[t['id']] = items
        STATS['ok' if items else 'none'] += 1
        if not items:
            LOG.append(f'Không có ảnh phù hợp: {t["id"]} {t["name"]}')
        if n % 25 == 0:
            print(n, t['id'], len(items)); json.dump(gal, open(GJ, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump(gal, open(GJ, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    have = sum(1 for v in gal.values() if v)
    summary = f'Có ảnh thêm: {have}/{len(targets)} điểm · tổng {sum(len(v) for v in gal.values())} ảnh'
    print(summary)
    open(os.path.join(ROOT, 'tools', 'gallery_last.log'), 'w', encoding='utf-8').write(summary + '\n' + '\n'.join(LOG) + '\n')


if __name__ == '__main__':
    main()
