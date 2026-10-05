import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";

test("evidence cards render safe text, version warning and accessible preview", async () => {
  const server = await createServer({ server: { middlewareMode: true } });
  try {
    const { default: Cards } = await server.ssrLoadModule("/src/components/EvidenceCards.vue");
    const html = await renderToString(createSSRApp(Cards, { evidence: [{
      evidence_id: "E-0123456789abcdef", source_doc: "测试规范", section_number: "1.2",
      version_status: "unknown", quotes: ['<script>alert("x")</script>'],
    }] }));
    assert.ok(html.includes("生效日期未核实"));
    assert.ok(html.includes("查看条款原文"));
    assert.ok(html.includes('aria-expanded="false"'));
    assert.ok(html.includes("&lt;script&gt;"));
    assert.ok(!html.includes("<script>"));
    const verified = await renderToString(createSSRApp(Cards, { evidence: [{
      evidence_id: "E-0123456789abcdef", source_doc: "测试规范", quotes: [],
      version_status: "verified", effective_from: "2024-01-01", effective_to: "2025-01-01",
    }] }));
    assert.ok(verified.includes("不含终止日"));
    assert.ok(!verified.includes("生效日期未核实"));
  } finally {
    await server.close();
  }
});
