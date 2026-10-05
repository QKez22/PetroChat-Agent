<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import MarkdownIt from "markdown-it";
import { availableActions, reportRequest, statusLabels } from "../services/reports";

const props = defineProps({ token: { type: String, required: true } });
const tasks = ref([]), selectedId = ref(""), question = ref(""), revisionQuestion = ref("");
const error = ref(""), busy = ref(false), draft = ref(""), chartUrl = ref(""), events = ref([]);
const selected = computed(() => tasks.value.find(item => item.id === selectedId.value));
const actions = computed(() => availableActions(selected.value?.status));
const labels = { approve: "确认并继续", revise: "按新需求重新生成", pause: "暂停", resume: "恢复 / 重试", cancel: "取消任务" };
const md = new MarkdownIt({ html: false, breaks: true });
// Only authenticated blob charts are displayed; never fetch Markdown image URLs.
md.renderer.rules.image = () => "";
const renderedDraft = computed(() => md.render(draft.value));
let timer, disposed = false, loading = false, controller = new AbortController();
let previewKey = "";

function request(path, options = {}) {
  return reportRequest(path, props.token, { ...options, signal: controller.signal });
}

function clearPreview() {
  previewKey = "";
  draft.value = "";
  events.value = [];
  if (chartUrl.value) URL.revokeObjectURL(chartUrl.value);
  chartUrl.value = "";
}

async function loadDetail() {
  const row = selected.value;
  if (!row) return;
  const identity = row.id;
  const artifact = row.state_json.artifacts || {};
  const key = `${identity}:${artifact.draft || ""}:${artifact.chart || ""}`;
  const history = await request(`/${identity}/events`);
  if (selectedId.value !== identity || disposed) return;
  events.value = history.slice(-12);
  if (key === previewKey) return;
  clearPreview();
  events.value = history.slice(-12);
  const text = artifact.draft ? await (await request(`/${identity}/artifacts/draft`, { blob: true })).text() : "";
  const chart = artifact.chart ? await request(`/${identity}/artifacts/chart`, { blob: true }) : null;
  if (selectedId.value !== identity || disposed) return;
  draft.value = text;
  chartUrl.value = chart ? URL.createObjectURL(chart) : "";
  previewKey = key;
}

async function refresh() {
  if (loading || disposed || !props.token) return;
  loading = true;
  try {
    const rows = await request("");
    if (disposed) return;
    tasks.value = rows;
    if (!selected.value) selectedId.value = rows[0]?.id || "";
    await loadDetail();
  } catch (err) {
    if (err.name !== "AbortError") error.value = err.message;
  } finally { loading = false; }
}

async function mutate(operation) {
  busy.value = true;
  error.value = "";
  try { await operation(); }
  catch (err) { if (err.name !== "AbortError") error.value = err.message; }
  finally { busy.value = false; await refresh(); }
}

function create() {
  return mutate(async () => {
    const row = await request("", { method: "POST", body: { question: question.value } });
    tasks.value.unshift(row);
    selectedId.value = row.id;
    question.value = "";
  });
}

function act(action) {
  const row = selected.value;
  return mutate(async () => {
    await request(`/${row.id}/actions`, { method: "POST", body: {
      expected_revision: row.revision, action, comment: action === "revise" ? revisionQuestion.value : "",
    } });
    revisionQuestion.value = "";
  });
}

function download() {
  return mutate(async () => {
    const blob = await request(`/${selected.value.id}/artifacts/export`, { blob: true });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "report.zip"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

async function poll() {
  if (!document.hidden && !busy.value) await refresh();
  if (!disposed) timer = setTimeout(poll, 2000);
}

watch(selectedId, () => { clearPreview(); revisionQuestion.value = ""; });
onMounted(poll);
onUnmounted(() => {
  disposed = true; clearTimeout(timer); controller.abort(); clearPreview();
});
</script>

<template>
  <section class="report-panel">
    <header><h2>可恢复报表</h2><p>确认方案 → 固定数据快照 → 确认草稿 → ZIP 导出</p></header>
    <p class="hint">关闭页面不取消任务。暂停在节点完成后生效；修改统计口径会生成新版本并重新审批。</p>
    <form class="create-report" @submit.prevent="create">
      <label for="report-question">报表需求（请明确时间、分组维度、统计口径）</label>
      <textarea id="report-question" v-model="question" minlength="3" maxlength="2000" required placeholder="例如：统计各专业的事务数量，按数量降序排列" />
      <button :disabled="busy || question.trim().length < 3">创建报表</button>
    </form>
    <p v-if="error" class="report-error" role="alert">{{ error }}</p>
    <div class="report-grid">
      <aside class="report-list" aria-label="我的报表任务">
        <button type="button" :disabled="busy" @click="error = ''; refresh()">刷新任务</button>
        <p v-if="!tasks.length">暂无任务</p>
        <button v-for="task in tasks" :key="task.id" :class="{ chosen: task.id === selectedId }" type="button"
                @click="selectedId = task.id; refresh()">
          <strong>{{ task.question }}</strong><span>{{ statusLabels[task.status] || task.status }}</span>
        </button>
      </aside>
      <article v-if="selected" class="report-detail">
        <h3>{{ selected.question }}</h3>
        <p aria-live="polite">{{ statusLabels[selected.status] }} · 版本 {{ selected.state_json.generation + 1 }} · {{ selected.workflow_version }}</p>
        <p class="hint">当前步骤：{{ (selected.state_json.next || []).join(' → ') || '等待调度 / 已结束' }}</p>
        <p v-if="selected.state_json.error" class="report-error">{{ selected.state_json.error }}</p>
        <div v-if="selected.state_json.review && selected.status === 'awaiting_input'" class="review-box">
          <h4>{{ selected.state_json.review.stage === 'plan' ? '请确认执行方案' : '请确认下方报表草稿' }}</h4>
          <pre v-if="selected.state_json.review.text">{{ selected.state_json.review.text }}</pre>
          <p>确认后后台将继续执行。修改需求请填写完整的新口径。</p>
        </div>
        <label v-if="actions.includes('revise')" class="revision-field">修改后的完整需求
          <textarea v-model="revisionQuestion" maxlength="2000" placeholder="填写完整的新需求；将重新查询并生成快照" />
        </label>
        <div class="report-actions">
          <button v-for="action in actions" :key="action" type="button"
                  :disabled="busy || (action === 'revise' && revisionQuestion.trim().length < 3)" @click="act(action)">{{ labels[action] }}</button>
          <button v-if="selected.status === 'completed'" type="button" :disabled="busy" @click="download">下载 ZIP</button>
        </div>
        <div v-if="draft" class="report-markdown" v-html="renderedDraft" />
        <img v-if="chartUrl" class="report-chart" :src="chartUrl" alt="当前快照统计图表" />
        <details><summary>任务事件记录</summary><ol><li v-for="event in events" :key="event.id">{{ event.event_type }} · {{ event.payload.status || 'created' }} · {{ event.created_at }} UTC</li></ol></details>
      </article>
    </div>
  </section>
</template>

<style scoped>
.report-panel { padding: 28px; overflow-y: auto; height: 100%; color: #243247; }
.report-panel h2 { margin: 0; }
.hint, header p { color: #627086; font-size: 13px; line-height: 1.7; }
.create-report, .revision-field { display: grid; gap: 10px; margin: 20px 0; }
textarea { width: 100%; min-height: 80px; padding: 12px; border: 1px solid #b9c9da; border-radius: 8px; font: inherit; resize: vertical; box-sizing: border-box; }
button { padding: 9px 14px; border: 1px solid #a4bacf; border-radius: 8px; background: #f5f9fd; color: #20496c; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.create-report button { justify-self: start; background: #20496c; color: white; }
.report-grid { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 22px; }
.report-list { display: flex; flex-direction: column; gap: 10px; }
.report-list button { text-align: left; overflow-wrap: anywhere; }
.report-list strong, .report-list span { display: block; margin: 4px 0; }
.report-list .chosen { border-color: #226791; background: #e4f0f8; }
.report-detail { padding: 20px; border: 1px solid #d5e0ea; border-radius: 12px; min-width: 0; }
.review-box { padding: 14px; background: #edf6ff; border-radius: 8px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.report-actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }
.report-error { color: #a02727; }
.report-chart { max-width: 100%; }
.report-markdown { overflow-x: auto; overflow-wrap: anywhere; line-height: 1.7; }
.report-markdown :deep(td), .report-markdown :deep(th) { border: 1px solid #d5e0ea; padding: 6px 10px; }
details { margin-top: 20px; font-size: 12px; }
@media(max-width: 900px) { .report-grid { grid-template-columns: 1fr; } .report-panel { padding: 16px; } }
</style>
