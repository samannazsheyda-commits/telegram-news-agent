const CACHE = 'bikhabar-newsroom-v5-1';
const LEGACY_CACHE = 'bikhabar-newsroom-v4-1';
const STATIC_SHELL = [
  '/static/newsroom-v5-app.css',
  '/static/newsroom-v5-review.js',
  '/static/newsroom-v5-app.js',
  '/static/manifest.webmanifest',
  '/static/newsroom-v4.css',
  '/static/newsroom-v4-polish.css',
  '/static/newsroom-v4.js',
  '/static/newsroom-v4-dashboard.js',
  '/static/newsroom-v4-luna.css',
  '/static/luna-assistant.js',
  '/static/settings.css',
  '/static/settings.js',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(STATIC_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: 'window', includeUncontrolled: true }))
      .then(clients => Promise.all(clients.map(client => client.postMessage({ type: 'NEW_VERSION_AVAILABLE', cache: CACHE, replaced: LEGACY_CACHE }))))
  );
});

function networkOnly(request) {
  return fetch(request, { cache: 'no-store' });
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const network = fetch(request, { cache: 'no-cache' }).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  });
  return cached || network;
}

async function networkFirstShell(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request, { cache: 'no-store' });
    if (response.ok && response.type === 'basic') await cache.put('/v5', response.clone());
    return response;
  } catch (error) {
    const fallback = await caches.match('/v5');
    if (fallback) return fallback;
    throw error;
  }
}

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  if (url.pathname === '/v5') {
    event.respondWith(networkFirstShell(event.request));
    return;
  }

  if (
    url.pathname === '/' ||
    url.pathname.startsWith('/login') ||
    url.pathname.startsWith('/review') ||
    url.pathname.startsWith('/history') ||
    url.pathname.startsWith('/sources') ||
    url.pathname.startsWith('/source-manager') ||
    url.pathname.startsWith('/luna') ||
    url.pathname.startsWith('/intake') ||
    url.pathname.startsWith('/settings') ||
    url.pathname.startsWith('/system')
  ) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(staleWhileRevalidate(event.request));
  }
});
