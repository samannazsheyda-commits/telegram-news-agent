const CACHE = 'bikhabar-command-center-v1';
const SHELL = ['/static/panel.css', '/static/live.js', '/static/manifest.webmanifest'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function networkOnly(request) {
  return fetch(request, { cache: 'no-store' });
}

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/' || url.pathname.startsWith('/login') || url.pathname.startsWith('/review') || url.pathname.startsWith('/history') || url.pathname.startsWith('/sources')) {
    event.respondWith(networkOnly(event.request));
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, clone));
        }
        return response;
      }))
    );
  }
});
