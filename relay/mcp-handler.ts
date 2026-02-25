/**
 * MCP protocol handler for the CrewBus relay.
 *
 * Accepts JSON-RPC 2.0 requests (single or batch), forwards them through
 * the user's tunnel Durable Object to their Mac, and returns the response.
 */

interface JsonRpcRequest {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
  id?: string | number | null;
}

interface JsonRpcError {
  jsonrpc: "2.0";
  error: { code: number; message: string; data?: unknown };
  id: string | number | null;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
  id: string | number | null;
}

const MAC_NOT_CONNECTED_ERROR = {
  code: -32000,
  message:
    "Your CrewBus Mac app is not connected. Open CrewBus on your Mac to use your agents.",
};

/**
 * MCP methods that the relay can handle locally without a tunnel connection.
 * This allows the MCP handshake to succeed even when the Mac app is offline,
 * so clients like claude.ai don't mistake a disconnected tunnel for an auth failure.
 */
function handleLocalMethod(rpcRequest: JsonRpcRequest): Response | null {
  const { method, id } = rpcRequest;

  if (method === "initialize") {
    const sessionId = crypto.randomUUID();
    return Response.json(
      {
        jsonrpc: "2.0",
        result: {
          protocolVersion: "2025-03-26",
          capabilities: { tools: {} },
          serverInfo: { name: "CrewBus Relay", version: "1.0.0" },
        },
        id: id ?? null,
      },
      { headers: { "Content-Type": "application/json", "Mcp-Session-Id": sessionId } },
    );
  }

  if (method === "notifications/initialized") {
    // Notification — no response needed, return 202 Accepted
    return new Response(null, { status: 202 });
  }

  if (method === "tools/list") {
    return Response.json(
      {
        jsonrpc: "2.0",
        result: { tools: [] },
        id: id ?? null,
      },
      { headers: { "Content-Type": "application/json" } },
    );
  }

  return null; // Not a locally-handled method
}

/**
 * Handle an incoming MCP request. Accepts the raw Request, forwards it
 * through the tunnel DO, and returns a Response with the JSON-RPC result.
 */
export async function handleMcpRequest(
  request: Request,
  tunnelStub: DurableObjectStub,
  userId: string,
): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return mcpErrorResponse(null, {
      code: -32700,
      message: "Parse error: invalid JSON",
    });
  }

  // Handle batch requests
  if (Array.isArray(body)) {
    return handleBatch(body, tunnelStub);
  }

  const rpcRequest = body as JsonRpcRequest;

  // Check tunnel connectivity
  const statusRes = await tunnelStub.fetch(new Request("http://tunnel/status"));
  const status = (await statusRes.json()) as { connected: boolean };

  if (!status.connected) {
    // Handle MCP handshake methods locally so the connection succeeds
    const localResponse = handleLocalMethod(rpcRequest);
    if (localResponse) return localResponse;

    // For everything else, tell the user their Mac isn't connected
    return mcpErrorResponse(rpcRequest.id ?? null, MAC_NOT_CONNECTED_ERROR);
  }

  // Tunnel is connected — forward everything to the Mac
  return handleSingle(rpcRequest, tunnelStub);
}

async function handleSingle(
  rpcRequest: JsonRpcRequest,
  tunnelStub: DurableObjectStub,
): Promise<Response> {
  if (!rpcRequest.jsonrpc || rpcRequest.jsonrpc !== "2.0" || !rpcRequest.method) {
    return mcpErrorResponse(rpcRequest.id ?? null, {
      code: -32600,
      message: "Invalid JSON-RPC request",
    });
  }

  try {
    const forwardRes = await tunnelStub.fetch(
      new Request("http://tunnel/forward", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rpcRequest),
      }),
    );

    if (!forwardRes.ok) {
      const err = (await forwardRes.json()) as { error?: string };
      return mcpErrorResponse(rpcRequest.id ?? null, {
        code: -32000,
        message: err.error ?? "Tunnel forwarding failed",
      });
    }

    const result = await forwardRes.json();
    return Response.json(result, {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal relay error";
    return mcpErrorResponse(rpcRequest.id ?? null, {
      code: -32603,
      message,
    });
  }
}

async function handleBatch(
  requests: unknown[],
  tunnelStub: DurableObjectStub,
): Promise<Response> {
  if (requests.length === 0) {
    return mcpErrorResponse(null, {
      code: -32600,
      message: "Empty batch request",
    });
  }

  const results = await Promise.all(
    requests.map(async (req) => {
      const rpc = req as JsonRpcRequest;
      const res = await handleSingle(rpc, tunnelStub);
      return res.json();
    }),
  );

  return Response.json(results, {
    headers: { "Content-Type": "application/json" },
  });
}

function mcpErrorResponse(
  id: string | number | null,
  error: { code: number; message: string; data?: unknown },
): Response {
  const body: JsonRpcError = {
    jsonrpc: "2.0",
    error,
    id,
  };
  return Response.json(body, {
    status: 200, // JSON-RPC errors use 200 with error in body
    headers: { "Content-Type": "application/json" },
  });
}
