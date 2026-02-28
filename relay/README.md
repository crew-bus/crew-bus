# CrewBus Relay

A Cloudflare Worker that proxies MCP requests from remote clients (Claude Desktop, claude.ai) to a user's Mac running CrewBus via a WebSocket tunnel.

## Architecture

```
Claude Desktop / claude.ai
        |
        | HTTPS (JSON-RPC over POST /mcp)
        v
  CrewBus Relay (Cloudflare Worker)
        |
        | WebSocket tunnel (wss://relay.crew-bus.dev/tunnel)
        v
  CrewBus Mac App (local)
```

The relay is intentionally thin — it authenticates requests, looks up the user's tunnel, and forwards MCP payloads. No agent logic runs on the relay.

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Create KV namespaces

```bash
wrangler kv namespace create OAUTH_KV
wrangler kv namespace create TUNNEL_KV
```

Update the `id` values in `wrangler.toml` with the returned namespace IDs.

### 3. Set secrets

```bash
wrangler secret put MAGIC_LINK_SECRET   # random 64-char string
wrangler secret put RESEND_API_KEY      # from resend.com dashboard
```

### 4. Deploy

```bash
npm run deploy
```

### 5. Configure DNS

Point `relay.crew-bus.dev` to your Cloudflare Worker via a CNAME or Workers route.

## Development

```bash
npm run dev     # starts wrangler dev server on localhost:8787
npm test        # runs vitest
```

## Wire Protocol

The Mac app connects via WebSocket to `wss://relay.crew-bus.dev/tunnel` with a Bearer token.

**Relay to Mac (request):**
```json
{"type": "mcp_request", "id": "<uuid>", "body": <MCP JSON-RPC request>}
```

**Mac to Relay (response):**
```json
{"type": "mcp_response", "id": "<uuid>", "body": <MCP JSON-RPC response>}
```

**Keepalive:** `{"type": "ping"}` / `{"type": "pong"}`

## OAuth Flow

1. Client calls `POST /register` to get a `client_id`
2. Client redirects user to `GET /authorize` with PKCE challenge
3. User authenticates via magic link email
4. Relay redirects back with authorization code
5. Client exchanges code for token via `POST /token`
6. Client uses token as `Authorization: Bearer <token>` on `POST /mcp`

## Configuration

| Variable | Description |
|---|---|
| `RELAY_ORIGIN` | Public URL of the relay (e.g., `https://relay.crew-bus.dev`) |
| `MAGIC_LINK_SECRET` | Secret for signing magic link tokens and access tokens |
| `RESEND_API_KEY` | API key for sending emails via Resend |
