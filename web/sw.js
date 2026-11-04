// Online-only remote: never replay/cache control commands or private library data.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.method==='GET'&&!new URL(event.request.url).pathname.startsWith('/api/'))event.respondWith(fetch(event.request));});
