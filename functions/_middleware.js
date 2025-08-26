export const onRequest = async ({ next }) => {
  const res = await next();
  const h = new Headers(res.headers);

  // Strip any permissive CORS added upstream
  h.delete("access-control-allow-origin");
  h.delete("access-control-allow-methods");
  h.delete("access-control-allow-headers");

  // Optional: add a debug header so we know this ran
  h.set("x-debug-functions", "on");

  // Re-assert your security headers (kept in _headers too; dupes are fine)
  h.set("X-Content-Type-Options", "nosniff");
  h.set("X-Frame-Options", "SAMEORIGIN");
  h.set("Referrer-Policy", "strict-origin-when-cross-origin");
  h.set(
    "Permissions-Policy",
    "geolocation=(), microphone=(), camera=(), payment=(), usb=(), accelerometer=(), gyroscope=(), magnetometer=()"
  );
  h.set(
    "Content-Security-Policy",
    "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
  );

  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
};

