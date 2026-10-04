<script setup>
import { ref } from "vue";
import { getEvidence } from "../services/chatStream";

const props = defineProps({
  evidence: { type: Array, default: () => [] },
  token: { type: String, default: "" },
  asOf: { type: String, default: "" },
});
const previews = ref({});
const errors = ref({});
const loading = ref({});
const info = item => ({ ...item, ...(previews.value[item.evidence_id] || {}) });
async function preview(item) {
  const id = item.evidence_id;
  if (previews.value[id]) { delete previews.value[id]; return; }
  loading.value[id] = true;
  errors.value[id] = "";
  try {
    // 每次重新展开都重新鉴权，旧快照/撤销权限时不回退到缓存原文。
    previews.value[id] = await getEvidence(id, props.token, props.asOf);
  } catch (error) {
    errors.value[id] = error.message;
  } finally {
    loading.value[id] = false;
  }
}
</script>

<template>
  <section v-if="evidence.length" class="evidence-cards" aria-label="回答原文依据">
    <h4>可核查的原文依据</h4>
    <article v-for="item in evidence" :key="item.evidence_id" class="evidence-card">
      <strong>{{ info(item).source_doc }} · {{ info(item).section_number || "未编号条款" }}</strong>
      <small>{{ item.evidence_id }} · 版本 {{ info(item).version_id?.slice(0, 12) || "未标注" }}</small>
      <p v-if="info(item).version_status !== 'verified'" class="evidence-warning">生效日期未核实，仅供资料参考</p>
      <p v-else>有效期：{{ info(item).effective_from }} 至 {{ info(item).effective_to || "未设终止日期" }}（不含终止日）</p>
      <blockquote v-for="quote in item.quotes" :key="quote">{{ quote }}</blockquote>
      <button type="button" :disabled="loading[item.evidence_id]" :aria-expanded="Boolean(previews[item.evidence_id])" @click="preview(item)">
        {{ loading[item.evidence_id] ? "正在核验访问权限…" : previews[item.evidence_id] ? "收起原文" : "查看条款原文" }}
      </button>
      <p v-if="errors[item.evidence_id]" role="alert">{{ errors[item.evidence_id] }}</p>
      <pre v-if="previews[item.evidence_id]">{{ previews[item.evidence_id].content }}</pre>
    </article>
  </section>
</template>

<style scoped>
.evidence-cards { margin-top: 16px; display: grid; gap: 10px; }
.evidence-cards h4 { margin: 0; }
.evidence-card { border: 1px solid #cbd5e1; border-radius: 10px; padding: 14px; background: #f8fafc; color: #1e293b; }
.evidence-card small { display: block; margin-top: 6px; overflow-wrap: anywhere; }
.evidence-card blockquote { margin: 10px 0; padding-left: 12px; border-left: 3px solid #0284c7; white-space: pre-wrap; }
.evidence-card button { border: 1px solid #94a3b8; border-radius: 6px; padding: 6px 10px; background: white; cursor: pointer; }
.evidence-card pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 400px; overflow: auto; }
.evidence-warning { color: #92400e; }
</style>
