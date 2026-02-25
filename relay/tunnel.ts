/**
 * TunnelDurableObject — manages the WebSocket tunnel between the relay
 * and a single user's Mac running CrewBus.
 *
 * One Durable Object instance per user. The Mac connects via WebSocket
 * and the relay forwards MCP requests through it.
 */

interface TunnelRequest {
  type: "mcp_request";
  id: string;
  body: unknown;
}

interface TunnelResponse {
  type: "mcp_response";
  id: string;
  body: unknown;
}

interface PingMessage {
  type: "ping";
}

interface PongMessage {
  type: "pong";
}

type TunnelMessage = TunnelRequest | TunnelResponse | PingMessage | PongMessage;

interface PendingRequest {
  resolve: (body: unknown) => void;
  reject: (error: Error) => void;
  timer: number;
}

const REQUEST_TIMEOUT_MS = 195_000;
const KEEPALIVE_INTERVAL_MS = 30_000;

export class TunnelDurableObject implements DurableObject {
  private socket: WebSocket | null = null;
  private pending: Map<string, PendingRequest> = new Map();
  private keepaliveInterval: number | null = null;
  private lastPong: number = 0;

  constructor(
    private state: DurableObjectState,
    private env: unknown,
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/status") {
      return Response.json({ connected: this.isConnected });
    }

    if (url.pathname === "/forward") {
      const body = await request.json();
      try {
        const result = await this.forwardRequest(body);
        return Response.json(result);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        return Response.json({ error: message }, { status: 502 });
      }
    }

    if (url.pathname === "/websocket") {
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("Expected WebSocket upgrade", { status: 426 });
      }
      return this.handleWebSocketUpgrade();
    }

    return new Response("Not found", { status: 404 });
  }

  get isConnected(): boolean {
    return this.socket !== null;
  }

  async forwardRequest(body: unknown): Promise<unknown> {
    if (!this.socket) {
      throw new Error("Mac tunnel not connected");
    }

    const id = crypto.randomUUID();

    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Request timed out after 30 seconds"));
      }, REQUEST_TIMEOUT_MS) as unknown as number;

      this.pending.set(id, { resolve, reject, timer });

      const message: TunnelRequest = {
        type: "mcp_request",
        id,
        body,
      };

      try {
        this.socket!.send(JSON.stringify(message));
      } catch (err) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new Error("Failed to send request to Mac tunnel"));
      }
    });
  }

  private handleWebSocketUpgrade(): Response {
    // Close any existing connection
    if (this.socket) {
      try {
        this.socket.close(1000, "New connection replacing old one");
      } catch {
        // Ignore close errors on stale socket
      }
      this.cleanupConnection();
    }

    const pair = new WebSocketPair();
    const [client, server] = [pair[0], pair[1]];

    this.state.acceptWebSocket(server);
    this.socket = server;
    this.lastPong = Date.now();

    this.startKeepalive();

    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws: WebSocket, data: string | ArrayBuffer): void {
    if (typeof data !== "string") {
      return;
    }

    let message: TunnelMessage;
    try {
      message = JSON.parse(data);
    } catch {
      return;
    }

    switch (message.type) {
      case "pong":
        this.lastPong = Date.now();
        break;

      case "ping":
        try {
          ws.send(JSON.stringify({ type: "pong" }));
        } catch {
          // Connection may be dead
        }
        break;

      case "mcp_response":
        this.handleMcpResponse(message as TunnelResponse);
        break;

      default:
        break;
    }
  }

  webSocketClose(ws: WebSocket, code: number, reason: string, wasClean: boolean): void {
    this.cleanupConnection();
  }

  webSocketError(ws: WebSocket, error: unknown): void {
    this.cleanupConnection();
  }

  private handleMcpResponse(message: TunnelResponse): void {
    const pending = this.pending.get(message.id);
    if (!pending) {
      return;
    }

    clearTimeout(pending.timer);
    this.pending.delete(message.id);
    pending.resolve(message.body);
  }

  private startKeepalive(): void {
    this.stopKeepalive();

    this.keepaliveInterval = setInterval(() => {
      if (!this.socket) {
        this.stopKeepalive();
        return;
      }

      // If we haven't received a pong in 2x the interval, consider connection dead
      if (Date.now() - this.lastPong > KEEPALIVE_INTERVAL_MS * 2) {
        try {
          this.socket.close(1001, "Keepalive timeout");
        } catch {
          // Ignore
        }
        this.cleanupConnection();
        return;
      }

      try {
        this.socket.send(JSON.stringify({ type: "ping" }));
      } catch {
        this.cleanupConnection();
      }
    }, KEEPALIVE_INTERVAL_MS) as unknown as number;
  }

  private stopKeepalive(): void {
    if (this.keepaliveInterval !== null) {
      clearInterval(this.keepaliveInterval);
      this.keepaliveInterval = null;
    }
  }

  private cleanupConnection(): void {
    this.stopKeepalive();
    this.socket = null;

    // Reject all pending requests
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(new Error("Mac tunnel disconnected"));
    }
    this.pending.clear();
  }
}
