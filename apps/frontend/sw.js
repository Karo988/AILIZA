const CACHE = 'ailiza-v1';
const OFFLINE = ['/'];

self.addEventListener('install', e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE)))
);

self.addEventListener('fetch', e => {
  // API-Calls nie cachen
  if (e.request.url.includes('/agent/') || e.request.url.includes('/chat')) {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
