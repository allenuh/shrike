/** Fixed-origin server boundary; never imported by a client component. */
export function allowedPath(path: string): boolean {
  return /^(?:auth\/(?:session|logout|github\/(?:start|callback))|v1\/dashboard\/(?:repositories|reviews|metrics|operations|settings)|v1\/dashboard\/reviews\/[a-f0-9-]{36})$/.test(
    path,
  );
}
export function backendOrigin(raw: string | undefined): URL {
  const url = new URL(raw || "http://127.0.0.1:8000");
  if (
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    (url.protocol !== "https:" &&
      !(
        url.protocol === "http:" &&
        ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
      ))
  )
    throw new Error("invalid_backend_origin");
  return url;
}
export function forwardedCookies(header: string): string {
  const allowed = new Set([
    "shrike_session",
    "__Host-shrike_session",
    "shrike_oauth_state",
    "__Host-shrike_oauth_state",
  ]);
  return header
    .split(";")
    .map((v) => v.trim())
    .filter((v) => allowed.has(v.split("=", 1)[0]))
    .join("; ");
}
