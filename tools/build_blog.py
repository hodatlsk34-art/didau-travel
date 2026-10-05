#!/usr/bin/env python3
"""Tạo Blog từ các file bài viết.

Đọc  content/blog/*.md  (mỗi bài một file: phần đầu ghi tiêu đề, ngày, ảnh bìa…; phần sau là nội dung)
     public/images/credits.json (ảnh bìa có sẵn của 77 điểm đến)
     public/images/uploads/* (ảnh tự tải lên qua trang quản trị /admin)
Ghi  public/blog/posts.json (app đọc), public/blog/<slug>/index.html, public/blog/index.html,
     public/sitemap.xml, public/images/uploads/opt/*.webp (ảnh đã thu nhỏ)

Chạy lại mỗi khi thêm/sửa bài:  python3 tools/build_blog.py
(GitHub Action .github/workflows/blog.yml tự chạy khi có bài mới.)
"""
import html, json, re, datetime, hashlib, unicodedata
from pathlib import Path
from urllib.parse import quote, unquote
import yaml
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / 'public'
SITE = 'https://didautravel.id.vn'
GA_ID = 'G-4SZ0F47T3Z'

CONTENT = ROOT / 'content' / 'blog'
UPLOADS = PUB / 'images' / 'uploads'
credits = json.loads((PUB / 'images/credits.json').read_text(encoding='utf-8'))
esc = lambda s: html.escape(str(s or ''), quote=True)


def slugify(s):
    s = unicodedata.normalize('NFD', str(s)).replace('đ', 'd').replace('Đ', 'D')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:80].strip('-')


def opt_image(src, width=1600):
    """Ảnh tải lên (/images/uploads/x.jpg) -> bản webp đã thu nhỏ. Trả về đường dẫn web."""
    if not isinstance(src, str) or not src.startswith('/images/uploads/') or '/opt/' in src:
        return src
    f = PUB / unquote(src.strip()).lstrip('/')
    if not f.is_file():
        print('  ! Không thấy ảnh', src); return None
    h = hashlib.md5(f.read_bytes()).hexdigest()[:8]
    out = UPLOADS / 'opt' / f'{slugify(f.stem) or "anh"}-{h}.webp'
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        im = ImageOps.exif_transpose(Image.open(f))
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') else 'RGB')
        im.thumbnail((width, width))
        im.save(out, 'WEBP', quality=82, method=6)
    return '/' + str(out.relative_to(PUB)).replace('\\', '/')


def to_date(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    m = re.match(r'\d{4}-\d{2}-\d{2}', str(v or ''))
    return m[0] if m else datetime.date.today().isoformat()


def plain(t):
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)|\[\[dest:[^\]]*\]\]', '', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    return re.sub(r'[#>*_`\\]+', '', t).strip()


def load_posts():
    out, seen = [], set()
    for f in sorted(CONTENT.glob('*.md')):
        txt = f.read_text(encoding='utf-8').replace('\r\n', '\n')
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', txt, re.S)
        if not m:
            print('  ! Bỏ qua (thiếu phần đầu ---):', f.name); continue
        fm = yaml.safe_load(m[1]) or {}
        body = m[2].strip()
        if fm.get('draft') or not fm.get('title') or not body:
            continue
        slug = slugify(fm.get('slug') or f.stem) or slugify(fm['title'])
        while slug in seen:
            slug += '-2'
        seen.add(slug)
        tags = fm.get('tags') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
        cover_key = str(fm.get('cover') or '').strip()
        cover_img = opt_image(fm.get('cover_image')) if fm.get('cover_image') else None
        body = re.sub(r'(!\[[^\]]*\]\()<?(/images/uploads/[^)>\n]+?)>?(\))', lambda x: x[1] + (opt_image(x[2]) or x[2].replace(' ', '%20')) + x[3], body)
        if cover_key in credits and '[[dest:' not in body.replace('\\', ''):
            body += f'\n\n[[dest:{cover_key}|Lên lịch trình {cover_key.split("|")[-1]}]]'
        excerpt = str(fm.get('excerpt') or '').strip()
        if not excerpt:
            first = next((plain(x) for x in body.split('\n\n') if plain(x) and not x.lstrip().startswith('#')), '')
            excerpt = first[:180] + ('…' if len(first) > 180 else '')
        out.append({'slug': slug, 'title': str(fm['title']).strip(), 'date': to_date(fm.get('date')),
                    'author': str(fm.get('author') or 'Đi Đâu?'), 'cover': cover_key, 'coverImg': cover_img or '',
                    'tags': [str(t) for t in tags if str(t).strip()][:6], 'excerpt': excerpt, 'body': body})
    out.sort(key=lambda p: p['date'], reverse=True)
    return out


posts = load_posts()


def fmt_date(d):
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', d or '')
    return f'{m[3]}/{m[2]}/{m[1]}' if m else ''


def cover(p):
    if p.get('coverImg'):
        return {'f': p['coverImg']}
    c = credits.get(p.get('cover') or '')
    if c and re.fullmatch(r'/images/(dest2?|place)/[\w.-]+\.webp', c.get('f', '')):
        return c
    return None


def dest_name(key):
    return key.split('|')[-1]


ESC_CH = r'\\`*_{}\[\]()#+\-.!|~>'


def inline(t):
    r"""t đã escape HTML. Hỗ trợ **đậm**, *nghiêng*, _nghiêng_, [link](url), ![ảnh](url), dấu \ thoát."""
    keep = []
    t = re.sub(r'\\([' + ESC_CH + r'])', lambda m: (keep.append(m[1]), f'\x00{len(keep)-1}\x00')[1], t)
    t = re.sub(r'!\[([^\]]*)\]\((/[^\s)]+|https?://[^\s)]+)\)', r'<img src="\2" alt="\1" loading="lazy">', t)
    t = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: '<b>' + (m[1] or m[2]) + '</b>', t)
    t = re.sub(r'(^|[^\w*])\*([^\s*](?:[^*]*?[^\s*])?)\*(?!\*)', r'\1<i>\2</i>', t)
    t = re.sub(r'(^|[^\w_])_([^\s_](?:[^_]*?[^\s_])?)_(?!\w)', r'\1<i>\2</i>', t)
    t = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r'\[([^\]]+)\]\((/[^\s)]*)\)', r'<a href="\2">\1</a>', t)
    return re.sub(r'\x00(\d+)\x00', lambda m: keep[int(m[1])], t)


def md(src):
    out, lst = [], None   # lst = [tag, items]

    def flush():
        nonlocal lst
        if lst:
            out.append(f'<{lst[0]}>' + ''.join(lst[1]) + f'</{lst[0]}>')
            lst = None

    def add_li(tag, text):
        nonlocal lst
        if not lst or lst[0] != tag:
            flush(); lst = [tag, []]
        lst[1].append('<li>' + inline(esc(text)) + '</li>')
    for raw in str(src).split('\n'):
        line = raw.strip()
        if not line:
            flush(); continue
        m = re.fullmatch(r'\[\[dest:(.+)\]\]', re.sub(r'\\([\[\]|_*-])', r'\1', line))
        if m:
            flush()
            parts = m[1].split('|')
            label = parts.pop() if len(parts) > 2 else 'Lên lịch trình'
            key = '|'.join(parts)
            k = quote(key, safe='')
            out.append(f'<div class="cta-in"><a class="btn" href="/#go=plan:{k}" data-ev="plan">✨ {esc(label)}</a>'
                       f'<a class="btn ghost" href="/#go=dest:{k}" data-ev="dest">🧭 Xem địa điểm ở {esc(dest_name(key))}</a></div>')
            continue
        h = re.match(r'(#{1,6})\s+(.*)', line)
        if h:
            flush(); tag = 'h2' if len(h[1]) <= 2 else 'h3'
            out.append(f'<{tag}>' + inline(esc(h[2].rstrip('#').strip())) + f'</{tag}>'); continue
        if re.fullmatch(r'(-\s*){3,}|(\*\s*){3,}|(_\s*){3,}', line):
            flush(); out.append('<hr>'); continue
        im = re.fullmatch(r'!\[([^\]]*)\]\((/[^\s)]+|https?://[^\s)]+)\)', line)
        if im:
            flush(); cap = esc(im[1])
            out.append(f'<figure class="pimg"><img src="{esc(im[2])}" alt="{cap}" loading="lazy">' + (f'<figcaption>{cap}</figcaption>' if cap else '') + '</figure>'); continue
        li = re.match(r'[-*+]\s+(.*)', line)
        if li:
            add_li('ul', li[1]); continue
        ol = re.match(r'\d+[.)]\s+(.*)', line)
        if ol:
            add_li('ol', ol[1]); continue
        if line.startswith('>'):
            flush(); out.append('<blockquote>' + inline(esc(line.lstrip('> ').strip())) + '</blockquote>'); continue
        flush(); out.append('<p>' + inline(esc(line)) + '</p>')
    flush()
    return ''.join(out)


CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://gc.zgo.at https://www.googletagmanager.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: https://didau.goatcounter.com https://*.google-analytics.com https://www.googletagmanager.com; "
       "connect-src 'self' https://didau.goatcounter.com https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; "
       "frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests")

CSS = """
:root{--ink:#14283a;--mut:#4f6577;--acc:#0E4C8E;--acc2:#F28A1E;--green:#22803A;--bg:#F3F7FA;--card:#fff;--line:#dbe5ec}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.7 "Be Vietnam Pro",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--acc)}
.top{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.top-in{max-width:1080px;margin:0 auto;padding:8px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.logo{display:flex;align-items:center;gap:8px;text-decoration:none;color:var(--acc);font:800 22px/1 Lexend,sans-serif}
.logo img{width:40px;height:40px;object-fit:contain}
.logo small{display:block;font:600 10.5px/1.2 "Be Vietnam Pro",sans-serif;color:var(--green);letter-spacing:.04em;text-transform:uppercase}
.nav{display:flex;gap:6px}
.nav a{text-decoration:none;font:600 14px/1 Lexend,sans-serif;padding:9px 13px;border-radius:999px;color:var(--ink)}
.nav a.on{background:var(--acc);color:#fff}
.nav a.app{background:var(--acc2);color:#fff}
main{max-width:760px;margin:0 auto;padding:20px 16px 48px}
.crumb{font-size:14px;color:var(--mut);margin:0 0 12px}
.crumb a{color:var(--mut);text-decoration:none}
.crumb a:hover{color:var(--acc)}
figure.cover{margin:0 0 18px;border-radius:18px;overflow:hidden;background:#dfe9ef;aspect-ratio:16/9}
figure.cover img{width:100%;height:100%;object-fit:cover;display:block}
.credit{font-size:12px;color:var(--mut);margin:-12px 0 18px}
.credit a{color:var(--mut)}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.tag{font:600 12px/1 "Be Vietnam Pro",sans-serif;background:#e6eef5;color:var(--acc);padding:6px 10px;border-radius:999px}
h1{font:700 clamp(26px,5vw,36px)/1.2 Lexend,sans-serif;margin:0 0 8px;text-wrap:balance}
.meta{color:var(--mut);font-size:14px;margin:0 0 22px}
article h2{font:700 22px/1.3 Lexend,sans-serif;margin:30px 0 8px;color:var(--acc)}
article p{margin:0 0 14px}
article ul{padding-left:22px;margin:0 0 16px}
article li{margin:5px 0}
article ol{padding-left:24px;margin:0 0 16px}
article h3{font:700 18px/1.35 Lexend,sans-serif;margin:22px 0 6px}
article img{max-width:100%;height:auto;border-radius:14px}
figure.pimg{margin:18px 0}figure.pimg figcaption{font-size:13.5px;color:var(--mut);text-align:center;margin-top:6px}
article blockquote{margin:0 0 16px;padding:10px 16px;border-left:4px solid var(--acc2);background:#fff;border-radius:0 12px 12px 0}
article hr{border:0;border-top:1px solid var(--line);margin:24px 0}
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--acc);color:#fff;text-decoration:none;font:600 15px/1.2 Lexend,sans-serif;padding:12px 18px;border-radius:12px}
.btn.ghost{background:#fff;color:var(--acc);border:1.5px solid var(--acc)}
.cta-in{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 22px}
.cta{margin:34px 0 0;padding:22px;border-radius:18px;background:linear-gradient(135deg,#0E4C8E,#1b6fb8);color:#fff}
.cta h2{font:700 21px/1.3 Lexend,sans-serif;margin:0 0 6px;color:#fff}
.cta p{margin:0 0 14px;opacity:.92}
.cta .btn{background:var(--acc2)}
.more{max-width:1080px;margin:0 auto;padding:0 16px 40px}
.more h2,.list-h h1{font:700 22px/1.3 Lexend,sans-serif;margin:0 0 14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;text-decoration:none;color:inherit;box-shadow:0 6px 18px rgba(16,40,34,.07);transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-3px);box-shadow:0 12px 26px rgba(16,40,34,.13)}
.card .im{flex:none;aspect-ratio:16/9;overflow:hidden;background:#dfe9ef}
.card .im img{width:100%;height:100%;aspect-ratio:16/9;object-fit:cover;display:block}
.card .bd{padding:14px 16px 16px;display:flex;flex-direction:column;gap:6px}
.card h3{font:700 17px/1.35 Lexend,sans-serif;margin:0}
.card p{font-size:14.5px;line-height:1.55;color:var(--mut);margin:0}
.card span{font-size:13px;color:var(--mut)}
.list-h{max-width:1080px;margin:0 auto;padding:24px 16px 6px}
.list-h p{color:var(--mut);margin:-6px 0 14px}
footer{border-top:1px solid var(--line);background:#fff}
.ft{max-width:1080px;margin:0 auto;padding:20px 16px 28px;display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;color:var(--mut)}
.ft a{color:var(--mut)}
@media (max-width:560px){ .nav a:not(.app){display:none} .logo small{display:none} body{font-size:16.5px} }
"""


def head(title, desc, url, image=None, extra=''):
    img = SITE + image if image else SITE + '/og.jpg'
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Đi Đâu?">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0E4C8E">
<link rel="icon" type="image/png" href="/favicon64.png"><link rel="apple-touch-icon" href="/apple180.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lexend:wght@600;700;800&family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap">
<script>
window.GA_ID='{GA_ID}';
(function(){{ if(location.protocol!=='https:') return;
  window.dataLayer=window.dataLayer||[]; window.gtag=function(){{ dataLayer.push(arguments); }};
  gtag('js',new Date()); gtag('config',window.GA_ID);
  var s=document.createElement('script'); s.async=true; s.src='https://www.googletagmanager.com/gtag/js?id='+window.GA_ID; document.head.appendChild(s);
  var g=document.createElement('script'); g.async=true; g.src='https://gc.zgo.at/count.js'; g.setAttribute('data-goatcounter','https://didau.goatcounter.com/count'); document.head.appendChild(g); }})();
</script>
{extra}<style>{CSS}</style></head><body>"""


def topbar(active):
    return f"""<header class="top"><div class="top-in">
<a class="logo" href="/"><img src="/images/logo-art-520.webp" alt="" width="40" height="40"><span>Đi Đâu?<small>AI Travel Planner Việt Nam</small></span></a>
<nav class="nav"><a href="/">Trang chủ</a><a href="/blog/"{' class="on"' if active == 'blog' else ''}>Blog</a><a class="app" href="/">✨ Lập lịch trình</a></nav>
</div></header>"""


FOOT = """<footer><div class="ft"><span>© 2026 Đi Đâu? – AI Travel Planner Việt Nam</span>
<a href="/">Trang chủ</a><a href="/blog/">Blog</a><a href="/dieu-khoan.html">Điều khoản sử dụng</a><a href="/chinh-sach-bao-mat.html">Chính sách bảo mật</a></div></footer>
<script>document.addEventListener('click',function(e){ var a=e.target.closest&&e.target.closest('[data-ev]'); if(a&&window.gtag) gtag('event','blog_cta',{cta:a.dataset.ev,post:location.pathname}); });</script>
</body></html>
"""


def card(p):
    c = cover(p)
    im = f'<img src="{c["f"]}" alt="" loading="lazy" width="480" height="270">' if c else ''
    return (f'<a class="card" href="/blog/{p["slug"]}/"><div class="im">{im}</div><div class="bd">'
            f'<h3>{esc(p["title"])}</h3><p>{esc(p.get("excerpt"))}</p><span>{fmt_date(p.get("date"))}</span></div></a>')


def post_page(p):
    url = f'{SITE}/blog/{p["slug"]}/'
    c = cover(p)
    desc = (p.get('excerpt') or '')[:300]
    first_dest = re.search(r'\[\[dest:([^\]|]+\|[^\]|]+)', p['body'])
    dkey = first_dest[1] if first_dest else (p.get('cover') if (p.get('cover') or '') in credits else None)
    ld = {
        '@context': 'https://schema.org',
        '@graph': [
            {'@type': 'BlogPosting', 'headline': p['title'], 'description': desc,
             'datePublished': p.get('date'), 'dateModified': p.get('date'), 'inLanguage': 'vi',
             'author': {'@type': 'Organization', 'name': p.get('author') or 'Đi Đâu?', 'url': SITE + '/'},
             'publisher': {'@type': 'Organization', 'name': 'Đi Đâu?', 'logo': {'@type': 'ImageObject', 'url': SITE + '/icons/icon-512.png'}},
             'mainEntityOfPage': url, 'image': SITE + (c['f'] if c else '/og.jpg'), 'keywords': ', '.join(p.get('tags') or [])},
            {'@type': 'BreadcrumbList', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': 'Đi Đâu?', 'item': SITE + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': 'Blog', 'item': SITE + '/blog/'},
                {'@type': 'ListItem', 'position': 3, 'name': p['title'], 'item': url}]}]}
    ldj = json.dumps(ld, ensure_ascii=False).replace('</', '<\\/')
    fig = (f'<figure class="cover"><img src="{c["f"]}" alt="{esc(p["title"])}" width="960" height="540"></figure>'
           + (f'<p class="credit">Ảnh: <a href="{esc(c["page"])}" target="_blank" rel="noopener">{esc(c.get("credit"))}</a> qua Wikimedia Commons</p>' if c.get('page') else '')) if c else ''
    tags = ''.join(f'<span class="tag">{esc(t)}</span>' for t in p.get('tags') or [])
    if dkey:
        k = quote(dkey, safe='')
        cta = (f'<section class="cta"><h2>Đi {esc(dest_name(dkey))} mấy ngày, bao nhiêu tiền?</h2>'
               f'<p>Đi Đâu? lập lịch trình theo giờ, ước tính chi phí và chỉ đường giữa các điểm – miễn phí, không cần đăng ký.</p>'
               f'<a class="btn" href="/#go=plan:{k}" data-ev="plan-bottom">✨ Lập lịch trình {esc(dest_name(dkey))}</a></section>')
    else:
        cta = ('<section class="cta"><h2>Chưa biết đi đâu?</h2><p>Kể chuyến đi bằng một câu (ngân sách, số ngày, đi cùng ai), '
               'Đi Đâu? sẽ gợi ý điểm đến và lập lịch trình cho bạn.</p><a class="btn" href="/" data-ev="home-bottom">✨ Thử ngay</a></section>')
    more = [x for x in posts if x['slug'] != p['slug']][:3]
    more_html = f'<section class="more"><h2>Bài viết khác</h2><div class="grid">{"".join(card(x) for x in more)}</div></section>' if more else ''
    return (head(f'{p["title"]} | Blog Đi Đâu?', desc, url, c['f'] if c else None,
                 f'<script type="application/ld+json">{ldj}</script>\n')
            + topbar('blog')
            + f'<main><nav class="crumb"><a href="/">Trang chủ</a> › <a href="/blog/">Blog</a></nav><article>{fig}<div class="tags">{tags}</div>'
            + f'<h1>{esc(p["title"])}</h1><p class="meta">{fmt_date(p.get("date"))} · {esc(p.get("author") or "Đi Đâu?")}</p>'
            + md(p['body']) + cta + '</article></main>' + more_html + FOOT)


def index_page():
    url = SITE + '/blog/'
    return (head('Blog du lịch Việt Nam – kinh nghiệm, lịch trình gợi ý | Đi Đâu?',
                 'Cẩm nang du lịch Việt Nam: mùa đẹp, món ngon, lịch trình gợi ý và mẹo đi chơi cùng gia đình từ Đi Đâu? – AI Travel Planner Việt Nam.', url)
            + topbar('blog')
            + '<div class="list-h"><h1>📖 Blog Đi Đâu?</h1><p>Cẩm nang, kinh nghiệm và lịch trình gợi ý cho chuyến đi của bạn.</p></div>'
            + f'<section class="more"><div class="grid">{"".join(card(p) for p in posts)}</div></section>' + FOOT)


def sitemap():
    today = datetime.date.today().isoformat()
    rows = [(SITE + '/', today, 'weekly', '1.0'), (SITE + '/blog/', today, 'weekly', '0.8')]
    rows += [(f'{SITE}/blog/{p["slug"]}/', p.get('date') or today, 'monthly', '0.7') for p in posts]
    rows += [(SITE + '/chinh-sach-bao-mat.html', today, 'yearly', '0.2'), (SITE + '/dieu-khoan.html', today, 'yearly', '0.2')]
    body = ''.join(f'  <url><loc>{u}</loc><lastmod>{d}</lastmod><changefreq>{f}</changefreq><priority>{pr}</priority></url>\n' for u, d, f, pr in rows)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n'


if __name__ == '__main__':
    keep = {p['slug'] for p in posts}
    for d in (PUB / 'blog').iterdir():
        if d.is_dir() and d.name not in keep and (d / 'index.html').exists():
            (d / 'index.html').unlink(); d.rmdir()
    for p in posts:
        out = PUB / 'blog' / p['slug']; out.mkdir(parents=True, exist_ok=True)
        (out / 'index.html').write_text(post_page(p), encoding='utf-8')
    (PUB / 'blog/index.html').write_text(index_page(), encoding='utf-8')
    (PUB / 'blog/posts.json').write_text(json.dumps(posts, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (PUB / 'sitemap.xml').write_text(sitemap(), encoding='utf-8')
    print(f'Đã tạo {len(posts)} bài + trang danh sách + sitemap.xml')
