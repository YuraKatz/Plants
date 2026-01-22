const CACHE_NAME = 'plants-care-v1';
const STATIC_CACHE = 'plants-static-v1';
const IMAGES_CACHE = 'plants-images-v1';

// Files to cache immediately on install
const STATIC_FILES = [
  '/',
  '/index.html',
  '/plants-catalog.html',
  '/water-groups.html',
  '/lighting-groups.html',
  '/soil-groups.html',
  '/feeding-guide.html',
  '/water-mixer.html',
  '/my-products.html',
  '/plant-problems.html',
  '/seasonal-care.html',
  '/propagation.html',
  '/pests-diseases.html',
  '/manifest.json'
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
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => {
            return name.startsWith('plants-') &&
                   name !== STATIC_CACHE &&
                   name !== IMAGES_CACHE;
          })
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

  // Handle image requests
  if (url.pathname.startsWith('/IMAGES/')) {
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
        // Offline and not in cache - show offline page
        if (event.request.headers.get('accept').includes('text/html')) {
          return caches.match('/index.html');
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
