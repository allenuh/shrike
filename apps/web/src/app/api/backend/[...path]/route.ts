import { NextRequest } from "next/server";
import { demoData } from "@/lib/demo";
import { allowedPath, backendOrigin, forwardedCookies } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const jsonHeaders = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json",
  Vary: "Cookie",
};
const failure = (status: number) =>
  new Response(JSON.stringify({ error: { code: "request_unavailable" } }), {
    status,
    headers: jsonHeaders,
  });

async function handle(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (!allowedPath(path)) return failure(404);
  if (request.method === "POST" && path !== "auth/logout") return failure(405);
  if (request.method === "GET" && path === "auth/logout") return failure(405);
  const mode = process.env.SHRIKE_WEB_MODE || "demo";
  if (mode === "demo") {
    if (path === "auth/logout")
      return new Response(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
    if (path === "auth/github/start")
      return Response.redirect(new URL("/", request.url), 303);
    if (path === "auth/github/callback") return failure(403);
    try {
      const data = demoData(path, request.nextUrl.searchParams);
      return data === null
        ? failure(404)
        : Response.json(data, { headers: jsonHeaders });
    } catch {
      return failure(400);
    }
  }
  if (mode !== "live") return failure(503);
  try {
    const target = new URL(path, backendOrigin(process.env.SHRIKE_API_ORIGIN));
    target.search = request.nextUrl.search;
    const headers = new Headers({
      Accept: "application/json",
      Cookie: forwardedCookies(request.headers.get("cookie") || ""),
    });
    if (request.method === "POST") {
      const origin = request.headers.get("origin");
      if (
        !process.env.SHRIKE_WEB_ORIGIN ||
        origin !== process.env.SHRIKE_WEB_ORIGIN
      )
        return failure(403);
      headers.set("Origin", origin);
    }
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
    const outputHeaders = new Headers(jsonHeaders);
    for (const value of upstream.headers.getSetCookie())
      outputHeaders.append("Set-Cookie", value);
    const location = upstream.headers.get("location");
    if (location) {
      const redirect = new URL(location);
      if (
        !(
          path === "auth/github/start" &&
          redirect.origin === "https://github.com" &&
          redirect.pathname === "/login/oauth/authorize"
        ) &&
        redirect.origin !== process.env.SHRIKE_WEB_ORIGIN
      )
        return failure(502);
      outputHeaders.set("Location", location);
    }
    // Response bytes are never logged or included in error messages.
    const bytes = await upstream.arrayBuffer();
    if (bytes.byteLength > 2_097_152) return failure(502);
    return new Response(upstream.status === 204 ? null : bytes, {
      status: upstream.status,
      headers: outputHeaders,
    });
  } catch {
    return failure(503);
  }
}
export const GET = handle;
export const POST = handle;
