#!/usr/bin/env python3
"""Tạo trang tĩnh cho từng ĐIỂM ĐẾN để Google đọc được (SEO).

  /diem-den/<slug>/   77 điểm đến trong nước   (dữ liệu: tools/vn_dest.json – xuất từ app)
  /quoc-te/<id>/      21 thành phố quốc tế      (dữ liệu: public/data/intl.json)
  /diem-den/, /quoc-te/  trang tổng hợp
Ghi danh sách URL vào tools/page_urls.json để build_blog.py đưa vào sitemap.xml.

Chạy:  python3 tools/build_pages.py && python3 tools/build_blog.py
"""
import json, math, re, unicodedata, urllib.parse
from pathlib import Path
import build_blog as B  # dùng chung giao diện (head, thanh menu, chân trang, CSS)

ROOT, PUB, SITE, esc = B.ROOT, B.PUB, B.SITE, B.esc
VN = json.loads((ROOT / 'tools/vn_dest.json').read_text(encoding='utf-8'))
INTL = json.loads((PUB / 'data/intl.json').read_text(encoding='utf-8'))
CRED = json.loads((PUB / 'images/credits.json').read_text(encoding='utf-8'))
GJ = PUB / 'images/gallery/gallery.json'
GAL = json.loads(GJ.read_text(encoding='utf-8')) if GJ.exists() else {}
UPDATED = INTL.get('updated', '')
AFF = 'https://goeco.mobi/?token=jAAsklqtdBozRAjUNkPga&url={url}&sub1=didau-app&sub2=seo&sub3={sub3}&advertiser_id=traveloka.com.vn&global_domain=traveloka.com'
REGION = {'bac': 'Miền Bắc', 'btb': 'Bắc Trung Bộ', 'trung': 'Miền Trung', 'tn': 'Tây Nguyên', 'nam': 'Miền Nam', 'mekong': 'Miền Tây (ĐBSCL)'}
THEME = {'a': 'Ẩm thực', 'b': 'Biển', 'd': 'Đảo', 'n': 'Núi – thiên nhiên', 'v': 'Lịch sử – văn hóa', 'r': 'Nghỉ dưỡng', 'm': 'Khí hậu mát', 's': 'Sông nước'}
CATS = [('sight', 'Điểm tham quan nổi bật'), ('check', 'Điểm check-in đẹp'), ('food', 'Ăn gì ở {n}')]

EXTRA_CSS = """
.facts2{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 18px}
.facts2 div{background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.facts2 b{display:block;font:700 15px/1.3 Lexend,sans-serif}
.facts2 span{font-size:13px;color:var(--mut)}
.ctas{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 26px}
.plist3{display:grid;gap:12px;margin:0 0 10px}
.pc{display:grid;grid-template-columns:120px 1fr;gap:14px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px}
.pc.noimg{grid-template-columns:1fr}
.pc .pi{width:120px;height:120px;border-radius:12px;overflow:hidden;background:#e6eef5}
.pc .pi img{width:100%;height:100%;object-fit:cover;display:block}
.pc h3{font:700 17px/1.3 Lexend,sans-serif;margin:0 0 4px}
.pc p{margin:0 0 6px;font-size:15px}
.pc ul{list-style:none;padding:0;margin:0;font-size:14px;color:var(--mut)}
.pc li{margin:2px 0}
.pc a{font-size:14px;font-weight:600;text-decoration:none}
.faq h3{font:700 17px/1.35 Lexend,sans-serif;margin:16px 0 4px;color:var(--ink)}
.faq p{margin:0 0 8px}
.near{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.near a{background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 13px;text-decoration:none;font-weight:600;font-size:14px}
.hub h2{font:700 21px/1.3 Lexend,sans-serif;margin:26px 0 12px}
@media (max-width:560px){ .pc{grid-template-columns:88px 1fr} .pc .pi{width:88px;height:88px} }
"""


def slugify(s):
    s = unicodedata.normalize('NFD', s).replace('đ', 'd').replace('Đ', 'D')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def clean_name(n):
    n = re.sub(r'^(Trung tâm|Nội thành|TP) ', '', n)
    return {'Cố đô Huế': 'Huế'}.get(n, n)


def months_txt(ms):
    if not ms:
        return 'quanh năm'
    return 'tháng ' + ', '.join(str(m) for m in ms)


def km(a, b):
    R, p = 6371, math.radians
    dlat, dlng = p(b[0] - a[0]), p(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(p(a[0])) * math.cos(p(b[0])) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def aff(path, tag):
    return AFF.replace('{url}', urllib.parse.quote('https://www.traveloka.com/vi-vn/' + path, safe='')).replace('{sub3}', urllib.parse.quote(tag))


def img_tag(src, alt='', w=480, h=320):
    return f'<img src="{esc(src)}" alt="{esc(alt)}" loading="lazy" width="{w}" height="{h}">' if src else ''


def place_card(p, img=None, extra=None):
    det = []
    for icon, key in (('📍', 'addr'), ('🕘', 'hours'), ('🎟', 'price'), ('⭐', 'must'), ('💡', 'tip')):
        if p.get(key):
            det.append(f'<li>{icon} {esc(p[key])}</li>')
    links = []
    if p.get('lat') is not None:
        links.append(f'<a href="https://www.google.com/maps/search/?api=1&amp;query={p["lat"]},{p["lng"]}" target="_blank" rel="noopener">Chỉ đường Google Maps →</a>')
    if extra:
        links.append(extra)
    pi = f'<div class="pi">{img_tag(img, p["name"], 240, 240)}</div>' if img else ''
    return (f'<div class="pc{"" if img else " noimg"}">{pi}<div><h3>{esc(p["name"])}</h3>'
            f'<p>{esc(p.get("why", ""))}</p><ul>{"".join(det)}</ul>{" · ".join(links)}</div></div>')


def page(title, desc, url, image, body, ld, active):
    ldj = json.dumps(ld, ensure_ascii=False).replace('</', '<\\/')
    return (B.head(title, desc, url, image, f'<script type="application/ld+json">{ldj}</script>\n<style>{EXTRA_CSS}</style>\n')
            + B.topbar(active) + f'<main>{body}</main>' + B.FOOT)


def crumbs(items):
    html = ' › '.join(f'<a href="{u}">{esc(n)}</a>' if u else esc(n) for n, u in items)
    ld = {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, **({'item': SITE + u} if u else {})} for i, (n, u) in enumerate(items)]}
    return f'<nav class="crumb">{html}</nav>', ld


# ------------------------------------------------------------------ TRONG NƯỚC
def build_vn():
    dests = VN['dests']
    by_key = {}
    for d in dests:
        d['slug'] = slugify(clean_name(d['name']))
        d['title'] = clean_name(d['name'])
        d['img'] = (CRED.get(d['key']) or {})
        by_key[d['key']] = d
    places = {}
    for p in VN['places']:
        places.setdefault(p['prov'] + '|' + p['area'], []).append(p)
    blog = json.loads((PUB / 'blog/posts.json').read_text(encoding='utf-8'))
    urls = []
    for d in dests:
        ps = places.get(d['key'], [])
        name, prov = d['title'], d['prov']
        url = f'/diem-den/{d["slug"]}/'
        full = SITE + url
        cover = d['img'].get('f') or next(((CRED.get('p:' + p['id']) or {}).get('f') for p in ps if CRED.get('p:' + p['id'])), None)
        themes = [THEME[c] for c in d['v'] if c in THEME]
        days = '1–2 ngày' if len(ps) <= 8 else ('2–3 ngày' if len(ps) <= 14 else '3–4 ngày')
        prov_txt = '' if prov in name else f' ({prov})'
        title = f'Du lịch {name}{prov_txt}: ăn gì, chơi gì, mùa nào đẹp | Đi Đâu?'
        foods = [p['name'] for p in ps if p['cat'] == 'food']
        desc = (f'Cẩm nang du lịch {name}{prov_txt}: {d["intro"].rstrip(".")}. Mùa đẹp {months_txt(d["months"])}, '
                f'{len(ps)} địa điểm ăn uống, check-in, tham quan và lịch trình gợi ý miễn phí.')[:300]
        cr, crld = crumbs([('Trang chủ', '/'), ('Điểm đến trong nước', '/diem-den/'), (REGION.get(d['r'], ''), f'/diem-den/#{d["r"]}'), (name, None)])
        sections = []
        for cat, label in CATS:
            items = [p for p in ps if p['cat'] == cat]
            if not items:
                continue
            cards = []
            for p in items:
                im = (CRED.get('p:' + p['id']) or {}).get('f') or ((GAL.get(p['id']) or [{}])[0].get('f'))
                cards.append(place_card(p, im))
            sections.append(f'<h2>{esc(label.format(n=name))}</h2><div class="plist3">{"".join(cards)}</div>')
        near = sorted((x for x in dests if x['key'] != d['key']), key=lambda x: km((d['lat'], d['lng']), (x['lat'], x['lng'])))[:6]
        posts = [b for b in blog if b.get('cover') == d['key']]
        k = urllib.parse.quote(d['key'], safe='')
        fig = ''
        if cover:
            fig = f'<figure class="cover">{img_tag(cover, "Du lịch " + name, 960, 540)}</figure>'
            if d['img'].get('page'):
                fig += f'<p class="credit">Ảnh: <a href="{esc(d["img"]["page"])}" target="_blank" rel="noopener">{esc(d["img"].get("credit"))}</a> qua Wikimedia Commons</p>'
        suit = []
        if d.get('kid') == 2:
            suit.append('gia đình có trẻ nhỏ')
        if d.get('old') == 2:
            suit.append('người lớn tuổi')
        faq = [
            (f'Đi {name} mùa nào đẹp nhất?', f'Thời điểm đẹp để đi {name} là {months_txt(d["months"])}. {VN["season"].get(d["r"], "") if VN.get("season") else ""}'.strip()),
            (f'Đi {name} mấy ngày là đủ?', f'Với {len(ps)} địa điểm nổi bật, bạn nên dành khoảng {days}. Đi Đâu? có thể lập lịch trình theo giờ cho đúng số ngày bạn có.'),
        ]
        if foods:
            faq.append((f'Ăn gì ở {name}?', 'Gợi ý: ' + ', '.join(foods[:8]) + '.'))
        if suit:
            faq.append((f'{name} có hợp đi cùng ai?', f'{name} khá phù hợp cho {" và ".join(suit)}.'))
        body = (cr + fig + ''.join(f'<span class="tag">{esc(t)}</span> ' for t in themes)
                + f'<h1>Du lịch {esc(name)}: ăn gì, chơi gì, mùa nào đẹp?</h1>'
                + f'<p class="meta">{esc(prov)} · {esc(REGION.get(d["r"], ""))} · {len(ps)} địa điểm · cập nhật {esc(UPDATED)}</p>'
                + f'<p>{esc(name)}{esc(prov_txt)} – {esc(d["intro"])}. Dưới đây là những điểm tham quan, check-in và món ngon nên thử, kèm địa chỉ, giờ mở cửa, giá tham khảo và mẹo đi.</p>'
                + f'<div class="facts2"><div><b>{esc(months_txt(d["months"]).capitalize())}</b><span>Mùa đẹp</span></div><div><b>{days}</b><span>Thời gian gợi ý</span></div>'
                + f'<div><b>{len(ps)} địa điểm</b><span>Ăn uống · check-in · tham quan</span></div></div>'
                + f'<div class="ctas"><a class="btn" href="/#go=plan:{k}" data-ev="plan">✨ Lập lịch trình {esc(name)} miễn phí</a><a class="btn ghost" href="/#go=dest:{k}" data-ev="dest">🗺 Xem bản đồ</a>'
                + f'<a class="btn ghost" href="{esc(aff("hotel", d["slug"]))}" target="_blank" rel="noopener sponsored" data-ev="hotel">🏨 Khách sạn</a></div>'
                + ''.join(sections)
                + '<section class="faq"><h2>Câu hỏi thường gặp</h2>' + ''.join(f'<h3>{esc(q)}</h3><p>{esc(a)}</p>' for q, a in faq) + '</section>'
                + (f'<h2>Bài viết về {esc(name)}</h2><div class="near">' + ''.join(f'<a href="/blog/{b["slug"]}/">{esc(b["title"])}</a>' for b in posts) + '</div>' if posts else '')
                + f'<h2>Điểm đến gần {esc(name)}</h2><div class="near">' + ''.join(f'<a href="/diem-den/{x["slug"]}/">{esc(x["title"])}</a>' for x in near) + '</div>'
                + f'<section class="cta"><h2>Lên lịch trình {esc(name)} trong 1 phút</h2><p>Kể chuyến đi bằng một câu (số ngày, ngân sách, đi cùng ai), Đi Đâu? sẽ xếp lịch theo giờ, tối ưu đường đi và ước tính chi phí.</p><a class="btn" href="/#go=plan:{k}" data-ev="plan-bottom">✨ Bắt đầu ngay</a></section>')
        ld = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'TouristDestination', 'name': name, 'description': d['intro'], 'url': full,
             'geo': {'@type': 'GeoCoordinates', 'latitude': round(d['lat'], 5), 'longitude': round(d['lng'], 5)},
             'containedInPlace': {'@type': 'AdministrativeArea', 'name': prov + ', Việt Nam'},
             **({'image': SITE + cover} if cover else {}),
             'includesAttraction': [{'@type': 'Restaurant' if p['cat'] == 'food' else 'TouristAttraction', 'name': p['name'],
                                     **({'address': p['addr']} if p.get('addr') else {}),
                                     'geo': {'@type': 'GeoCoordinates', 'latitude': p['lat'], 'longitude': p['lng']}} for p in ps]},
            crld]}
        out = PUB / 'diem-den' / d['slug']
        out.mkdir(parents=True, exist_ok=True)
        (out / 'index.html').write_text(page(title, desc, full, cover, body, ld, 'vn'), encoding='utf-8')
        urls.append((url, '0.7'))
    # trang tổng hợp
    groups = ''
    for r, label in REGION.items():
        ds = [d for d in dests if d['r'] == r]
        cards = ''.join(f'<a class="card" href="/diem-den/{d["slug"]}/"><div class="im">{img_tag(d["img"].get("f"), "", 480, 270)}</div><div class="bd"><h3>{esc(d["title"])}</h3><p>{esc(d["intro"])}</p><span>{esc(d["prov"])} · mùa đẹp {esc(months_txt(d["months"]))}</span></div></a>' for d in ds)
        groups += f'<h2 id="{r}">{esc(label)} ({len(ds)})</h2><div class="grid">{cards}</div>'
    cr, crld = crumbs([('Trang chủ', '/'), ('Điểm đến trong nước', None)])
    body = (cr + '<h1>77 điểm đến du lịch Việt Nam: ăn gì, chơi gì, mùa nào đẹp</h1>'
            + f'<p>Cẩm nang {len(VN["places"])} địa điểm ăn uống, check-in, tham quan ở 34 tỉnh thành theo địa giới mới. Chọn một điểm đến để xem chi tiết và lập lịch trình miễn phí.</p>'
            + f'<div class="hub">{groups}</div>')
    hub = page('77 điểm đến du lịch Việt Nam – cẩm nang 34 tỉnh thành | Đi Đâu?',
               'Danh sách 77 điểm đến du lịch Việt Nam theo vùng miền: món ngon, điểm check-in, tham quan, mùa đẹp và lịch trình gợi ý miễn phí.',
               SITE + '/diem-den/', None, body, {'@context': 'https://schema.org', '@graph': [crld]}, 'vn')
    hub = hub.replace('<main>', '<main style="max-width:1080px">')
    (PUB / 'diem-den' / 'index.html').write_text(hub, encoding='utf-8')
    urls.insert(0, ('/diem-den/', '0.8'))
    return urls, {d['key']: d['slug'] for d in dests}


# ------------------------------------------------------------------ QUỐC TẾ
def build_intl():
    K = {c['id']: c for c in INTL['countries']}
    urls = []
    for c in INTL['cities']:
        k = K[c['country']]
        url = f'/quoc-te/{c["id"]}/'
        full = SITE + url
        name = c['name']
        cover = (c.get('img') or {}).get('f')
        title = f'Du lịch {name} ({k["name"]}) tự túc: visa, ăn gì, chơi gì, mùa đẹp | Đi Đâu?'
        desc = f'Cẩm nang du lịch {name}, {k["name"]}: {c["intro"].rstrip(".")}. Visa cho người Việt, giờ bay, tỷ giá, mùa đẹp và {len(c["places"])} địa điểm nên đến.'[:300]
        cr, crld = crumbs([('Trang chủ', '/'), ('Du lịch quốc tế', '/quoc-te/'), (k['name'], f'/quoc-te/#{k["id"]}'), (name, None)])
        sections = []
        for cat, label in CATS:
            items = [p for p in c['places'] if p['cat'] == cat]
            if items:
                cards = ''.join(place_card(p, (p.get('img') or {}).get('f'), f'<a href="{esc(p["wp"])}" target="_blank" rel="noopener">Wikipedia</a>' if p.get('wp') else None) for p in items)
                sections.append(f'<h2>{esc(label.format(n=name))}</h2><div class="plist3">{cards}</div>')
        same = [x for x in INTL['cities'] if x['country'] == c['country'] and x['id'] != c['id']]
        others = [x for x in INTL['cities'] if x['country'] != c['country']][:8]
        fig = ''
        if cover:
            fig = f'<figure class="cover">{img_tag(cover, "Du lịch " + name, 960, 540)}</figure>'
            if (c.get('img') or {}).get('page'):
                fig += f'<p class="credit">Ảnh: <a href="{esc(c["img"]["page"])}" target="_blank" rel="noopener">{esc(c["img"].get("credit"))}</a> qua Wikimedia Commons</p>'
        faq = [(f'Người Việt đi {name} có cần visa không?', k['visa'] + f' (Thông tin tham khảo, cập nhật {UPDATED}; kiểm tra lại trước khi đi.)'),
               (f'Đi {name} mùa nào đẹp?', f'Đẹp nhất vào {months_txt(c["best"])}. Thời gian gợi ý: {c["days"]}.'),
               (f'Bay từ Việt Nam đến {name} mất bao lâu?', k['flight'] + '.'),
               (f'Tiền tệ ở {k["name"]} là gì?', f'{k["currency"]}; tỷ giá tham khảo {k["rate"]}.')]
        body = (cr + fig + f'<span class="tag">{esc(k["flag"])} {esc(k["name"])}</span>'
                + (' <span class="tag">Miễn visa</span>' if k.get('visaFree') else '')
                + f'<h1>Du lịch {esc(name)} tự túc: visa, ăn gì, chơi gì, mùa nào đẹp?</h1>'
                + f'<p class="meta">{esc(k["name"])} · {len(c["places"])} địa điểm · cập nhật {esc(UPDATED)}</p><p>{esc(c["intro"])}</p>'
                + f'<div class="facts2"><div><b>{"Miễn visa" if k.get("visaFree") else "Cần visa"}</b><span>Hộ chiếu Việt Nam</span></div>'
                + f'<div><b>{esc(months_txt(c["best"]).capitalize())}</b><span>Mùa đẹp</span></div><div><b>{esc(c["days"])}</b><span>Thời gian gợi ý</span></div>'
                + f'<div><b>{esc(k["rate"])}</b><span>{esc(k["currency"])}</span></div></div>'
                + f'<div class="ctas"><a class="btn" href="/#quoc-te/{c["id"]}" data-ev="intl-app">🗺 Xem bản đồ {esc(name)}</a>'
                + f'<a class="btn ghost" href="{esc(aff("activities", c["id"]))}" target="_blank" rel="noopener sponsored" data-ev="tour">🎟 Tour & vé</a>'
                + f'<a class="btn ghost" href="{esc(aff("hotel", c["id"]))}" target="_blank" rel="noopener sponsored" data-ev="hotel">🏨 Khách sạn</a></div>'
                + ''.join(sections)
                + f'<h2>Kinh nghiệm đi {esc(k["name"])}</h2><ul>' + ''.join(f'<li>{esc(t)}</li>' for t in k.get('tips', [])) + '</ul>'
                + '<section class="faq"><h2>Câu hỏi thường gặp</h2>' + ''.join(f'<h3>{esc(q)}</h3><p>{esc(a)}</p>' for q, a in faq) + '</section>'
                + (f'<h2>Điểm khác ở {esc(k["name"])}</h2><div class="near">' + ''.join(f'<a href="/quoc-te/{x["id"]}/">{esc(x["name"])}</a>' for x in same) + '</div>' if same else '')
                + '<h2>Điểm đến quốc tế khác</h2><div class="near">' + ''.join(f'<a href="/quoc-te/{x["id"]}/">{esc(x["name"])}</a>' for x in others) + '</div>')
        ld = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'TouristDestination', 'name': name, 'description': c['intro'], 'url': full,
             **({'geo': {'@type': 'GeoCoordinates', 'latitude': round(c['lat'], 5), 'longitude': round(c['lng'], 5)}} if c.get('lat') is not None else {}),
             'containedInPlace': {'@type': 'Country', 'name': k['name']},
             **({'image': SITE + cover} if cover else {}),
             'includesAttraction': [{'@type': 'Restaurant' if p['cat'] == 'food' else 'TouristAttraction', 'name': p['name'],
                                     **({'geo': {'@type': 'GeoCoordinates', 'latitude': p['lat'], 'longitude': p['lng']}} if p.get('lat') is not None else {})} for p in c['places']]},
            crld]}
        out = PUB / 'quoc-te' / c['id']
        out.mkdir(parents=True, exist_ok=True)
        (out / 'index.html').write_text(page(title, desc, full, cover, body, ld, 'intl'), encoding='utf-8')
        urls.append((url, '0.7'))
    groups = ''
    for k in INTL['countries']:
        cs = [c for c in INTL['cities'] if c['country'] == k['id']]
        cards = ''.join(f'<a class="card" href="/quoc-te/{c["id"]}/"><div class="im">{img_tag((c.get("img") or {}).get("f"), "", 480, 270)}</div><div class="bd"><h3>{esc(c["name"])}</h3><p>{esc(c["intro"])}</p><span>{"Miễn visa · " if k.get("visaFree") else ""}mùa đẹp {esc(months_txt(c["best"]))}</span></div></a>' for c in cs)
        groups += f'<h2 id="{k["id"]}">{esc(k["flag"])} Du lịch {esc(k["name"])}</h2><p>{esc(k["visa"])}</p><div class="grid">{cards}</div>'
    cr, crld = crumbs([('Trang chủ', '/'), ('Du lịch quốc tế', None)])
    body = (cr + '<h1>Du lịch nước ngoài tự túc: Thái Lan, Trung Quốc, Hàn Quốc, Nhật Bản, Singapore…</h1>'
            + f'<p>Cẩm nang {len(INTL["cities"])} thành phố được khách Việt đặt tour nhiều: visa cho hộ chiếu Việt Nam, mùa đẹp, tỷ giá, món ngon và điểm check-in. Thông tin cập nhật {esc(UPDATED)}.</p>'
            + f'<div class="hub">{groups}</div>')
    hub = page('Du lịch nước ngoài tự túc: visa, mùa đẹp, ăn gì chơi gì | Đi Đâu?',
               'Cẩm nang du lịch Thái Lan, Trung Quốc, Hàn Quốc, Nhật Bản, Singapore, Malaysia, Đài Loan, Bali cho người Việt: visa, mùa đẹp, tỷ giá, điểm đến nổi bật.',
               SITE + '/quoc-te/', None, body, {'@context': 'https://schema.org', '@graph': [crld]}, 'intl')
    (PUB / 'quoc-te' / 'index.html').write_text(hub.replace('<main>', '<main style="max-width:1080px">'), encoding='utf-8')
    urls.insert(0, ('/quoc-te/', '0.8'))
    return urls


if __name__ == '__main__':
    u1, slugs = build_vn()
    u2 = build_intl()
    (ROOT / 'tools' / 'page_urls.json').write_text(json.dumps(u1 + u2, ensure_ascii=False, indent=0), encoding='utf-8')
    (PUB / 'data' / 'dest_slugs.json').write_text(json.dumps(slugs, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Đã tạo {len(u1) - 1} trang trong nước + {len(u2) - 1} trang quốc tế + 2 trang tổng hợp')
