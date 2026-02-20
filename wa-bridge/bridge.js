/**
 * crew-bus WhatsApp Bridge — Crew Boss Only
 *
 * Node.js sidecar that connects WhatsApp to the crew-bus Python system.
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
 *   POST /stop                               → graceful shutdown
 */

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const http = require("http");

// ── Config ──────────────────────────────────────────────────────────

const PORT = parseInt(process.env.WA_PORT || "3001", 10);
const BUS_URL = process.env.BUS_URL || "http://localhost:8080";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL || "5000", 10);

// These get resolved at runtime from the crew-bus API
let MY_WHATSAPP_ID = null; // e.g. "15551234567@c.us" — set after first inbound message
let humanAgentId = null;
let crewBossAgentId = null;
let lastSeenMessageId = 0;
let latestQR = null;        // raw QR string for HTTP endpoint
let qrTimestamp = 0;         // when the QR was generated

// ── WhatsApp Client ─────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "./wa-session" }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--single-process",
    ],
  },
});

let clientReady = false;
let clientStatus = "initializing";

client.on("qr", (qr) => {
  clientStatus = "waiting_for_qr_scan";
  latestQR = qr;
  qrTimestamp = Date.now();
  console.log("\n╔══════════════════════════════════════════╗");
  console.log("║  Scan this QR code with WhatsApp:        ║");
  console.log("║  Phone → Settings → Linked Devices       ║");
  console.log("╚══════════════════════════════════════════╝\n");
  qrcode.generate(qr, { small: true });
});

client.on("ready", async () => {
  clientReady = true;
  clientStatus = "connected";
  latestQR = null;  // no longer needed once connected
  console.log("[wa-bridge] WhatsApp client ready ✓");
  console.log("[wa-bridge] Listening on http://localhost:" + PORT);
  console.log("[wa-bridge] Polling crew-bus every " + POLL_INTERVAL_MS + "ms");

  // Get our own WhatsApp ID so we know who we are
  try {
    const info = client.info;
    if (info && info.wid) {
      MY_WHATSAPP_ID = info.wid._serialized;
      console.log("[wa-bridge] My WhatsApp ID: " + MY_WHATSAPP_ID);
    }
  } catch (e) {
    console.warn("[wa-bridge] Could not get own WhatsApp ID:", e.message);
  }

  resolveAgentIds();
  startOutboundPoller();
});

client.on("authenticated", () => {
  console.log("[wa-bridge] Session authenticated (saved for next restart)");
});

client.on("auth_failure", (msg) => {
  clientStatus = "auth_failed";
  console.error("[wa-bridge] Authentication failed:", msg);
});

client.on("disconnected", (reason) => {
  clientReady = false;
  clientStatus = "disconnected: " + reason;
  console.warn("[wa-bridge] Disconnected:", reason);
  console.log("[wa-bridge] Attempting reconnect in 10s...");
  setTimeout(() => {
    console.log("[wa-bridge] Reconnecting...");
    client.initialize();
  }, 10000);
});

// ── Inbound: WhatsApp → crew-bus ────────────────────────────────────

// Inbound from OTHER people messaging you → forward to Crew Boss
client.on("message", async (msg) => {
  if (msg.isGroupMsg || msg.from === "status@broadcast") return;
  const text = msg.body;
  if (!text || !text.trim()) return;

  console.log("[wa-bridge] ← Inbound from " + msg.from + ": " + text.substring(0, 80));

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
});

// Messages YOU send from your phone → also forward to Crew Boss
// This lets you type on WhatsApp as a way to talk to Crew Boss
client.on("message_create", async (msg) => {
  if (!msg.fromMe) return; // inbound handled by "message" event above
  if (msg.isGroupMsg || msg.to === "status@broadcast") return;

  const text = msg.body;
  if (!text || !text.trim()) return;

  // Skip Crew Boss replies we sent (echo prevention)
  if (text.startsWith("[Crew Boss]")) return;

  console.log("[wa-bridge] ← You sent on WhatsApp: " + text.substring(0, 80));

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
});

// ── Outbound: crew-bus → WhatsApp ───────────────────────────────────

let pollTimer = null;

function startOutboundPoller() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollOutbound, POLL_INTERVAL_MS);
  // Initial poll
  pollOutbound();
}

async function pollOutbound() {
  if (!clientReady || !MY_WHATSAPP_ID) return;
  if (!crewBossAgentId) {
    await resolveAgentIds();
    if (!crewBossAgentId) return;
  }

  try {
    // Fetch recent messages and find ones from Crew-Boss to any human
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

      // New message from Crew-Boss → forward to WhatsApp
      const text = msg.body || msg.subject || "(empty)";
      console.log(
        "[wa-bridge] → Outbound to WhatsApp: " + text.substring(0, 80)
      );
      try {
        await client.sendMessage(MY_WHATSAPP_ID, "[Crew Boss] " + text);
        console.log("[wa-bridge]   ✓ Sent to WhatsApp");
      } catch (err) {
        console.error("[wa-bridge]   ✗ Send failed:", err.message);
      }
      lastSeenMessageId = msg.id;
    }
  } catch (err) {
    // Silent — bus might not be running yet
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

      // Seed lastSeenMessageId so we don't replay old messages
      const msgs = await getFromBus("/api/messages?limit=1");
      if (Array.isArray(msgs) && msgs.length > 0) {
        lastSeenMessageId = msgs[0].id;
        console.log(
          "[wa-bridge] Seeded last message ID: " + lastSeenMessageId
        );
      }
    } else {
      console.warn(
        "[wa-bridge] Could not find Human or Crew-Boss agent in bus"
      );
    }
  } catch (err) {
    console.warn("[wa-bridge] Agent resolution failed (bus offline?):", err.message);
  }
}

// ── HTTP Helpers (bus communication) ────────────────────────────────

function postToBus(path, data) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    const url = new URL(path, BUS_URL);
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

function getFromBus(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BUS_URL);
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
      const QRCode = require("qrcode-terminal/vendor/QRCode");
      const QRErrorCorrectLevel = require("qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel");
      const qr = new QRCode(-1, QRErrorCorrectLevel.M);
      qr.addData(latestQR);
      qr.make();
      const count = qr.getModuleCount();
      const cellSize = 4;
      const margin = 16;
      const size = count * cellSize + margin * 2;
      let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + " " + size + '">';
      svg += '<rect width="' + size + '" height="' + size + '" fill="white"/>';
      for (let r = 0; r < count; r++) {
        for (let c = 0; c < count; c++) {
          if (qr.isDark(r, c)) {
            svg += '<rect x="' + (c * cellSize + margin) + '" y="' + (r * cellSize + margin) + '" width="' + cellSize + '" height="' + cellSize + '" fill="black"/>';
          }
        }
      }
      svg += "</svg>";
      respond(res, 200, { svg: svg, status: clientStatus });
    } catch (err) {
      respond(res, 500, { error: "QR generation failed: " + err.message });
    }
    return;
  }

  // POST /send — manually send a WhatsApp message
  if (req.method === "POST" && url.pathname === "/send") {
    if (!clientReady) {
      respond(res, 503, { error: "WhatsApp not connected" });
      return;
    }
    if (!MY_WHATSAPP_ID) {
      respond(res, 400, {
        error: "No WhatsApp ID yet — send a message from WhatsApp first to register your number",
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
      await client.sendMessage(MY_WHATSAPP_ID, text);
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
  client
    .destroy()
    .then(() => {
      console.log("[wa-bridge] WhatsApp client destroyed");
      server.close(() => process.exit(0));
    })
    .catch(() => process.exit(0));
}

process.on("SIGINT", gracefulShutdown);
process.on("SIGTERM", gracefulShutdown);

// ── Start ───────────────────────────────────────────────────────────

console.log("[wa-bridge] crew-bus WhatsApp Bridge — Crew Boss Only");
console.log("[wa-bridge] Initializing WhatsApp client...");
console.log("[wa-bridge] Session dir: ./wa-session/");

server.listen(PORT, () => {
  client.initialize();
});
