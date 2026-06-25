<script setup>
import MarkdownIt from "markdown-it";
import {
  Activity,
  BarChart3,
  Bot,
  CircleStop,
  ClipboardList,
  Database,
  Download,
  FileText,
  Gauge,
  History,
  KeyRound,
  Loader2,
  Lock,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  Wrench,
} from "lucide-vue-next";
import { computed, nextTick, onMounted, ref, watch } from "vue";

import {
  checkHealth,
  deleteSession,
  getEvaluationFailures,
  getEvaluationRuns,
  getMe,
  getLatestEvaluation,
  getSession,
  listSessions,
  login,
  sendChat,
  streamChat,
} from "./services/chatStream";
import { evaluationSummary as fallbackEvaluationSummary } from "./data/evaluationSummary";

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

const examples = [
  { icon: FileText, label: "规范问答", text: "什么是 ITPM 策略？" },
  { icon: Database, label: "事务查询", text: "查询仪表专业的运行中事务清单" },
  { icon: BarChart3, label: "统计报表", text: "统计各专业的事务数量" },
  { icon: Gauge, label: "单位换算", text: "1 MPa 等于多少 psi？" },
];

const adminCards = [
  { label: "用户与角色", value: "user 表 / authority_flag" },
  { label: "知识库管理", value: "文档 / Chroma / 重建" },
  { label: "Agent 配置", value: "提示词 / 模型参数 / 工具" },
  { label: "审计观察", value: "问答 / 工具 / 质量指标" },
];

const TOKEN_STORAGE_KEY = "petrochat.auth.token";
const USER_STORAGE_KEY = "petrochat.auth.user";
const LOG_STORAGE_KEY = "petrochat.admin.turns";
const SESSION_STORAGE_KEY = "petrochat.current.session";

const messages = ref([]);
const draft = ref("");
const loginForm = ref({ username: "admin", password: "admin" });
const loginError = ref("");
const isLoggingIn = ref(false);
const isStreaming = ref(false);
const isLoadingSessions = ref(false);
const sessionError = ref("");
const backendStatus = ref("checking");
const backendMessage = ref("连接中");
const activeController = ref(null);
const chatBody = ref(null);
const currentSessionId = ref(localStorage.getItem(SESSION_STORAGE_KEY) || null);
const activeView = ref("chat");
const currentUser = ref(loadStoredUser());
const localToken = ref(localStorage.getItem(TOKEN_STORAGE_KEY) || "");
const sessions = ref([]);
const adminLogs = ref(loadAdminLogs());
const selectedLogId = ref(adminLogs.value[0]?.id || null);
const evaluation = ref(fallbackEvaluationSummary);
const evaluationError = ref("");
const evaluationCases = ref(fallbackEvaluationSummary.issueCases || []);
const evaluationCaseError = ref("");
const selectedEvaluationCaseId = ref(evaluationCases.value[0]?.id || null);
const evaluationRuns = ref(fallbackEvaluationSummary.runs || []);
const evaluationRunError = ref("");
const selectedEvaluationRunId = ref(evaluationRuns.value[0]?.id || null);
const isLoadingEvaluation = ref(false);

const isAdmin = computed(() => currentUser.value?.role === "admin");
const roleLabel = computed(() => (isAdmin.value ? "管理员 admin" : "工程师用户 engineer"));
const canSend = computed(() => Boolean(currentUser.value) && draft.value.trim().length > 0 && !isStreaming.value);
const latestAssistant = computed(() => [...messages.value].reverse().find((m) => m.role === "assistant"));
const selectedLog = computed(() => adminLogs.value.find((item) => item.id === selectedLogId.value) || adminLogs.value[0] || null);
const selectedEvaluationCase = computed(() => (
  evaluationCases.value.find((item) => item.id === selectedEvaluationCaseId.value)
  || evaluationCases.value[0]
  || null
));
const selectedEvaluationRun = computed(() => (
  evaluationRuns.value.find((item) => item.id === selectedEvaluationRunId.value)
  || evaluationRuns.value[0]
  || null
));
const visibleLogs = computed(() => {
  if (isAdmin.value) {
    return adminLogs.value;
  }
  return adminLogs.value.filter((item) => item.userId === currentUser.value?.user_id);
});
const adminStats = computed(() => {
  const total = visibleLogs.value.length;
  const success = visibleLogs.value.filter((item) => item.status === "done").length;
  const error = visibleLogs.value.filter((item) => item.status === "error").length;
  const avgDuration = total
    ? Math.round(visibleLogs.value.reduce((sum, item) => sum + item.durationMs, 0) / total)
    : 0;
  return { total, success, error, avgDuration };
});

function createId() {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

function loadAdminLogs() {
  try {
    return JSON.parse(localStorage.getItem(LOG_STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function persistAdminLogs() {
  localStorage.setItem(LOG_STORAGE_KEY, JSON.stringify(adminLogs.value.slice(0, 100)));
}

function persistAuth(token, user) {
  localToken.value = token;
  currentUser.value = user;
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

function clearAuth() {
  localToken.value = "";
  currentUser.value = null;
  sessions.value = [];
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
  resetConversation();
  activeView.value = "chat";
}

function setCurrentSession(sessionId) {
  currentSessionId.value = sessionId || null;
  if (currentSessionId.value) {
    localStorage.setItem(SESSION_STORAGE_KEY, currentSessionId.value);
  } else {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

function renderMarkdown(content) {
  return md.render(content || "");
}

function scrollToBottom() {
  nextTick(() => {
    if (chatBody.value) {
      chatBody.value.scrollTop = chatBody.value.scrollHeight;
    }
  });
}

async function refreshHealth() {
  backendStatus.value = "checking";
  backendMessage.value = "连接中";
  try {
    await checkHealth();
    backendStatus.value = "online";
    backendMessage.value = "API 在线";
  } catch (error) {
    backendStatus.value = "offline";
    backendMessage.value = error.message || "API 不可达";
  }
}

async function refreshSessions() {
  if (!currentUser.value) {
    sessions.value = [];
    return;
  }
  isLoadingSessions.value = true;
  sessionError.value = "";
  try {
    sessions.value = await listSessions(currentUser.value.user_id, 30);
  } catch (error) {
    sessionError.value = error.message || "会话加载失败";
  } finally {
    isLoadingSessions.value = false;
  }
}

async function refreshEvaluation() {
  if (!isAdmin.value) {
    evaluation.value = fallbackEvaluationSummary;
    evaluationError.value = "";
    evaluationCases.value = fallbackEvaluationSummary.issueCases || [];
    evaluationCaseError.value = "";
    evaluationRuns.value = fallbackEvaluationSummary.runs || [];
    evaluationRunError.value = "";
    return;
  }
  isLoadingEvaluation.value = true;
  evaluationError.value = "";
  evaluationCaseError.value = "";
  evaluationRunError.value = "";
  try {
    evaluation.value = await getLatestEvaluation();
  } catch (error) {
    evaluation.value = fallbackEvaluationSummary;
    evaluationError.value = error.message || "评估摘要加载失败，已使用静态摘要";
  } finally {
    isLoadingEvaluation.value = false;
  }
  try {
    const result = await getEvaluationRuns(10);
    evaluationRuns.value = result.runs || [];
    selectedEvaluationRunId.value = evaluationRuns.value[0]?.id || null;
    if (!evaluationRuns.value.length) {
      evaluationRunError.value = "当前未发现评估历史运行";
    }
  } catch (error) {
    evaluationRuns.value = fallbackEvaluationSummary.runs || [];
    selectedEvaluationRunId.value = evaluationRuns.value[0]?.id || null;
    evaluationRunError.value = error.message || "评估历史加载失败，已使用静态示例";
  }
  try {
    const result = await getEvaluationFailures(8);
    evaluationCases.value = result.cases || [];
    selectedEvaluationCaseId.value = evaluationCases.value[0]?.id || null;
    if (!evaluationCases.value.length) {
      evaluationCaseError.value = "当前 prediction 未发现失败或风险样例";
    }
  } catch (error) {
    evaluationCases.value = fallbackEvaluationSummary.issueCases || [];
    selectedEvaluationCaseId.value = evaluationCases.value[0]?.id || null;
    evaluationCaseError.value = error.message || "评估样例加载失败，已使用静态示例";
  }
}

async function restoreAuth() {
  if (!localToken.value) {
    return;
  }
  try {
    const user = await getMe(localToken.value);
    persistAuth(localToken.value, user);
    await refreshSessions();
    if (user.role === "admin") {
      await refreshEvaluation();
    }
  } catch {
    clearAuth();
  }
}

async function handleLogin() {
  loginError.value = "";
  isLoggingIn.value = true;
  try {
    const result = await login(loginForm.value.username.trim(), loginForm.value.password);
    persistAuth(result.token, result.user);
    activeView.value = "chat";
    await refreshSessions();
    if (result.user.role === "admin") {
      await refreshEvaluation();
    }
  } catch (error) {
    loginError.value = error.message || "登录失败";
  } finally {
    isLoggingIn.value = false;
  }
}

function applyExample(text) {
  if (isStreaming.value || !currentUser.value) {
    return;
  }
  activeView.value = "chat";
  draft.value = text;
}

function inferRoute(assistant) {
  if (assistant.chart) {
    return "sql";
  }
  if (assistant.citations?.length) {
    return "qa";
  }
  if (assistant.events?.length) {
    return "general";
  }
  return "supervisor";
}

function previewText(text, max = 180) {
  const normalized = (text || "").replace(/\s+/g, " ").trim();
  return normalized.length > max ? `${normalized.slice(0, max)}...` : normalized;
}

function extractCitations(text) {
  const matches = text.match(/\[(\d+(?:\.\d+){1,3})\]/g) || [];
  return [...new Set(matches.map((item) => item.slice(1, -1)))];
}

function saveAdminTurn(question, assistant, startedAt, status) {
  const item = {
    id: createId(),
    userId: currentUser.value?.user_id || "default",
    username: currentUser.value?.username || "unknown",
    role: currentUser.value?.role || "engineer",
    question,
    questionSummary: previewText(question, 120),
    answerPreview: previewText(assistant.content, 240),
    answer: assistant.content || "",
    status,
    route: inferRoute(assistant),
    durationMs: Date.now() - startedAt,
    createdAt: new Date(startedAt).toISOString(),
    updatedAt: new Date().toISOString(),
    sessionId: currentSessionId.value,
    eventCount: assistant.events?.length || 0,
    citationCount: assistant.citations?.length || 0,
    citations: assistant.citations || [],
    chart: assistant.chart,
    events: assistant.events || [],
  };
  adminLogs.value = [item, ...adminLogs.value].slice(0, 100);
  selectedLogId.value = item.id;
  persistAdminLogs();
}

function toChatMessage(record) {
  const base = {
    id: record.id,
    role: record.role,
    content: record.content,
    createdAt: new Date(record.created_at),
  };
  if (record.role === "assistant") {
    return {
      ...base,
      events: [],
      citations: extractCitations(record.content),
      chart: null,
      status: "done",
    };
  }
  return base;
}

async function openSession(sessionId) {
  if (!currentUser.value || isStreaming.value) {
    return;
  }
  sessionError.value = "";
  try {
    const detail = await getSession(sessionId, currentUser.value.user_id);
    messages.value = detail.messages.map(toChatMessage);
    setCurrentSession(detail.session.id);
    activeView.value = "chat";
    scrollToBottom();
  } catch (error) {
    sessionError.value = error.message || "会话打开失败";
  }
}

async function removeSession(sessionId) {
  if (!currentUser.value || isStreaming.value) {
    return;
  }
  sessionError.value = "";
  try {
    await deleteSession(sessionId, currentUser.value.user_id);
    if (currentSessionId.value === sessionId) {
      messages.value = [];
      setCurrentSession(null);
    }
    await refreshSessions();
  } catch (error) {
    sessionError.value = error.message || "会话删除失败";
  }
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(ms) {
  if (!ms) {
    return "0 ms";
  }
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function routeLabel(route) {
  const labels = {
    qa: "QA / RAG",
    sql: "SQL / 报表",
    general: "General / 工具",
    supervisor: "Supervisor",
  };
  return labels[route] || route;
}

function riskLabel(level) {
  const labels = {
    fail: "失败",
    warn: "风险",
    pass: "抽样",
  };
  return labels[level] || level || "未知";
}

function runStatusLabel(status) {
  const labels = {
    scored: "已评分",
    "profile-only": "仅画像",
  };
  return labels[status] || status || "未知";
}

function exportAdminLogs() {
  const payload = visibleLogs.value.map((item) => ({
    id: item.id,
    userId: item.userId,
    username: item.username,
    role: item.role,
    questionSummary: item.questionSummary,
    answerPreview: item.answerPreview,
    route: item.route,
    status: item.status,
    durationMs: item.durationMs,
    sessionId: item.sessionId,
    eventCount: item.eventCount,
    citationCount: item.citationCount,
    createdAt: item.createdAt,
  }));
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `petrochat-admin-logs-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function clearAdminLogs() {
  if (isAdmin.value) {
    adminLogs.value = [];
  } else {
    adminLogs.value = adminLogs.value.filter((item) => item.userId !== currentUser.value?.user_id);
  }
  selectedLogId.value = visibleLogs.value[0]?.id || null;
  persistAdminLogs();
}

function appendToolEvent(kind, data) {
  const assistant = latestAssistant.value;
  if (!assistant) {
    return;
  }
  assistant.events.push({
    id: createId(),
    kind,
    name: data?.name || "tool",
    args: data?.args || null,
    preview: data?.preview || "",
  });
  scrollToBottom();
}

async function sendQuestion() {
  const question = draft.value.trim();
  if (!question || isStreaming.value || !currentUser.value) {
    return;
  }

  const startedAt = Date.now();
  const assistantId = createId();
  const controller = new AbortController();
  activeController.value = controller;
  isStreaming.value = true;
  draft.value = "";

  messages.value.push({
    id: createId(),
    role: "user",
    content: question,
    createdAt: new Date(),
  });
  messages.value.push({
    id: assistantId,
    role: "assistant",
    content: "",
    createdAt: new Date(),
    events: [],
    citations: [],
    chart: null,
    status: "streaming",
  });
  scrollToBottom();

  const assistant = messages.value.find((m) => m.id === assistantId);

  try {
    await streamChat(
      question,
      {
        token(data) {
          assistant.content += data.text || "";
          scrollToBottom();
        },
        tool_call(data) {
          appendToolEvent("call", data);
        },
        tool_result(data) {
          appendToolEvent("result", data);
        },
        meta(data) {
          if (data.session_id) {
            setCurrentSession(data.session_id);
          }
          assistant.citations = data.citations || [];
          if (data.chart_data_uri) {
            assistant.chart = {
              uri: data.chart_data_uri,
              kind: data.chart_kind,
              rows: data.table_row_count,
            };
          }
        },
        error(data) {
          throw new Error(data.message || "流式响应失败");
        },
      },
      controller.signal,
      { sessionId: currentSessionId.value, userId: currentUser.value.user_id },
    );

    if (!assistant.content.trim()) {
      const fallback = await sendChat(question, controller.signal, {
        sessionId: currentSessionId.value,
        userId: currentUser.value.user_id,
      });
      setCurrentSession(fallback.session_id);
      assistant.content = fallback.answer || "";
      assistant.citations = assistant.citations.length ? assistant.citations : fallback.citations || [];
    }

    assistant.status = "done";
  } catch (error) {
    assistant.status = "error";
    assistant.content = error.name === "AbortError" ? "已停止生成。" : `请求失败：${error.message}`;
  } finally {
    saveAdminTurn(question, assistant, startedAt, assistant.status);
    isStreaming.value = false;
    activeController.value = null;
    await refreshSessions();
    scrollToBottom();
  }
}

function stopStreaming() {
  activeController.value?.abort();
}

function resetConversation() {
  if (isStreaming.value) {
    stopStreaming();
  }
  messages.value = [];
  setCurrentSession(null);
}

watch(currentUser, (user) => {
  if (user) {
    refreshSessions();
  }
});

onMounted(async () => {
  await Promise.all([refreshHealth(), restoreAuth()]);
});
</script>

<template>
  <main class="shell" :class="{ locked: !currentUser }">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <Sparkles :size="22" />
        </div>
        <div>
          <h1>PetroChat-Agent</h1>
          <p>v1.1 memory + RBAC</p>
        </div>
      </div>

      <div class="status-row">
        <span class="status-dot" :class="backendStatus"></span>
        <span>{{ backendMessage }}</span>
        <button class="icon-button" title="刷新状态" @click="refreshHealth">
          <RefreshCw :size="16" />
        </button>
      </div>

      <section v-if="currentUser" class="identity-panel">
        <div class="identity-avatar">
          <ShieldCheck v-if="isAdmin" :size="18" />
          <User v-else :size="18" />
        </div>
        <div>
          <strong>{{ currentUser.username }}</strong>
          <span>{{ roleLabel }}</span>
        </div>
        <button class="icon-button" title="退出登录" @click="clearAuth">
          <LogOut :size="16" />
        </button>
      </section>

      <nav v-if="currentUser" class="view-switch" aria-label="工作区切换">
        <button type="button" :class="{ active: activeView === 'chat' }" @click="activeView = 'chat'">
          <MessageSquareText :size="16" />
          对话
        </button>
        <button
          type="button"
          :class="{ active: activeView === 'admin' }"
          :disabled="!isAdmin"
          @click="activeView = 'admin'"
        >
          <ClipboardList :size="16" />
          管理员
        </button>
      </nav>

      <section v-if="currentUser" class="side-section">
        <div class="section-heading">
          <h2>历史会话</h2>
          <button class="tiny-button" type="button" title="刷新会话" @click="refreshSessions">
            <RefreshCw :size="14" :class="{ spin: isLoadingSessions }" />
          </button>
        </div>
        <div class="session-list">
          <div
            v-for="item in sessions"
            :key="item.id"
            class="session-row"
            :class="{ active: currentSessionId === item.id }"
            role="button"
            tabindex="0"
            @click="openSession(item.id)"
            @keydown.enter.prevent="openSession(item.id)"
          >
            <History :size="15" />
            <span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.message_count }} 条 / {{ formatTime(item.updated_at) }}</small>
            </span>
            <button class="delete-mini" type="button" title="删除会话" @click.stop="removeSession(item.id)">
              <Trash2 :size="14" />
            </button>
          </div>
          <p v-if="sessionError" class="side-error">{{ sessionError }}</p>
          <p v-else-if="!isLoadingSessions && !sessions.length" class="side-muted">暂无历史会话</p>
        </div>
      </section>

      <section v-if="currentUser" class="side-section">
        <h2>样例</h2>
        <button
          v-for="item in examples"
          :key="item.text"
          class="example-button"
          type="button"
          @click="applyExample(item.text)"
        >
          <component :is="item.icon" :size="17" />
          <span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.text }}</small>
          </span>
        </button>
      </section>

      <section v-if="currentUser" class="side-section compact">
        <h2>节点</h2>
        <div class="node-list">
          <span><Server :size="15" /> supervisor</span>
          <span><FileText :size="15" /> qa</span>
          <span><Database :size="15" /> sql</span>
          <span><Wrench :size="15" /> general</span>
        </div>
      </section>
    </aside>

    <section v-if="!currentUser" class="login-workspace">
      <form class="login-panel" @submit.prevent="handleLogin">
        <div class="login-heading">
          <Lock :size="28" />
          <div>
            <h2>登录 PetroChat-Agent</h2>
            <p>admin / engineer</p>
          </div>
        </div>

        <label>
          <span>账号</span>
          <input v-model="loginForm.username" autocomplete="username" maxlength="255" />
        </label>

        <label>
          <span>密码</span>
          <input v-model="loginForm.password" autocomplete="current-password" maxlength="255" type="password" />
        </label>

        <p v-if="loginError" class="login-error">{{ loginError }}</p>

        <button class="login-button" type="submit" :disabled="isLoggingIn">
          <Loader2 v-if="isLoggingIn" :size="17" class="spin" />
          <KeyRound v-else :size="17" />
          登录
        </button>
      </form>
    </section>

    <section v-else class="workspace">
      <header v-if="activeView === 'chat'" class="topbar">
        <div>
          <h2>多 Agent 对话工作台</h2>
          <p>Supervisor 路由 / RAG / NL2SQL / Tool Calling</p>
          <small v-if="currentSessionId" class="session-hint">Session {{ currentSessionId.slice(0, 8) }}</small>
        </div>
        <button class="secondary-button" type="button" @click="resetConversation">
          <RefreshCw :size="16" />
          新会话
        </button>
      </header>

      <div v-if="activeView === 'chat'" ref="chatBody" class="chat-body">
        <div v-if="messages.length === 0" class="empty-state">
          <Activity :size="38" />
          <h3>开始一次石化领域问答</h3>
          <p>规范、事务、报表和工具调用会由 Supervisor 自动分流。</p>
        </div>

        <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <div class="avatar">
            <User v-if="message.role === 'user'" :size="18" />
            <Bot v-else :size="18" />
          </div>

          <div class="message-main">
            <div class="message-meta">
              <span>{{ message.role === "user" ? currentUser.username : "PetroChat" }}</span>
              <span v-if="message.status === 'streaming'" class="inline-status">
                <Loader2 :size="14" class="spin" />
                生成中
              </span>
              <span v-if="message.status === 'error'" class="error-label">错误</span>
            </div>

            <div v-if="message.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(message.content)"></div>
            <p v-else class="plain-text">{{ message.content }}</p>

            <div v-if="message.events?.length" class="tool-events">
              <div v-for="event in message.events" :key="event.id" class="tool-event">
                <Wrench :size="15" />
                <div>
                  <strong>{{ event.kind === "call" ? "调用" : "结果" }} {{ event.name }}</strong>
                  <pre v-if="event.args">{{ JSON.stringify(event.args, null, 2) }}</pre>
                  <p v-if="event.preview">{{ event.preview }}</p>
                </div>
              </div>
            </div>

            <figure v-if="message.chart" class="chart-panel">
              <figcaption>
                <BarChart3 :size="16" />
                {{ message.chart.kind }} / {{ message.chart.rows }} 行
              </figcaption>
              <img :src="message.chart.uri" alt="查询结果图表" />
            </figure>

            <div v-if="message.citations?.length" class="citations">
              <span v-for="citation in message.citations" :key="citation">[{{ citation }}]</span>
            </div>
          </div>
        </article>
      </div>

      <form v-if="activeView === 'chat'" class="composer" @submit.prevent="sendQuestion">
        <textarea
          v-model="draft"
          rows="3"
          maxlength="2000"
          placeholder="输入问题，例如：统计各专业的事务数量"
          @keydown.enter.exact.prevent="sendQuestion"
        ></textarea>
        <div class="composer-actions">
          <span>{{ draft.length }}/2000</span>
          <button v-if="isStreaming" class="stop-button" type="button" title="停止生成" @click="stopStreaming">
            <CircleStop :size="17" />
            停止
          </button>
          <button v-else class="send-button" type="submit" :disabled="!canSend">
            <Send :size="17" />
            发送
          </button>
        </div>
      </form>

      <template v-else>
        <header class="topbar">
          <div>
            <h2>管理员工作台</h2>
            <p>用户权限、Agent 调用、工具事件、检索引用和报表侧信道。</p>
          </div>
          <div class="admin-actions">
            <button class="secondary-button" type="button" :disabled="!visibleLogs.length" @click="exportAdminLogs">
              <Download :size="16" />
              导出
            </button>
            <button class="danger-button" type="button" :disabled="!visibleLogs.length" @click="clearAdminLogs">
              <Trash2 :size="16" />
              清空
            </button>
          </div>
        </header>

        <div class="admin-body">
          <section class="admin-card-grid">
            <div v-for="card in adminCards" :key="card.label" class="admin-card">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
            </div>
          </section>

          <section class="metric-grid">
            <div class="metric-item">
              <span>总轮次</span>
              <strong>{{ adminStats.total }}</strong>
            </div>
            <div class="metric-item">
              <span>成功</span>
              <strong>{{ adminStats.success }}</strong>
            </div>
            <div class="metric-item">
              <span>异常</span>
              <strong>{{ adminStats.error }}</strong>
            </div>
            <div class="metric-item">
              <span>平均耗时</span>
              <strong>{{ formatDuration(adminStats.avgDuration) }}</strong>
            </div>
          </section>

          <section class="evaluation-panel">
            <div class="panel-heading">
              <div>
                <h3>{{ evaluation.title }}</h3>
                <span>{{ evaluation.generatedAt }} / {{ evaluation.source }}</span>
              </div>
              <div class="eval-heading-actions">
                <button class="tiny-button" type="button" title="刷新评估摘要" @click="refreshEvaluation">
                  <RefreshCw :size="14" :class="{ spin: isLoadingEvaluation }" />
                </button>
                <span class="status-pill done">Phase 5.8</span>
              </div>
            </div>

            <div class="eval-dataset">
              <div>
                <span>对话组</span>
                <strong>{{ evaluation.dataset.dialogues }}</strong>
              </div>
              <div>
                <span>总轮次</span>
                <strong>{{ evaluation.dataset.turns }}</strong>
              </div>
              <div>
                <span>SQL 期望</span>
                <strong>{{ evaluation.dataset.sqlExpectations }}</strong>
              </div>
              <div>
                <span>RAG 证据</span>
                <strong>{{ evaluation.dataset.ragEvidence }}</strong>
              </div>
              <div>
                <span>记忆状态</span>
                <strong>{{ evaluation.dataset.memoryStates }}</strong>
              </div>
            </div>

            <div class="eval-content">
              <div class="eval-column">
                <h4>合约指标</h4>
                <div class="eval-metric-list">
                  <div v-for="metric in evaluation.contractMetrics" :key="metric.label" class="eval-metric">
                    <span>{{ metric.label }}</span>
                    <strong>{{ metric.value }}</strong>
                    <small>{{ metric.detail }}</small>
                  </div>
                </div>
              </div>

              <div class="eval-column">
                <h4>Prediction 指标</h4>
                <div class="eval-metric-list">
                  <div v-for="metric in evaluation.predictionMetrics" :key="metric.label" class="eval-metric">
                    <span>{{ metric.label }}</span>
                    <strong>{{ metric.value }}</strong>
                    <small>{{ metric.detail }}</small>
                  </div>
                </div>
              </div>

              <div class="eval-column">
                <h4>场景分布</h4>
                <div class="scenario-list">
                  <div v-for="item in evaluation.scenarioCounts" :key="item.label">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <p v-if="evaluationError" class="eval-note warning">{{ evaluationError }}</p>
            <p class="eval-note">{{ evaluation.note }}</p>

            <div class="eval-run-section">
              <div class="eval-case-header">
                <div>
                  <h4>评估运行历史</h4>
                  <span>摘要文件、prediction 产物与 Trace 查询线索</span>
                </div>
                <strong>{{ evaluationRuns.length }} 批</strong>
              </div>
              <p v-if="evaluationRunError" class="eval-note warning">{{ evaluationRunError }}</p>

              <div v-if="evaluationRuns.length" class="eval-run-grid">
                <button
                  v-for="item in evaluationRuns"
                  :key="item.id"
                  class="eval-run-row"
                  :class="{ active: selectedEvaluationRun?.id === item.id }"
                  type="button"
                  @click="selectedEvaluationRunId = item.id"
                >
                  <span>
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.generatedAt }}</small>
                  </span>
                  <small class="status-pill done">{{ runStatusLabel(item.status) }}</small>
                  <span>
                    <small>{{ item.dataset.dialogues }} 组 / {{ item.dataset.turns }} 轮</small>
                    <small>SQL {{ item.metrics.sqlValidationRate }} · RAG {{ item.metrics.ragRecallAt5 }}</small>
                  </span>
                </button>
              </div>

              <div v-if="selectedEvaluationRun" class="eval-trace-panel">
                <div>
                  <span>产物</span>
                  <strong>
                    {{ selectedEvaluationRun.artifacts.summary ? "summary" : "-" }} /
                    {{ selectedEvaluationRun.artifacts.predictions ? "predictions" : "-" }} /
                    {{ selectedEvaluationRun.artifacts.markdown ? "markdown" : "-" }}
                  </strong>
                </div>
                <div>
                  <span>Trace 项目</span>
                  <strong>{{ selectedEvaluationRun.traceHint.project }}</strong>
                </div>
                <div>
                  <span>查询线索</span>
                  <strong>{{ selectedEvaluationRun.traceHint.query }}</strong>
                </div>
              </div>
            </div>

            <div class="eval-case-section">
              <div class="eval-case-header">
                <div>
                  <h4>失败与风险样例</h4>
                  <span>来自 prediction JSONL 的截断摘要</span>
                </div>
                <strong>{{ evaluationCases.length }} 条</strong>
              </div>
              <p v-if="evaluationCaseError" class="eval-note warning">{{ evaluationCaseError }}</p>

              <div v-if="evaluationCases.length" class="eval-case-grid">
                <div class="eval-case-list">
                  <button
                    v-for="item in evaluationCases"
                    :key="item.id"
                    class="eval-case-row"
                    :class="{ active: selectedEvaluationCase?.id === item.id }"
                    type="button"
                    @click="selectedEvaluationCaseId = item.id"
                  >
                    <span class="eval-case-top">
                      <small :class="['risk-pill', item.riskLevel]">{{ riskLabel(item.riskLevel) }}</small>
                      <strong>{{ item.dialogue }}</strong>
                    </span>
                    <span class="eval-case-question">{{ item.questionSummary }}</span>
                    <span class="eval-case-bottom">
                      <small>{{ item.scenario }}</small>
                      <small>{{ routeLabel(item.route) }}</small>
                      <small>{{ formatDuration(item.latencyMs) }}</small>
                    </span>
                  </button>
                </div>

                <div v-if="selectedEvaluationCase" class="eval-case-detail">
                  <div class="eval-case-detail-head">
                    <div>
                      <h4>{{ selectedEvaluationCase.dialogue }}</h4>
                      <span>{{ selectedEvaluationCase.mode }} / {{ selectedEvaluationCase.status }}</span>
                    </div>
                    <small :class="['risk-pill', selectedEvaluationCase.riskLevel]">
                      {{ riskLabel(selectedEvaluationCase.riskLevel) }}
                    </small>
                  </div>
                  <div class="eval-reason-list">
                    <span v-for="reason in selectedEvaluationCase.reasons" :key="reason">{{ reason }}</span>
                  </div>
                  <dl class="eval-case-fields">
                    <div>
                      <dt>问题摘要</dt>
                      <dd>{{ selectedEvaluationCase.questionSummary || "-" }}</dd>
                    </div>
                    <div>
                      <dt>回答摘要</dt>
                      <dd>{{ selectedEvaluationCase.answerSummary || "-" }}</dd>
                    </div>
                    <div>
                      <dt>SQL 摘要</dt>
                      <dd>
                        {{ selectedEvaluationCase.sqlSummary.present ? "已生成" : "未生成" }} /
                        {{ selectedEvaluationCase.sqlSummary.valid ? "校验通过" : "需复核" }} /
                        {{ selectedEvaluationCase.sqlSummary.tables.join(", ") || "无表信息" }}
                      </dd>
                    </div>
                    <div>
                      <dt>检索摘要</dt>
                      <dd>
                        {{ selectedEvaluationCase.retrievalSummary.count }} 条 /
                        {{ selectedEvaluationCase.retrievalSummary.sources.join(", ") || "无来源摘要" }}
                      </dd>
                    </div>
                    <div>
                      <dt>Trace 查询</dt>
                      <dd>{{ selectedEvaluationCase.traceHint.query }}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>
          </section>

          <section class="admin-content">
            <div class="log-list">
              <div class="panel-heading">
                <h3>问答记录</h3>
                <span>{{ visibleLogs.length }} 条</span>
              </div>

              <button
                v-for="item in visibleLogs"
                :key="item.id"
                class="log-row"
                :class="{ active: selectedLog?.id === item.id }"
                type="button"
                @click="selectedLogId = item.id"
              >
                <span class="log-row-top">
                  <strong>{{ routeLabel(item.route) }}</strong>
                  <small>{{ formatTime(item.createdAt) }}</small>
                </span>
                <span class="log-question">{{ item.questionSummary }}</span>
                <span class="log-row-bottom">
                  <small :class="['status-pill', item.status]">{{ item.status === "done" ? "完成" : "异常" }}</small>
                  <small>{{ item.username }}</small>
                  <small>{{ formatDuration(item.durationMs) }}</small>
                </span>
              </button>

              <div v-if="!visibleLogs.length" class="admin-empty">
                <ClipboardList :size="34" />
                <p>暂无问答记录。</p>
              </div>
            </div>

            <article class="log-detail">
              <template v-if="selectedLog">
                <div class="panel-heading">
                  <h3>轮次详情</h3>
                  <span>{{ routeLabel(selectedLog.route) }}</span>
                </div>

                <dl class="detail-grid">
                  <div>
                    <dt>状态</dt>
                    <dd>{{ selectedLog.status === "done" ? "完成" : "异常" }}</dd>
                  </div>
                  <div>
                    <dt>耗时</dt>
                    <dd>{{ formatDuration(selectedLog.durationMs) }}</dd>
                  </div>
                  <div>
                    <dt>引用数</dt>
                    <dd>{{ selectedLog.citationCount }}</dd>
                  </div>
                  <div>
                    <dt>工具事件</dt>
                    <dd>{{ selectedLog.eventCount }}</dd>
                  </div>
                </dl>

                <section class="detail-section">
                  <h4>用户问题</h4>
                  <p>{{ selectedLog.question }}</p>
                </section>

                <section class="detail-section">
                  <h4>Agent 回答</h4>
                  <div class="markdown-body" v-html="renderMarkdown(selectedLog.answer)"></div>
                </section>

                <section v-if="selectedLog.events?.length" class="detail-section">
                  <h4>工具事件</h4>
                  <div class="tool-events">
                    <div v-for="event in selectedLog.events" :key="event.id" class="tool-event">
                      <Wrench :size="15" />
                      <div>
                        <strong>{{ event.kind === "call" ? "调用" : "结果" }} {{ event.name }}</strong>
                        <pre v-if="event.args">{{ JSON.stringify(event.args, null, 2) }}</pre>
                        <p v-if="event.preview">{{ event.preview }}</p>
                      </div>
                    </div>
                  </div>
                </section>

                <section v-if="selectedLog.chart" class="detail-section">
                  <h4>报表图</h4>
                  <figure class="chart-panel">
                    <figcaption>
                      <BarChart3 :size="16" />
                      {{ selectedLog.chart.kind }} / {{ selectedLog.chart.rows }} 行
                    </figcaption>
                    <img :src="selectedLog.chart.uri" alt="管理员查看的查询结果图表" />
                  </figure>
                </section>

                <div v-if="selectedLog.citations?.length" class="citations">
                  <span v-for="citation in selectedLog.citations" :key="citation">[{{ citation }}]</span>
                </div>
              </template>

              <div v-else class="admin-empty">
                <ClipboardList :size="34" />
                <p>完成一次对话后，这里会显示详情。</p>
              </div>
            </article>
          </section>
        </div>
      </template>
    </section>
  </main>
</template>
