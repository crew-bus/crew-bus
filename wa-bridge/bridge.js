/**
 * crew-bus WhatsApp Bridge — Crew Boss Only (Baileys edition)
 *
 * Node.js sidecar that connects WhatsApp to the crew-bus Python system.
 * Uses Baileys (WebSocket-based) instead of whatsapp-web.js (Puppeteer).
 * No browser required — lighter, faster, no "Execution context destroyed" crashes.
 *
 * Inbound:  WhatsApp message from you → POST to crew-bus API → lands as Human→Crew-Boss message
 * Outbound: Polls crew-bus for new Crew-Boss→Human messages → forwards to your WhatsApp
 *
 * Usage:
 *   node bridge.js                          # default port 3001
 *   WA_PORT=3002 node bridge.js             # custom port
 *
 * First run: scan the QR code with your phone's WhatsApp (Linked Devices).
 * Session is persisted in ./wa-session/ so you only scan once.
 *
 * API:
 *   POST /send   { "text": "Hello" }        → sends to your WhatsApp
 *   GET  /status                             → connection status
 *   GET  /qr                                 → raw QR string
 *   GET  /qr/svg                             → QR as inline SVG
 *   POST /stop                               → graceful shutdown
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("baileys");
const http = require("http");
const path = require("path");

// ── Config ──────────────────────────────────────────────────────────

const PORT = parseInt(process.env.WA_PORT || "3001", 10);
const BUS_URL = process.env.BUS_URL || "http://localhost:8080";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL || "5000", 10);
const AUTH_DIR = path.join(__dirname, "wa-session", "baileys-auth");

// ── State ───────────────────────────────────────────────────────────

let sock = null;
let MY_WHATSAPP_ID = null;
let humanAgentId = null;
let crewBossAgentId = null;
let lastSeenMessageId = 0;
let latestQR = null;
let qrTimestamp = 0;
let clientReady = false;
let clientStatus = "initializing";
let pollTimer = null;

// ── WhatsApp Connection (Baileys) ───────────────────────────────────

async function connectToWhatsApp() {
  clientStatus = "initializing";
  clientReady = false;

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    // Don't mark as online (saves battery, reduces detection)
    markOnlineOnConnect: false,
    // Suppress verbose Baileys logging
    logger: {
      level: "silent",
      trace: () => {},
      debug: () => {},
      info: () => {},
      warn: (msg) => console.warn("[baileys]", msg),
      error: (msg) => console.error("[baileys]", msg),
      fatal: (msg) => console.error("[baileys]", msg),
      child: () => ({
        level: "silent",
        trace: () => {},
        debug: () => {},
        info: () => {},
        warn: (msg) => console.warn("[baileys]", msg),
        error: (msg) => console.error("[baileys]", msg),
        fatal: (msg) => console.error("[baileys]", msg),
        child: function () { return this; },
      }),
    },
  });

  // Save credentials whenever they update (session persistence)
  sock.ev.on("creds.update", saveCreds);

  // ── Connection state changes ──────────────────────────────────
  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    // QR code received — store for HTTP endpoint
    if (qr) {
      latestQR = qr;
      qrTimestamp = Date.now();
      clientStatus = "waiting_for_qr_scan";
      console.log("\n╔══════════════════════════════════════════╗");
      console.log("║  Scan this QR code with WhatsApp:        ║");
      console.log("║  Phone → Settings → Linked Devices       ║");
      console.log("╚══════════════════════════════════════════╝\n");
    }

    if (connection === "open") {
      clientReady = true;
      clientStatus = "connected";
      latestQR = null;

      // Get our own JID
      if (sock.user && sock.user.id) {
        // Baileys JID format: "15551234567:42@s.whatsapp.net"
        // Normalize to standard format
        MY_WHATSAPP_ID = sock.user.id.replace(/:.*@/, "@");
        console.log("[wa-bridge] My WhatsApp ID: " + MY_WHATSAPP_ID);
      }

      console.log("[wa-bridge] WhatsApp connected ✓ (Baileys/WebSocket)");
      console.log("[wa-bridge] Listening on http://localhost:" + PORT);
      console.log("[wa-bridge] Polling crew-bus every " + POLL_INTERVAL_MS + "ms");

      resolveAgentIds();
      startOutboundPoller();
    }

    if (connection === "close") {
      clientReady = false;
      const statusCode =
        lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;

      if (loggedOut) {
        clientStatus = "logged_out";
        console.warn("[wa-bridge] Logged out — delete wa-session/baileys-auth and restart to re-scan");
      } else {
        clientStatus = "reconnecting";
        const reason = lastDisconnect?.error?.message || "unknown";
        console.warn("[wa-bridge] Disconnected (" + reason + "), reconnecting...");
        // Auto-reconnect (Baileys handles the backoff internally)
        setTimeout(connectToWhatsApp, 3000);
      }
    }
  });

  // ── Inbound messages ──────────────────────────────────────────
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return; // only real-time messages, not history sync

    for (const msg of messages) {
      // Skip group messages and status broadcasts
      const jid = msg.key.remoteJid || "";
      if (jid.endsWith("@g.us") || jid === "status@broadcast") continue;

      // Extract text from message
      const text =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        "";
      if (!text || !text.trim()) continue;

      if (msg.key.fromMe) {
        // Messages YOU sent from your phone → forward to Crew Boss
        // Skip our own outbound echoes
        if (text.startsWith("[Crew Boss]")) return;

        console.log("[wa-bridge] ← You sent on WhatsApp: " + text.substring(0, 80));
      } else {
        // Messages from others → forward to Crew Boss
        console.log("[wa-bridge] ← Inbound from " + jid + ": " + text.substring(0, 80));
      }

      try {
        await postToBus("/api/compose", {
          to_agent: "Crew-Boss",
          message_type: "task",
          subject: "WhatsApp message",
          body: text,
          priority: "normal",
        });
        console.log("[wa-bridge]   → Delivered to crew-bus");
      } catch (err) {
        console.error("[wa-bridge]   ✗ Failed:", err.message);
      }
    }
  });
}

// ── Outbound: crew-bus → WhatsApp ───────────────────────────────────

function startOutboundPoller() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollOutbound, POLL_INTERVAL_MS);
  pollOutbound();
}

async function pollOutbound() {
  if (!clientReady || !MY_WHATSAPP_ID || !sock) return;
  if (!crewBossAgentId) {
    await resolveAgentIds();
    if (!crewBossAgentId) return;
  }

  try {
    const msgs = await getFromBus("/api/messages?limit=20");
    if (!Array.isArray(msgs)) return;

    for (const msg of msgs) {
      if (msg.id <= lastSeenMessageId) continue;

      // Only forward messages FROM Crew-Boss TO a human agent
      if (msg.from_agent_id !== crewBossAgentId) {
        if (msg.id > lastSeenMessageId) lastSeenMessageId = msg.id;
        continue;
      }
      if (msg.to_type !== "human") {
        if (msg.id > lastSeenMessageId) lastSeenMessageId = msg.id;
        continue;
      }

      const text = msg.body || msg.subject || "(empty)";
      console.log("[wa-bridge] → Outbound to WhatsApp: " + text.substring(0, 80));
      try {
        await sock.sendMessage(MY_WHATSAPP_ID, { text: "[Crew Boss] " + text });
        console.log("[wa-bridge]   ✓ Sent to WhatsApp");
      } catch (err) {
        console.error("[wa-bridge]   ✗ Send failed:", err.message);
      }
      lastSeenMessageId = msg.id;
    }
  } catch (err) {
    if (err.code !== "ECONNREFUSED") {
      console.error("[wa-bridge] Poll error:", err.message);
    }
  }
}

// ── Agent ID Resolution ─────────────────────────────────────────────

async function resolveAgentIds() {
  try {
    const agents = await getFromBus("/api/agents");
    if (!Array.isArray(agents)) return;

    for (const a of agents) {
      if (a.agent_type === "human") humanAgentId = a.id;
      if (a.name === "Crew-Boss" && a.status === "active")
        crewBossAgentId = a.id;
    }

    if (humanAgentId && crewBossAgentId) {
      console.log(
        "[wa-bridge] Agent IDs resolved — Human:" +
          humanAgentId +
          " Crew-Boss:" +
          crewBossAgentId
      );

      const msgs = await getFromBus("/api/messages?limit=1");
      if (Array.isArray(msgs) && msgs.length > 0) {
        lastSeenMessageId = msgs[0].id;
        console.log("[wa-bridge] Seeded last message ID: " + lastSeenMessageId);
      }
    } else {
      console.warn("[wa-bridge] Could not find Human or Crew-Boss agent in bus");
    }
  } catch (err) {
    console.warn("[wa-bridge] Agent resolution failed (bus offline?):", err.message);
  }
}

// ── HTTP Helpers (bus communication) ────────────────────────────────

function postToBus(urlPath, data) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    const url = new URL(urlPath, BUS_URL);
    const req = http.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        let chunks = "";
        res.on("data", (d) => (chunks += d));
        res.on("end", () => {
          try {
            resolve(JSON.parse(chunks));
          } catch {
            resolve(chunks);
          }
        });
      }
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function getFromBus(urlPath) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlPath, BUS_URL);
    http
      .get(url, (res) => {
        let chunks = "";
        res.on("data", (d) => (chunks += d));
        res.on("end", () => {
          try {
            resolve(JSON.parse(chunks));
          } catch {
            resolve(chunks);
          }
        });
      })
      .on("error", reject);
  });
}

// ── QR SVG Generation ───────────────────────────────────────────────

function generateQRSvg(qrString) {
  // Simple QR → SVG using the qr data modules
  // Baileys gives us a raw QR string; we encode it ourselves
  try {
    const QRCode = require("qrcode");
    // Return a promise that resolves to SVG string
    return new Promise((resolve, reject) => {
      QRCode.toString(qrString, { type: "svg", margin: 2 }, (err, svg) => {
        if (err) reject(err);
        else resolve(svg);
      });
    });
  } catch {
    // Fallback: return null if qrcode module not available
    return Promise.resolve(null);
  }
}

// ── HTTP Server (for manual sends + status) ─────────────────────────

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");

  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  // GET /status
  if (req.method === "GET" && url.pathname === "/status") {
    respond(res, 200, {
      status: clientStatus,
      ready: clientReady,
      has_qr: !!latestQR,
      whatsapp_id: MY_WHATSAPP_ID,
      human_agent_id: humanAgentId,
      crew_boss_agent_id: crewBossAgentId,
      last_seen_message_id: lastSeenMessageId,
      poll_interval_ms: POLL_INTERVAL_MS,
      engine: "baileys",
    });
    return;
  }

  // GET /qr — raw QR string
  if (req.method === "GET" && url.pathname === "/qr") {
    respond(res, 200, { qr: latestQR, status: clientStatus, timestamp: qrTimestamp });
    return;
  }

  // GET /qr/svg — QR code rendered as inline SVG for dashboard embedding
  if (req.method === "GET" && url.pathname === "/qr/svg") {
    if (!latestQR) {
      respond(res, 200, { svg: null, status: clientStatus });
      return;
    }
    try {
      const svg = await generateQRSvg(latestQR);
      respond(res, 200, { svg: svg, status: clientStatus });
    } catch (err) {
      respond(res, 500, { error: "QR generation failed: " + err.message });
    }
    return;
  }

  // POST /send — manually send a WhatsApp message
  if (req.method === "POST" && url.pathname === "/send") {
    if (!clientReady || !sock) {
      respond(res, 503, { error: "WhatsApp not connected" });
      return;
    }
    if (!MY_WHATSAPP_ID) {
      respond(res, 400, {
        error: "No WhatsApp ID yet — send a message from WhatsApp first",
      });
      return;
    }

    const body = await readBody(req);
    const text = body.text;
    if (!text) {
      respond(res, 400, { error: "need 'text' field" });
      return;
    }

    try {
      await sock.sendMessage(MY_WHATSAPP_ID, { text: text });
      respond(res, 200, { ok: true, sent_to: MY_WHATSAPP_ID });
    } catch (err) {
      respond(res, 500, { error: err.message });
    }
    return;
  }

  // POST /stop — graceful shutdown
  if (req.method === "POST" && url.pathname === "/stop") {
    respond(res, 200, { ok: true, message: "shutting down" });
    gracefulShutdown();
    return;
  }

  respond(res, 404, { error: "not found" });
});

function respond(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => {
      try {
        resolve(JSON.parse(data));
      } catch {
        resolve({});
      }
    });
  });
}

// ── Lifecycle ───────────────────────────────────────────────────────

function gracefulShutdown() {
  console.log("\n[wa-bridge] Shutting down...");
  if (pollTimer) clearInterval(pollTimer);
  if (sock) {
    try {
      sock.end(undefined);
    } catch {
      // ignore
    }
  }
  server.close(() => process.exit(0));
  // Force exit after 5s if graceful close hangs
  setTimeout(() => process.exit(0), 5000);
}

process.on("SIGINT", gracefulShutdown);
process.on("SIGTERM", gracefulShutdown);

// ── Start ───────────────────────────────────────────────────────────

console.log("[wa-bridge] crew-bus WhatsApp Bridge — Crew Boss Only");
console.log("[wa-bridge] Engine: Baileys (WebSocket, no Puppeteer)");
console.log("[wa-bridge] Session dir: " + AUTH_DIR);

server.listen(PORT, () => {
  console.log("[wa-bridge] HTTP server listening on port " + PORT);
  connectToWhatsApp().catch((err) => {
    console.error("[wa-bridge] Fatal connection error:", err.message);
    clientStatus = "error: " + err.message;
  });
});
