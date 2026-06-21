const CACHE = 'ailiza-v1';
const CACHED = ['/', '/index.html', '/config.js', '/manifest.json', '/icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CACHED)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  // Never cache API calls
  if (url.includes('/agent/') || url.includes('/chat') ||
      url.includes('/approvals') || url.includes('/health') ||
      url.includes('/llm/')) return;

  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
