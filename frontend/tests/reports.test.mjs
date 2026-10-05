import test from "node:test";
import assert from "node:assert/strict";
import { availableActions, reportRequest, statusLabels } from "../src/services/reports.js";
import { createServer } from "vite";
import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";

test("report panel renders accessible request form and safe-boundary guidance", async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { default: Panel } = await server.ssrLoadModule("/src/components/ReportPanel.vue");
    const html = await renderToString(createSSRApp(Panel, { token: "test" }));
    assert.ok(html.includes('id="report-question"'));
    assert.ok(html.includes("关闭页面不取消任务"));
    assert.ok(html.includes("暂停在节点完成后生效"));
    assert.ok(html.includes("暂无任务"));
  } finally { await server.close(); }
});

test("terminal tasks have no mutating controls; approval only at input gate", () => {
  assert.deepEqual(availableActions("completed"), []);
  assert.deepEqual(availableActions("cancelled"), []);
  assert.ok(!availableActions("running").includes("approve"));
  assert.ok(availableActions("awaiting_input").includes("approve"));
  assert.equal(statusLabels.pause_requested, "等待安全暂停");
});

test("report transport includes bearer and revision, surfaces conflicts, supports blobs", async () => {
  const original = global.fetch;
  try {
    global.fetch = async (url, options) => {
      assert.equal(url, "/api/reports/task/actions");
      assert.equal(options.headers.Authorization, "Bearer token");
      assert.equal(JSON.parse(options.body).expected_revision, 4);
      return new Response(JSON.stringify({ detail: "refresh and retry" }), { status: 409 });
    };
    await assert.rejects(reportRequest("/task/actions", "token", { method: "POST",
      body: { action: "approve", expected_revision: 4 } }), /refresh and retry/);
    global.fetch = async () => new Response("zip-content");
    assert.equal(await (await reportRequest("/task/artifacts/export", "token", { blob: true })).text(), "zip-content");
  } finally { global.fetch = original; }
});
