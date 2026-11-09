import createClient from "openapi-fetch";
import type { paths } from "./schema";

// CSRF is required by Django; allauth headless + Ninja both expect the
// X-CSRFToken header to echo the `csrftoken` cookie value.
function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : "";
}

export const api = createClient<paths>({
  baseUrl: "/api",
  credentials: "include",
  fetch: async (input, init) => {
    const csrftoken = getCookie("csrftoken");
    const method = (init?.method ?? "GET").toUpperCase();
    const unsafe = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
    const headers = new Headers(init?.headers);
    if (unsafe && csrftoken) headers.set("X-CSRFToken", csrftoken);
    return fetch(input as Request, { ...init, headers });
  },
});
