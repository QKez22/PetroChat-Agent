const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];

  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  const rawData = dataLines.join("\n");
  let data = {};
  if (rawData) {
    try {
      data = JSON.parse(rawData);
    } catch {
      data = { raw: rawData };
    }
  }
  return { event, data };
}

async function readJson(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  return data;
}

export async function login(username, password) {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return readJson(response);
}

export async function getMe(token) {
  const response = await fetch(`${API_BASE}/api/auth/me?token=${encodeURIComponent(token)}`);
  return readJson(response);
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function streamChat(question, handlers, signal, options = {}) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      question,
      session_id: options.sessionId || null,
      user_id: options.userId || "default",
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) {
        continue;
      }
      const message = parseSseBlock(block);
      handlers.onEvent?.(message);
      handlers[message.event]?.(message.data);
    }
  }

  if (buffer.trim()) {
    const message = parseSseBlock(buffer);
    handlers.onEvent?.(message);
    handlers[message.event]?.(message.data);
  }
}

export async function sendChat(question, signal, options = {}) {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      session_id: options.sessionId || null,
      user_id: options.userId || "default",
    }),
    signal,
  });

  return readJson(response);
}

export async function listSessions(userId, limit = 30) {
  const params = new URLSearchParams({
    user_id: userId || "default",
    limit: String(limit),
  });
  const response = await fetch(`${API_BASE}/api/sessions?${params.toString()}`);
  return readJson(response);
}

export async function getSession(sessionId, userId) {
  const params = new URLSearchParams({
    user_id: userId || "default",
  });
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}?${params.toString()}`);
  return readJson(response);
}

export async function deleteSession(sessionId, userId) {
  const params = new URLSearchParams({
    user_id: userId || "default",
  });
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}?${params.toString()}`, {
    method: "DELETE",
  });
  return readJson(response);
}

export async function getLatestEvaluation() {
  const response = await fetch(`${API_BASE}/api/evaluation/latest`);
  return readJson(response);
}

export async function getEvaluationFailures(limit = 8) {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`${API_BASE}/api/evaluation/failures?${params.toString()}`);
  return readJson(response);
}

export async function getEvaluationRuns(limit = 10) {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`${API_BASE}/api/evaluation/runs?${params.toString()}`);
  return readJson(response);
}

export async function listMemories(userId, options = {}) {
  const params = new URLSearchParams({
    user_id: userId || "default",
    status: options.status || "active",
    limit: String(options.limit || 50),
  });
  if (options.memoryType) {
    params.set("memory_type", options.memoryType);
  }
  const response = await fetch(`${API_BASE}/api/memory?${params.toString()}`);
  return readJson(response);
}

export async function createMemory(payload) {
  const response = await fetch(`${API_BASE}/api/memory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function disableMemory(memoryId, actorId, reason) {
  const response = await fetch(`${API_BASE}/api/memory/${memoryId}/disable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actor_id: actorId || null,
      reason: reason || "frontend disable",
    }),
  });
  return readJson(response);
}

export async function deleteMemory(memoryId, actorId, reason) {
  const params = new URLSearchParams({
    reason: reason || "frontend delete",
  });
  if (actorId) {
    params.set("actor_id", actorId);
  }
  const response = await fetch(`${API_BASE}/api/memory/${memoryId}?${params.toString()}`, {
    method: "DELETE",
  });
  return readJson(response);
}

export async function getMemoryEvents(memoryId, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`${API_BASE}/api/memory/${memoryId}/events?${params.toString()}`);
  return readJson(response);
}
