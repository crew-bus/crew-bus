/**
 * Magic link authentication for the CrewBus relay.
 *
 * Users authenticate by entering their email. A signed magic link is
 * sent via the Resend API. Clicking the link verifies the token and
 * creates a session (stored in OAUTH_KV).
 */

interface Env {
  OAUTH_KV: KVNamespace;
  RELAY_ORIGIN: string;
  MAGIC_LINK_SECRET: string;
  RESEND_API_KEY: string;
}

interface UserRecord {
  userId: string;
  email: string;
  createdAt: number;
}

const MAGIC_LINK_EXPIRY_MS = 15 * 60 * 1000; // 15 minutes

// ---------------------------------------------------------------------------
// Login Page
// ---------------------------------------------------------------------------

export function renderLoginPage(error?: string, success?: string): string {
  const errorHtml = error
    ? `<div class="alert error">${escapeHtml(error)}</div>`
    : "";
  const successHtml = success
    ? `<div class="alert success">${escapeHtml(success)}</div>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in to CrewBus</title>
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
    }
    h1 {
      font-size: 1.5rem;
      margin-bottom: 0.5rem;
      color: #fff;
    }
    .subtitle {
      color: #888;
      margin-bottom: 1.5rem;
      font-size: 0.95rem;
    }
    label {
      display: block;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      color: #aaa;
    }
    input[type="email"] {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid #333;
      border-radius: 8px;
      background: #0f0f23;
      color: #fff;
      font-size: 1rem;
      margin-bottom: 1rem;
      outline: none;
      transition: border-color 0.2s;
    }
    input[type="email"]:focus {
      border-color: #6c63ff;
    }
    button {
      width: 100%;
      padding: 0.75rem;
      background: #6c63ff;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: #5a52d5; }
    .alert {
      padding: 0.75rem 1rem;
      border-radius: 8px;
      margin-bottom: 1rem;
      font-size: 0.9rem;
    }
    .alert.error { background: #3d1f1f; color: #ff6b6b; border: 1px solid #5a2d2d; }
    .alert.success { background: #1f3d2a; color: #6bff8e; border: 1px solid #2d5a3d; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Sign in to CrewBus</h1>
    <p class="subtitle">We'll send you a magic link to verify your email.</p>
    ${errorHtml}
    ${successHtml}
    <form method="POST" action="/auth/login">
      <label for="email">Email address</label>
      <input type="email" id="email" name="email" required placeholder="you@example.com" autocomplete="email">
      <button type="submit">Send magic link</button>
    </form>
  </div>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Send Magic Link
// ---------------------------------------------------------------------------

export async function sendMagicLink(email: string, env: Env): Promise<void> {
  const token = await generateMagicToken(email, env.MAGIC_LINK_SECRET);
  const verifyUrl = `${env.RELAY_ORIGIN}/auth/verify?token=${encodeURIComponent(token)}`;

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "CrewBus <noreply@crew-bus.dev>",
      to: [email],
      subject: "Sign in to CrewBus",
      html: `
        <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 2rem;">
          <h2 style="color: #333;">Sign in to CrewBus</h2>
          <p style="color: #555; line-height: 1.6;">
            Click the button below to sign in. This link expires in 15 minutes.
          </p>
          <a href="${verifyUrl}"
             style="display: inline-block; background: #6c63ff; color: #fff; padding: 12px 24px;
                    border-radius: 8px; text-decoration: none; margin: 1rem 0;">
            Sign in to CrewBus
          </a>
          <p style="color: #999; font-size: 0.85rem; margin-top: 1.5rem;">
            If you didn't request this, you can safely ignore this email.
          </p>
        </div>
      `,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to send email: ${res.status} ${text}`);
  }
}

// ---------------------------------------------------------------------------
// Verify Magic Link
// ---------------------------------------------------------------------------

export async function verifyMagicLink(
  token: string,
  env: Env,
): Promise<{ email: string; userId: string } | null> {
  const parsed = await parseMagicToken(token, env.MAGIC_LINK_SECRET);
  if (!parsed) return null;

  // Check token hasn't been used (one-time use)
  const usedKey = `magic_used:${parsed.nonce}`;
  const alreadyUsed = await env.OAUTH_KV.get(usedKey);
  if (alreadyUsed) return null;

  // Mark as used (keep for 1 hour to prevent replay)
  await env.OAUTH_KV.put(usedKey, "1", { expirationTtl: 3600 });

  const user = await getOrCreateUser(parsed.email, env);
  return { email: parsed.email, userId: user.userId };
}

// ---------------------------------------------------------------------------
// User Management
// ---------------------------------------------------------------------------

export async function getOrCreateUser(
  email: string,
  env: Env,
): Promise<UserRecord> {
  const key = `user:${email.toLowerCase()}`;
  const existing = await env.OAUTH_KV.get(key);

  if (existing) {
    return JSON.parse(existing);
  }

  const user: UserRecord = {
    userId: crypto.randomUUID(),
    email: email.toLowerCase(),
    createdAt: Date.now(),
  };

  await env.OAUTH_KV.put(key, JSON.stringify(user));
  return user;
}

// ---------------------------------------------------------------------------
// Magic Token Helpers (HMAC-SHA256 signed)
// ---------------------------------------------------------------------------

interface MagicTokenPayload {
  email: string;
  timestamp: number;
  nonce: string;
}

async function generateMagicToken(email: string, secret: string): Promise<string> {
  const payload: MagicTokenPayload = {
    email: email.toLowerCase(),
    timestamp: Date.now(),
    nonce: crypto.randomUUID(),
  };

  const payloadStr = JSON.stringify(payload);
  const payloadB64 = base64UrlEncode(new TextEncoder().encode(payloadStr));

  const key = await importHmacKey(secret);
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadB64),
  );
  const sigB64 = base64UrlEncode(new Uint8Array(signature));

  return `${payloadB64}.${sigB64}`;
}

async function parseMagicToken(
  token: string,
  secret: string,
): Promise<MagicTokenPayload | null> {
  const parts = token.split(".");
  if (parts.length !== 2) return null;

  const [payloadB64, sigB64] = parts;

  // Verify signature
  const key = await importHmacKey(secret);
  const sigBytes = base64UrlDecode(sigB64);
  const valid = await crypto.subtle.verify(
    "HMAC",
    key,
    sigBytes,
    new TextEncoder().encode(payloadB64),
  );

  if (!valid) return null;

  // Decode payload
  const payloadBytes = base64UrlDecode(payloadB64);
  const payloadStr = new TextDecoder().decode(payloadBytes);
  let payload: MagicTokenPayload;
  try {
    payload = JSON.parse(payloadStr);
  } catch {
    return null;
  }

  // Check expiry
  if (Date.now() - payload.timestamp > MAGIC_LINK_EXPIRY_MS) {
    return null;
  }

  return payload;
}

// ---------------------------------------------------------------------------
// Crypto / Encoding Helpers
// ---------------------------------------------------------------------------

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function base64UrlEncode(bytes: Uint8Array): string {
  const binStr = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
  return btoa(binStr).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlDecode(str: string): Uint8Array {
  const padded = str.replace(/-/g, "+").replace(/_/g, "/");
  const binStr = atob(padded);
  return Uint8Array.from(binStr, (c) => c.charCodeAt(0));
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
