// Selbstzerstörungs-Service-Worker (2026-07-12).
//
// Der alte Service Worker (Cache "ailiza-v1", offline-first fuer "/" und
// "/index.html") wurde in der aktuellen App nirgends mehr registriert,
// blieb aber bei jedem Nutzer, der die App frueher schon einmal geoeffnet
// hatte, installiert und aktiv — Service Worker ueberleben Deploys, bis sie
// explizit entfernt werden. Ergebnis: bei jedem Netzwerk-Ausfall (z.B.
// Render-Free-Tier-Aufwachzeit von bis zu 50s) wurde eine WOCHEN ALTE,
// gecachte Version der Seite angezeigt (u.a. mit dem laengst entfernten
// Login-Overlay und der falschen "EU AI Act Art. 52"-Referenz) — fuer eine
// DSGVO-/Compliance-kritische App inakzeptabel.
//
// Dieser Service Worker ersetzt den alten (gleiche Registrierungs-URL),
// loescht ALLE Caches und meldet sich selbst ab. Danach laeuft die App ohne
// Service Worker — jede Anfrage geht direkt ans Netzwerk.
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll())
      .then((clients) => clients.forEach((client) => client.navigate(client.url)))
  );
});
