/**
 * Service Worker for Porterminal PWA
 * Caches UI assets for offline access
 */

const CACHE_NAME = 'porterminal-v1';
const STATIC_ASSETS = [
    '/',
    '/static/index.html',
    '/static/manifest.json',
    '/static/icon.svg',
];

// Install - cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate - clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Don't cache WebSocket or API requests
    if (url.pathname.startsWith('/ws') || url.pathname.startsWith('/api')) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cached) => {
            // Return cached version or fetch from network
            return cached || fetch(event.request).then((response) => {
                // Cache successful responses
                if (response.ok && event.request.method === 'GET') {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        }).catch(() => {
            // Offline fallback
            if (event.request.destination === 'document') {
                return caches.match('/');
            }
        })
    );
});
