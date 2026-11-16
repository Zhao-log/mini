/**
 * Minimal Agent 同源 API 客户端。
 * 仅负责 HTTP 与错误规范化；会话状态由 app.js 管理，核心逻辑仍在 Python Agent 中。
 */

export class APIError extends Error {
  constructor(message, { status = 0, code = "request_failed" } = {}) {
    super(message);
    this.name = "APIError";
    this.status = status;
    this.code = code;
  }
}

async function request(path, { method = "GET", body } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new APIError("无法连接本地 Agent 服务，请确认 web_server.py 正在运行。", {
      code: "network_error",
    });
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new APIError("服务返回了无法解析的响应。", {
      status: response.status,
      code: "invalid_response",
    });
  }

  if (!response.ok) {
    throw new APIError(payload.error?.message || `请求失败（${response.status}）`, {
      status: response.status,
      code: payload.error?.code || "request_failed",
    });
  }
  return payload;
}

/**
 * 解析单个 SSE 事件块（形如 "event: trace\ndata: {...}"）。
 * 返回 null 表示该块不是有效数据帧。
 */
function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: null };
  }
}

/**
 * 以 SSE 方式发送消息，逐条回调 Agent 的执行过程。
 * 服务端在 done / error 后关闭连接，因此这里读到 EOF 即结束。
 */
async function streamMessage(sessionId, message, { signal, onEvent } = {}) {
  let response;
  try {
    response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new APIError("无法连接本地 Agent 服务，请确认 web_server.py 正在运行。", {
      code: "network_error",
    });
  }

  if (!response.ok || !response.body) {
    let detail = { status: response.status, code: "request_failed", message: `请求失败（${response.status}）` };
    try {
      const payload = await response.json();
      detail.message = payload.error?.message || detail.message;
      detail.code = payload.error?.code || detail.code;
    } catch { /* 非 JSON 错误响应，保留默认文案。 */ }
    throw new APIError(detail.message, detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseSseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) onEvent?.(frame.event, frame.data);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export const agentApi = {
  health: () => request("/api/health"),
  tools: () => request("/api/tools"),
  listSessions: () => request("/api/sessions"),
  getSession: (sessionId) => request(`/api/sessions/${encodeURIComponent(sessionId)}`),
  createSession: (sessionId) => request("/api/sessions", {
    method: "POST",
    body: sessionId ? { session_id: sessionId } : {},
  }),
  deleteSession: (sessionId) => request(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  }),
  resetSession: (sessionId) => request(`/api/sessions/${encodeURIComponent(sessionId)}/reset`, {
    method: "POST",
    body: {},
  }),
  sendMessage: (sessionId, message) => request("/api/chat", {
    method: "POST",
    body: { session_id: sessionId, message },
  }),
  sendMessageStream: streamMessage,
};

