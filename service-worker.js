// Bump these versions when you want all clients to refetch (e.g. after data changes).
const STATIC_CACHE = 'plants-static-v2';
const IMAGES_CACHE = 'plants-images-v2';
const API_CACHE = 'plants-api-v2';

// Pages cached on install (relative to SW scope, so works under any subpath like /Plants/)
const STATIC_FILES = [
  './',
  'index.html',
  'plants-catalog.html',
  'water-groups.html',
  'humidity-groups.html',
  'lighting-score.html',
  'soil-groups.html',
  'feeding-guide.html',
  'water-mixer.html',
  'my-products.html',
  'plant-problems.html',
  'seasonal-care.html',
  'propagation.html',
  'pests-diseases.html',
  'rotation.html',
  'garden.html',
  'manifest.json',
  // Machine-readable knowledge for offline AI / quick lookups
  'api/index.json',
  'api/catalog.json',
  'api/soil-mixes.json',
  'api/water-groups.json',
  'api/feeding.json',
  'api/diagnostics.json',
  'api/pesticides.json'
];

// Install event - cache static files
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static files');
        return cache.addAll(STATIC_FILES);
      })
      .then(() => {
        console.log('[SW] Static files cached');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[SW] Failed to cache static files:', error);
      })
  );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  const keep = new Set([STATIC_CACHE, IMAGES_CACHE, API_CACHE]);
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('plants-') && !keep.has(name))
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[SW] Activated');
      return self.clients.claim();
    })
  );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip cross-origin requests
  if (url.origin !== location.origin) {
    return;
  }

  // Handle image requests (works under any subpath: /IMAGES/ or /Plants/IMAGES/)
  if (url.pathname.includes('/IMAGES/')) {
    event.respondWith(
      caches.open(IMAGES_CACHE).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(event.request).then((networkResponse) => {
            if (networkResponse.ok) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          }).catch(() => {
            // Return placeholder for failed image loads
            return new Response('', { status: 404, statusText: 'Not Found' });
          });
        });
      })
    );
    return;
  }

  // Handle API JSON: stale-while-revalidate. Always show cached if exists, refresh in background.
  // This keeps offline answers fast and correct even when offline.
  if (url.pathname.includes('/api/') && url.pathname.endsWith('.json')) {
    event.respondWith(
      caches.open(API_CACHE).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          const networkFetch = fetch(event.request).then((networkResponse) => {
            if (networkResponse.ok) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          }).catch(() => cachedResponse);
          return cachedResponse || networkFetch;
        });
      })
    );
    return;
  }

  // Handle HTML/static requests
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Return cached version, but also fetch update in background
        event.waitUntil(
          fetch(event.request).then((networkResponse) => {
            if (networkResponse.ok) {
              caches.open(STATIC_CACHE).then((cache) => {
                cache.put(event.request, networkResponse);
              });
            }
          }).catch(() => {
            // Network failed, that's ok - we have cache
          })
        );
        return cachedResponse;
      }

      // Not in cache, fetch from network
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse.ok) {
          const responseClone = networkResponse.clone();
          caches.open(STATIC_CACHE).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      }).catch(() => {
        // Offline and not in cache - show offline page (resolved relative to SW scope)
        if (event.request.headers.get('accept').includes('text/html')) {
          return caches.match('index.html') || caches.match('./');
        }
        return new Response('Offline', { status: 503 });
      });
    })
  );
});

// Handle background sync (for future features)
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);
});

// Handle push notifications (for future features)
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event.data?.text());
});
