self.addEventListener('install', function(event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function(event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function(event) {
  // simple network-first strategy
  event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));
});
