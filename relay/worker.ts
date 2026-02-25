/**
 * CrewBus Relay — Cloudflare Worker
 *
 * A thin relay that proxies MCP requests from remote clients (Claude Desktop,
 * claude.ai, etc.) to the user's Mac via a WebSocket tunnel.
 *
 * Routes:
 *   GET  /                                   → relay info
 *   GET  /.well-known/oauth-authorization-server → OAuth metadata (RFC 8414)
 *   POST /register                           → dynamic client registration (RFC 7591)
 *   GET  /authorize                          → OAuth authorize with PKCE
 *   POST /token                              → token exchange
 *   POST /mcp                                → authenticated MCP endpoint
 *   GET  /mcp                                → SSE for server-initiated messages
 *   GET  /tunnel                             → WebSocket upgrade for Mac tunnel
 *   GET  /auth/login                         → magic link login page
 *   POST /auth/login                         → send magic link email
 *   GET  /auth/verify                        → verify magic link token
 */

import { Hono } from "hono";
import { cors } from "hono/cors";

import {
  oauthMetadata,
  registerClient,
  getClient,
  generateAuthorizationCode,
  exchangeCodeForToken,
  validateToken,
  generateAccessToken,
} from "./oauth";
import {
  renderLoginPage,
  sendMagicLink,
  verifyMagicLink,
} from "./auth-handler";
import { handleMcpRequest } from "./mcp-handler";

// Re-export the Durable Object class so wrangler can find it
export { TunnelDurableObject } from "./tunnel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Env {
  TUNNEL: DurableObjectNamespace;
  OAUTH_KV: KVNamespace;
  TUNNEL_KV: KVNamespace;
  RELAY_ORIGIN: string;
  MAGIC_LINK_SECRET: string;
  RESEND_API_KEY: string;
}

// ---------------------------------------------------------------------------
// Hono App
// ---------------------------------------------------------------------------

const app = new Hono<{ Bindings: Env }>();

// ---------------------------------------------------------------------------
// CORS — allow Claude clients and localhost dev
// ---------------------------------------------------------------------------

app.use(
  "*",
  cors({
    origin: (origin) => {
      if (!origin) return "";
      const allowed = [
        "https://claude.ai",
        "https://www.claude.ai",
        "https://claude.com",
        "https://www.claude.com",
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8787",
        "http://127.0.0.1",
      ];
      // Allow any localhost port
      if (origin.startsWith("http://localhost:") || origin.startsWith("http://127.0.0.1:")) {
        return origin;
      }
      return allowed.includes(origin) ? origin : "";
    },
    allowMethods: ["GET", "POST", "OPTIONS"],
    allowHeaders: ["Authorization", "Content-Type"],
    exposeHeaders: ["Content-Type"],
    credentials: true,
    maxAge: 86400,
  }),
);

// ---------------------------------------------------------------------------
// Rate Limiting Middleware (60 req/min per user on /mcp)
// ---------------------------------------------------------------------------

async function checkRateLimit(userId: string, kv: KVNamespace): Promise<boolean> {
  const key = `ratelimit:${userId}:${Math.floor(Date.now() / 60000)}`;
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= 60) {
    return false;
  }

  await kv.put(key, String(count + 1), { expirationTtl: 120 });
  return true;
}

// ---------------------------------------------------------------------------
// GET / — Relay info
// ---------------------------------------------------------------------------

app.get("/", (c) => {
  return c.json({
    name: "CrewBus Relay",
    version: "1.0.0",
    description: "MCP relay for CrewBus — proxies requests to your Mac via WebSocket tunnel.",
    docs: "https://crew-bus.dev/docs/relay",
    endpoints: {
      mcp: "/mcp",
      tunnel: "/tunnel",
      oauth_metadata: "/.well-known/oauth-authorization-server",
    },
  });
});

// ---------------------------------------------------------------------------
// GET /.well-known/oauth-authorization-server — OAuth metadata (RFC 8414)
// ---------------------------------------------------------------------------

app.get("/.well-known/oauth-authorization-server", (c) => {
  return c.json(oauthMetadata(c.env.RELAY_ORIGIN));
});

// ---------------------------------------------------------------------------
// GET /.well-known/oauth-protected-resource — Protected Resource Metadata (RFC 9728)
// ---------------------------------------------------------------------------

app.get("/.well-known/oauth-protected-resource/*", (c) => {
  return c.json({
    resource: `${c.env.RELAY_ORIGIN}/mcp`,
    authorization_servers: [`${c.env.RELAY_ORIGIN}`],
    scopes_supported: ["mcp"],
    bearer_methods_supported: ["header"],
  });
});

app.get("/.well-known/oauth-protected-resource", (c) => {
  return c.json({
    resource: `${c.env.RELAY_ORIGIN}/mcp`,
    authorization_servers: [`${c.env.RELAY_ORIGIN}`],
    scopes_supported: ["mcp"],
    bearer_methods_supported: ["header"],
  });
});

// ---------------------------------------------------------------------------
// POST /register — Dynamic client registration (RFC 7591)
// ---------------------------------------------------------------------------

app.post("/register", async (c) => {
  const body = await c.req.json<{ client_name?: string; redirect_uris?: string[] }>();
  const registration = await registerClient(body, c.env.OAUTH_KV);

  return c.json(registration, 201);
});

// ---------------------------------------------------------------------------
// GET /authorize — OAuth authorize with PKCE
// ---------------------------------------------------------------------------

app.get("/authorize", async (c) => {
  const {
    response_type,
    client_id,
    redirect_uri,
    code_challenge,
    code_challenge_method,
    state,
    scope,
  } = c.req.query();

  // Validate required params
  if (response_type !== "code") {
    return c.json({ error: "unsupported_response_type" }, 400);
  }
  if (!client_id || !redirect_uri || !code_challenge) {
    return c.json({ error: "invalid_request", error_description: "Missing required parameters" }, 400);
  }
  if (code_challenge_method && code_challenge_method !== "S256") {
    return c.json({ error: "invalid_request", error_description: "Only S256 code_challenge_method is supported" }, 400);
  }

  // Validate client exists
  const client = await getClient(client_id, c.env.OAUTH_KV);
  if (!client) {
    return c.json({ error: "invalid_client" }, 400);
  }

  // Check for an existing session cookie
  const sessionToken = getCookie(c.req.raw, "crewbus_session");
  if (sessionToken) {
    const userId = await validateToken(sessionToken, c.env.OAUTH_KV);
    if (userId) {
      // User is already authenticated — issue authorization code directly
      const code = await generateAuthorizationCode(
        userId,
        client_id,
        code_challenge,
        redirect_uri,
        c.env.OAUTH_KV,
      );
      const redirectUrl = new URL(redirect_uri);
      redirectUrl.searchParams.set("code", code);
      if (state) redirectUrl.searchParams.set("state", state);
      return c.redirect(redirectUrl.toString());
    }
  }

  // No valid session — redirect to login with OAuth params in the URL
  const loginUrl = new URL(`${c.env.RELAY_ORIGIN}/auth/login`);
  loginUrl.searchParams.set("client_id", client_id);
  loginUrl.searchParams.set("redirect_uri", redirect_uri);
  loginUrl.searchParams.set("code_challenge", code_challenge);
  loginUrl.searchParams.set("code_challenge_method", code_challenge_method || "S256");
  if (state) loginUrl.searchParams.set("state", state);
  if (scope) loginUrl.searchParams.set("scope", scope);

  return c.redirect(loginUrl.toString());
});

// ---------------------------------------------------------------------------
// POST /token — Token exchange
// ---------------------------------------------------------------------------

app.post("/token", async (c) => {
  let params: Record<string, string>;

  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("application/x-www-form-urlencoded")) {
    const formData = await c.req.parseBody();
    params = Object.fromEntries(
      Object.entries(formData).map(([k, v]) => [k, String(v)]),
    );
  } else {
    params = await c.req.json<Record<string, string>>();
  }

  const { grant_type, code, code_verifier, client_id, redirect_uri } = params;

  if (grant_type !== "authorization_code") {
    return c.json({ error: "unsupported_grant_type" }, 400);
  }
  if (!code || !code_verifier || !client_id || !redirect_uri) {
    return c.json({ error: "invalid_request", error_description: "Missing required parameters" }, 400);
  }

  const result = await exchangeCodeForToken(
    code,
    code_verifier,
    client_id,
    redirect_uri,
    c.env.OAUTH_KV,
    c.env.MAGIC_LINK_SECRET,
  );

  if (!result) {
    return c.json({ error: "invalid_grant" }, 400);
  }

  return c.json(result);
});

// ---------------------------------------------------------------------------
// POST /mcp — Authenticated MCP endpoint (proxy to Mac)
// ---------------------------------------------------------------------------

app.post("/mcp", async (c) => {
  const userId = await extractAndValidateUser(c);
  if (!userId) {
    return c.json(
      {
        jsonrpc: "2.0",
        error: { code: -32001, message: "Unauthorized — invalid or missing access token" },
        id: null,
      },
      {
        status: 401,
        headers: {
          "WWW-Authenticate": `Bearer resource_metadata="${c.env.RELAY_ORIGIN}/.well-known/oauth-protected-resource"`,
        },
      },
    );
  }

  // Rate limit
  const allowed = await checkRateLimit(userId, c.env.OAUTH_KV);
  if (!allowed) {
    return c.json(
      {
        jsonrpc: "2.0",
        error: { code: -32002, message: "Rate limit exceeded — 60 requests per minute" },
        id: null,
      },
      429,
    );
  }

  // Get the user's tunnel DO
  const tunnelStub = await getTunnelStub(userId, c.env);
  return handleMcpRequest(c.req.raw, tunnelStub, userId);
});

// ---------------------------------------------------------------------------
// GET /mcp — SSE endpoint for server-initiated messages
// ---------------------------------------------------------------------------

app.get("/mcp", async (c) => {
  const userId = await extractAndValidateUser(c);
  if (!userId) {
    return c.text("Unauthorized", 401);
  }

  // SSE stream — the Mac can push notifications through the tunnel
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  // Send initial connection event
  await writer.write(encoder.encode("event: connected\ndata: {}\n\n"));

  // Keep the connection alive with periodic comments
  const keepalive = setInterval(async () => {
    try {
      await writer.write(encoder.encode(": keepalive\n\n"));
    } catch {
      clearInterval(keepalive);
    }
  }, 15000);

  // Clean up when the client disconnects
  c.req.raw.signal.addEventListener("abort", () => {
    clearInterval(keepalive);
    writer.close().catch(() => {});
  });

  return new Response(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
});

// ---------------------------------------------------------------------------
// GET /tunnel — WebSocket upgrade for Mac tunnel clients
// ---------------------------------------------------------------------------

app.get("/tunnel", async (c) => {
  // Authenticate the Mac client
  const authHeader = c.req.header("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return c.text("Unauthorized — Bearer token required", 401);
  }

  const token = authHeader.slice(7);
  const userId = await validateToken(token, c.env.OAUTH_KV);
  if (!userId) {
    return c.text("Unauthorized — invalid token", 401);
  }

  if (c.req.header("Upgrade") !== "websocket") {
    return c.text("Expected WebSocket upgrade", 426);
  }

  // Store the user-to-tunnel mapping
  const tunnelId = c.env.TUNNEL.idFromName(userId);
  await c.env.TUNNEL_KV.put(`tunnel:${userId}`, tunnelId.toString());

  // Forward the WebSocket upgrade to the Durable Object
  const tunnelStub = c.env.TUNNEL.get(tunnelId);
  return tunnelStub.fetch(new Request("http://tunnel/websocket", {
    headers: c.req.raw.headers,
  }));
});

// ---------------------------------------------------------------------------
// GET /auth/login — Magic link login page
// ---------------------------------------------------------------------------

app.get("/auth/login", (c) => {
  const oauthParams: Record<string, string> = {};
  for (const key of ["client_id", "redirect_uri", "code_challenge", "code_challenge_method", "state", "scope"]) {
    const val = c.req.query(key);
    if (val) oauthParams[key] = val;
  }
  return c.html(renderLoginPage(undefined, undefined, oauthParams));
});

// ---------------------------------------------------------------------------
// POST /auth/login — Send magic link email
// ---------------------------------------------------------------------------

app.post("/auth/login", async (c) => {
  const formData = await c.req.parseBody();
  const email = String(formData.email ?? "").trim().toLowerCase();

  if (!email || !email.includes("@")) {
    return c.html(renderLoginPage("Please enter a valid email address."), 400);
  }

  // Preserve OAuth flow params
  const url = new URL(c.req.url);
  const clientId = url.searchParams.get("client_id") ?? formData.client_id?.toString() ?? "";
  const redirectUri = url.searchParams.get("redirect_uri") ?? formData.redirect_uri?.toString() ?? "";
  const codeChallenge = url.searchParams.get("code_challenge") ?? formData.code_challenge?.toString() ?? "";
  const codeChallengeMethod = url.searchParams.get("code_challenge_method") ?? formData.code_challenge_method?.toString() ?? "S256";
  const state = url.searchParams.get("state") ?? formData.state?.toString() ?? "";

  // Store OAuth params in KV so we can continue the flow after email verification
  if (clientId && redirectUri && codeChallenge) {
    const flowId = crypto.randomUUID();
    await c.env.OAUTH_KV.put(
      `oauth_flow:${email}`,
      JSON.stringify({ clientId, redirectUri, codeChallenge, codeChallengeMethod, state, flowId }),
      { expirationTtl: 900 }, // 15 minutes
    );
  }

  try {
    await sendMagicLink(email, c.env);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to send email";
    return c.html(renderLoginPage(message), 500);
  }

  return c.html(
    renderLoginPage(
      undefined,
      "Check your email for a magic link to sign in.",
    ),
  );
});

// ---------------------------------------------------------------------------
// GET /auth/verify — Show confirmation page (prevents link scanners from consuming the token)
// ---------------------------------------------------------------------------

app.get("/auth/verify", (c) => {
  const token = c.req.query("token");
  if (!token) {
    return c.html(renderLoginPage("Missing verification token."), 400);
  }

  // Render a confirmation page with a button that POSTs the token
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Confirm Sign In — CrewBus</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f0f23; color: #e0e0e0;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; padding: 1rem;
    }
    .card {
      background: #1a1a2e; border-radius: 16px; padding: 2.5rem;
      max-width: 420px; width: 100%;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4); text-align: center;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #fff; }
    .subtitle { color: #888; margin-bottom: 1.5rem; font-size: 0.95rem; }
    button {
      width: 100%; padding: 0.75rem; background: #6c63ff; color: #fff;
      border: none; border-radius: 8px; font-size: 1rem; cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: #5a52d5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Confirm Sign In</h1>
    <p class="subtitle">Click below to complete sign in to CrewBus.</p>
    <form method="POST" action="/auth/verify">
      <input type="hidden" name="token" value="${token.replace(/"/g, '&quot;')}">
      <button type="submit">Confirm Sign In</button>
    </form>
  </div>
</body>
</html>`);
});

// ---------------------------------------------------------------------------
// POST /auth/verify — Actually verify and consume the magic link token
// ---------------------------------------------------------------------------

app.post("/auth/verify", async (c) => {
  const formData = await c.req.parseBody();
  const token = String(formData.token ?? "");
  if (!token) {
    return c.html(renderLoginPage("Missing verification token."), 400);
  }

  const result = await verifyMagicLink(token, c.env);
  if (!result) {
    return c.html(renderLoginPage("Invalid or expired link. Please try again."), 400);
  }

  // Create a session token (reuse our access token generation)
  const sessionToken = await generateAccessToken(result.userId, c.env.MAGIC_LINK_SECRET);

  // Store the session token
  await c.env.OAUTH_KV.put(
    `token:${sessionToken}`,
    JSON.stringify({
      userId: result.userId,
      clientId: "session",
      expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000, // 30 days
    }),
    { expirationTtl: 30 * 24 * 60 * 60 },
  );

  // Check if there's a pending OAuth flow for this user
  const flowRaw = await c.env.OAUTH_KV.get(`oauth_flow:${result.email}`);
  if (flowRaw) {
    const flow = JSON.parse(flowRaw) as {
      clientId: string;
      redirectUri: string;
      codeChallenge: string;
      state: string;
    };
    await c.env.OAUTH_KV.delete(`oauth_flow:${result.email}`);

    // Generate authorization code and redirect back to the OAuth client
    const code = await generateAuthorizationCode(
      result.userId,
      flow.clientId,
      flow.codeChallenge,
      flow.redirectUri,
      c.env.OAUTH_KV,
    );

    const redirectUrl = new URL(flow.redirectUri);
    redirectUrl.searchParams.set("code", code);
    if (flow.state) redirectUrl.searchParams.set("state", flow.state);

    // Set session cookie and redirect
    return new Response(null, {
      status: 302,
      headers: {
        Location: redirectUrl.toString(),
        "Set-Cookie": `crewbus_session=${sessionToken}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${30 * 24 * 60 * 60}`,
      },
    });
  }

  // No OAuth flow — just set session and show success
  return new Response(successHtml(result.email), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Set-Cookie": `crewbus_session=${sessionToken}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${30 * 24 * 60 * 60}`,
    },
  });
});

// ---------------------------------------------------------------------------
// Helper: Extract and validate user from Bearer token
// ---------------------------------------------------------------------------

async function extractAndValidateUser(c: { req: { header: (name: string) => string | undefined }; env: Env }): Promise<string | null> {
  const authHeader = c.req.header("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return null;
  }
  const token = authHeader.slice(7);
  return validateToken(token, c.env.OAUTH_KV);
}

// ---------------------------------------------------------------------------
// Helper: Get a user's tunnel Durable Object stub
// ---------------------------------------------------------------------------

async function getTunnelStub(userId: string, env: Env): Promise<DurableObjectStub> {
  const tunnelId = env.TUNNEL.idFromName(userId);
  return env.TUNNEL.get(tunnelId);
}

// ---------------------------------------------------------------------------
// Helper: Parse cookie from request
// ---------------------------------------------------------------------------

function getCookie(request: Request, name: string): string | null {
  const cookieHeader = request.headers.get("Cookie");
  if (!cookieHeader) return null;

  const cookies = cookieHeader.split(";").map((c) => c.trim());
  for (const cookie of cookies) {
    const [key, ...rest] = cookie.split("=");
    if (key.trim() === name) {
      return rest.join("=").trim();
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Helper: Success page HTML after magic link verification
// ---------------------------------------------------------------------------

function successHtml(email: string): string {
  const safeEmail = email
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Signed in to CrewBus</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f0f23;
      color: #e0e0e0;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background: #1a1a2e;
      border-radius: 16px;
      padding: 2.5rem;
      max-width: 420px;
      width: 100%;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
      text-align: center;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.75rem; color: #6bff8e; }
    p { color: #aaa; line-height: 1.6; }
    .email { color: #fff; font-weight: 600; }
  </style>
</head>
<body>
  <div class="card">
    <h1>You're signed in!</h1>
    <p>Authenticated as <span class="email">${safeEmail}</span>.</p>
    <p style="margin-top: 1rem;">You can close this tab and return to your app.</p>
  </div>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default app;
