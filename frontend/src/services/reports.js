const API_BASE = import.meta.env?.VITE_API_BASE_URL || "";

export async function reportRequest(path, token, { method = "GET", body, signal, blob = false } = {}) {
  const response = await fetch(`${API_BASE}/api/reports${path}`, {
    method, signal,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`);
  }
  return blob ? response.blob() : response.json();
}

export const statusLabels = {
  queued: "排队中", running: "执行中", awaiting_input: "等待确认",
  pause_requested: "等待安全暂停", paused: "已暂停", failed: "执行失败",
  completed: "已完成", cancelled: "已取消",
};

export function availableActions(status) {
  return {
    queued: ["pause", "cancel"], running: ["pause", "cancel"],
    pause_requested: ["cancel"], paused: ["resume", "revise", "cancel"],
    failed: ["resume", "revise", "cancel"], awaiting_input: ["approve", "revise", "cancel"],
  }[status] || [];
}
