self.addEventListener("install", event => {
  event.waitUntil(caches.open("sales-mobile-v1").then(cache => cache.addAll(["/mobile/", "/mobile/static/styles.css", "/mobile/static/app.js"])));
});

self.addEventListener("fetch", event => {
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
