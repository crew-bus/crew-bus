/**
 * OAuth 2.1 helpers for the CrewBus relay.
 *
 * Implements:
 *  - Dynamic client registration (RFC 7591)
 *  - Authorization with PKCE (RFC 7636)
 *  - Token exchange
 *  - Token validation
 *  - OAuth server metadata (RFC 8414)
 */

const CODE_EXPIRY_SECONDS = 10 * 60; // 10 minutes
const TOKEN_EXPIRY_SECONDS = 30 * 24 * 60 * 60; // 30 days

// ---------------------------------------------------------------------------
// OAuth Server Metadata (RFC 8414)
// ---------------------------------------------------------------------------

export function oauthMetadata(origin: string) {
  return {
    issuer: origin,
    authorization_endpoint: `${origin}/authorize`,
    token_endpoint: `${origin}/token`,
    registration_endpoint: `${origin}/register`,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none"],
    scopes_supported: ["mcp"],
  };
}

// ---------------------------------------------------------------------------
// Dynamic Client Registration (RFC 7591)
// ---------------------------------------------------------------------------

interface ClientRegistration {
  client_id: string;
  client_name?: string;
  redirect_uris: string[];
  created_at: number;
}

export async function registerClient(
  body: { client_name?: string; redirect_uris?: string[] },
  kv: KVNamespace,
): Promise<ClientRegistration> {
  const clientId = crypto.randomUUID();
  const registration: ClientRegistration = {
    client_id: clientId,
    client_name: body.client_name,
    redirect_uris: body.redirect_uris ?? [],
    created_at: Date.now(),
  };

  await kv.put(`client:${clientId}`, JSON.stringify(registration));
  return registration;
}

export async function getClient(
  clientId: string,
  kv: KVNamespace,
): Promise<ClientRegistration | null> {
  const raw = await kv.get(`client:${clientId}`);
  if (!raw) return null;
  return JSON.parse(raw);
}

// ---------------------------------------------------------------------------
// Authorization Code
// ---------------------------------------------------------------------------

interface AuthCodeRecord {
  userId: string;
  clientId: string;
  codeChallenge: string;
  codeChallengeMethod: string;
  redirectUri: string;
  expiresAt: number;
}

export async function generateAuthorizationCode(
  userId: string,
  clientId: string,
  codeChallenge: string,
  redirectUri: string,
  kv: KVNamespace,
): Promise<string> {
  const code = crypto.randomUUID();
  const record: AuthCodeRecord = {
    userId,
    clientId,
    codeChallenge,
    codeChallengeMethod: "S256",
    redirectUri,
    expiresAt: Date.now() + CODE_EXPIRY_SECONDS * 1000,
  };

  await kv.put(`code:${code}`, JSON.stringify(record), {
    expirationTtl: CODE_EXPIRY_SECONDS,
  });

  return code;
}

// ---------------------------------------------------------------------------
// Token Exchange
// ---------------------------------------------------------------------------

interface TokenRecord {
  userId: string;
  clientId: string;
  expiresAt: number;
}

export async function exchangeCodeForToken(
  code: string,
  codeVerifier: string,
  clientId: string,
  redirectUri: string,
  kv: KVNamespace,
  secret: string,
): Promise<{ access_token: string; token_type: string; expires_in: number } | null> {
  const raw = await kv.get(`code:${code}`);
  if (!raw) return null;

  const record: AuthCodeRecord = JSON.parse(raw);

  // Validate expiry
  if (Date.now() > record.expiresAt) {
    await kv.delete(`code:${code}`);
    return null;
  }

  // Validate client and redirect
  if (record.clientId !== clientId || record.redirectUri !== redirectUri) {
    return null;
  }

  // Validate PKCE S256
  const challengeFromVerifier = await computeS256Challenge(codeVerifier);
  if (challengeFromVerifier !== record.codeChallenge) {
    return null;
  }

  // Consume the code (one-time use)
  await kv.delete(`code:${code}`);

  // Generate access token
  const accessToken = await generateAccessToken(record.userId, secret);
  const expiresAt = Date.now() + TOKEN_EXPIRY_SECONDS * 1000;

  const tokenRecord: TokenRecord = {
    userId: record.userId,
    clientId: record.clientId,
    expiresAt,
  };

  await kv.put(`token:${accessToken}`, JSON.stringify(tokenRecord), {
    expirationTtl: TOKEN_EXPIRY_SECONDS,
  });

  return {
    access_token: accessToken,
    token_type: "Bearer",
    expires_in: TOKEN_EXPIRY_SECONDS,
  };
}

// ---------------------------------------------------------------------------
// Token Validation
// ---------------------------------------------------------------------------

export async function validateToken(
  token: string,
  kv: KVNamespace,
): Promise<string | null> {
  const raw = await kv.get(`token:${token}`);
  if (!raw) return null;

  const record: TokenRecord = JSON.parse(raw);
  if (Date.now() > record.expiresAt) {
    await kv.delete(`token:${token}`);
    return null;
  }

  return record.userId;
}

// ---------------------------------------------------------------------------
// Access Token Generation (HMAC-signed)
// ---------------------------------------------------------------------------

export async function generateAccessToken(
  userId: string,
  secret: string,
): Promise<string> {
  const payload = {
    sub: userId,
    iat: Math.floor(Date.now() / 1000),
    jti: crypto.randomUUID(),
  };

  const payloadStr = JSON.stringify(payload);
  const payloadB64 = base64UrlEncode(new TextEncoder().encode(payloadStr));

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadB64),
  );

  const sigB64 = base64UrlEncode(new Uint8Array(signature));
  return `${payloadB64}.${sigB64}`;
}

// ---------------------------------------------------------------------------
// PKCE S256
// ---------------------------------------------------------------------------

async function computeS256Challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return base64UrlEncode(new Uint8Array(digest));
}

// ---------------------------------------------------------------------------
// Base64url helpers
// ---------------------------------------------------------------------------

function base64UrlEncode(bytes: Uint8Array): string {
  const binStr = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
  return btoa(binStr).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
