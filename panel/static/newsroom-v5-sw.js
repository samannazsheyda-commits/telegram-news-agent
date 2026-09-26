// Served by the panel at /sw.js (scope /v5); VERSION is a hash of the V5 assets.
// /static/sw.js is the separate legacy V4 worker.
const VERSION = '__V5_ASSET_VERSION__';
const CACHE_PREFIX = 'bikhabar-newsroom-v5-';
const CACHE = CACHE_PREFIX + VERSION;
const LEGACY_CACHE = 'bikhabar-newsroom-v4-1';
const STATIC_SHELL = [
  `/static/newsroom-v5-app.css?v=${VERSION}`,
  `/static/newsroom-v5-review.js?v=${VERSION}`,
  `/static/newsroom-v5-app.js?v=${VERSION}`,
  '/static/manifest.webmanifest',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(STATIC_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    const stale = keys.filter(key => key !== CACHE && (key.startsWith(CACHE_PREFIX) || key === LEGACY_CACHE));
    const hadPreviousV5 = stale.some(key => key.startsWith(CACHE_PREFIX));
    await Promise.all(stale.map(key => caches.delete(key)));
    await self.clients.claim();
    if (hadPreviousV5) {
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      clients.forEach(client => client.postMessage({ type: 'NEW_VERSION_AVAILABLE', cache: CACHE }));
    }
  })());
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
    // A redirect here is the login page after session expiry; it must never become the shell.
    if (response.ok && response.type === 'basic' && !response.redirected) await cache.put('/v5', response.clone());
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

  if (url.pathname.startsWith('/static/newsroom-v5-') || url.pathname === '/static/manifest.webmanifest') {
    event.respondWith(staleWhileRevalidate(event.request));
  }
});
