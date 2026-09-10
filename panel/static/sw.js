const CACHE = 'bikhabar-newsroom-v4';
const SHELL = [
  '/static/panel.css',
  '/static/newsroom.css',
  '/static/newsroom-nav-v2.css',
  '/static/newsroom-compact.css',
  '/static/live.js',
  '/static/settings.css',
  '/static/settings.js',
  '/static/manifest.webmanifest',
];

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
      fetch(event.request, { cache: 'no-store' }).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => caches.match(event.request))
    );
  }
});
