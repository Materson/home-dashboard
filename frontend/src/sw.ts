/// <reference lib="webworker" />
/* eslint-disable @typescript-eslint/no-explicit-any */
import { precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

precacheAndRoute((self as any).__WB_MANIFEST ?? []);

self.addEventListener("push", (event: PushEvent) => {
  const data = event.data?.json() ?? {};
  const title = data.title ?? "Home Dashboard";
  const body = data.body ?? "";
  const url = data.url ?? "/";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      data: { url },
      badge: "/icon-192.png",
      icon: "/icon-192.png",
    }),
  );
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string })?.url ?? "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const client = clients.find((c) => c.url.includes(url));
      if (client) return client.focus();
      return self.clients.openWindow(url);
    }),
  );
});
