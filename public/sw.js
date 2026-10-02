/* Đi Đâu? – service worker: chạy offline cơ bản cho bản app & PWA */
const VER = 'didau-v1';
const SHELL = [
  '/', '/manifest.webmanifest', '/offline.html',
  '/icons/icon-192.png', '/icons/icon-512.png',
  '/images/didau-banner-1672x193.webp', '/images/didau-banner-mobile-882x193.webp',
  '/images/didau-bg-v2-1920x1080.webp'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Trang chính: lấy bản mới nhất từ mạng, mất mạng thì dùng bản đã lưu
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then(r => {
        const copy = r.clone();
        caches.open(VER).then(c => c.put('/', copy));
        return r;
      }).catch(() => caches.match('/').then(r => r || caches.match('/offline.html')))
    );
    return;
  }

  // Tài nguyên cùng tên miền + ảnh Wikimedia + thư viện bản đồ: ưu tiên bộ nhớ đệm
  const cacheable = url.origin === location.origin
    || url.hostname === 'upload.wikimedia.org'
    || url.hostname === 'cdnjs.cloudflare.com'
    || url.hostname === 'fonts.gstatic.com';
  if (!cacheable) return;

  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === 'opaque') {
        const copy = r.clone();
        caches.open(VER).then(c => c.put(req, copy));
      }
      return r;
    }))
  );
});
