import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

// CSRF is required by Django; allauth headless + Ninja both expect the
// X-CSRFToken header to echo the `csrftoken` cookie value.
function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : "";
}

const csrf: Middleware = {
  onRequest({ request }) {
    const unsafe = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(request.method.toUpperCase());
    const token = getCookie("csrftoken");
    if (unsafe && token) request.headers.set("X-CSRFToken", token);
    return request;
  },
};

// The generated `paths` already start with `/api/…`, so no baseUrl prefix.
export const api = createClient<paths>({ baseUrl: "", credentials: "include" });
api.use(csrf);
