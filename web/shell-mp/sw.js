// Minimal service worker: makes the page installable as an app (web/MOBILE.md, P4). It does not cache
// anything; the pk3 already lives in Cache Storage and the engine files use no-cache revalidation.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
