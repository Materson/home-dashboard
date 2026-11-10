/// <reference lib="webworker" />
/* eslint-disable @typescript-eslint/no-explicit-any */
import { precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

precacheAndRoute((self as any).__WB_MANIFEST ?? []);

type PushAction = { action: string; title: string; url: string };
type PushPayload = {
  title?: string;
  body?: string;
  url?: string;
  tag?: string;
  actions?: PushAction[];
};

self.addEventListener("push", (event: PushEvent) => {
  const data = (event.data?.json() ?? {}) as PushPayload;
  const actions = data.actions ?? [];
  event.waitUntil(
    self.registration.showNotification(data.title ?? "Home Dashboard", {
      body: data.body ?? "",
      tag: data.tag,
      badge: "/icon-192.png",
      icon: "/icon-192.png",
      // Buttons like "Wzięte" / "Pominięte" (browsers show up to 2).
      actions: actions.map(({ action, title }) => ({ action, title })),
      data: { url: data.url ?? "/", actions },
    } as NotificationOptions),
  );
});

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  event.notification.close();
  const { url = "/", actions = [] } = (event.notification.data ?? {}) as {
    url?: string;
    actions?: PushAction[];
  };

  const action = actions.find((a) => a.action === event.action);
  if (action) {
    // Action urls carry a signed token, so no session cookie or CSRF header
    // is needed here — the service worker has neither.
    event.waitUntil(fetch(action.url, { method: "POST" }).then(() => undefined));
    return;
  }

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const client = clients.find((c) => c.url.includes(url));
      if (client) return client.focus();
      return self.clients.openWindow(url);
    }),
  );
});
