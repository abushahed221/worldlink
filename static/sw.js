/* ==================== إعدادات ==================== */
const CACHE_VERSION = "worldlink-v1.0.1";"; // ⚠️ غيّرها مع كل إصدار جديد
const CACHE_NAME = "worldlink-cache-" + CACHE_VERSION;
const OFFLINE_URL = "/offline/";

const PRECACHE_URLS = [
    "/offline/",
    "/static/icon.svg",
    "/static/manifest.json",
    "/static/version.json",
];

/* ==================== التثبيت ==================== */
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(PRECACHE_URLS).catch(() => {});
        })
    );
    // لا تُنشّط فورًا — انتظر إشارة من الصفحة
    // self.skipWaiting();
});

/* ==================== التنشيط ==================== */
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((k) => k !== CACHE_NAME)
                    .map((k) => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

/* ==================== التوجيه ==================== */
self.addEventListener("fetch", (event) => {
    const req = event.request;
    if (req.method !== "GET") return;

    const url = new URL(req.url);

    // تجاهل بعض المسارات
    if (url.pathname.startsWith("/ws/")) return;
    if (url.pathname.startsWith("/admin/")) return;
    if (url.pathname.startsWith("/media/")) return;
    if (url.pathname.includes("/chat/")) return;

    // الصفحات: محاولة الشبكة أولًا، وإذا فشلت ارجع للصفحة المخزنة
    if (req.mode === "navigate") {
        event.respondWith(
            fetch(req)
                .then((res) => {
                    // خزّن نسخة من الصفحة (اختياري)
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
                    return res;
                })
                .catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    // الملفات الثابتة: من الكاش أولًا
    if (url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(req).then((cached) => {
                if (cached) return cached;
                return fetch(req).then((res) => {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
                    return res;
                });
            })
        );
    }
});

/* ==================== الرسائل من الصفحة ==================== */
self.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.type === "SKIP_WAITING") {
        self.skipWaiting();
    }
});