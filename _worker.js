export default {
  async fetch(request, env, ctx) {
    const res = await env.ASSETS.fetch(request);
    const h = new Headers(res.headers);

    // Remove permissive CORS if present
    h.delete("access-control-allow-origin");
    h.delete("access-control-allow-methods");
    h.delete("access-control-allow-headers");

    // Keep your security headers
    h.set("X-Content-Type-Options", "nosniff");
    h.set("X-Frame-Options", "SAMEORIGIN");
    h.set("Referrer-Policy", "strict-origin-when-cross-origin");
    h.set("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=(), usb=(), accelerometer=(), gyroscope=(), magnetometer=()");
    h.set("Content-Security-Policy",
      "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'");

    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
  }
}

