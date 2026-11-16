import { agentApi, APIError } from "/api.js";

/**
 * 页面唯一状态源。当前会话中的 messages / trace 均来自 Python Session，
 * 前端不复制 ReAct 决策，也不持久化对话内容。
 */
const state = {
  health: null,
  tools: [],
  sessions: [],
  currentSession: null,
  loadingSession: true,
  sending: false,
  creating: false,
  pendingMessage: "",
  liveTrace: [],
  inspectorTab: "trace",
};

const ACTIVE_SESSION_KEY = "minimal-agent:active-session";
const $ = (selector) => document.querySelector(selector);
const dom = {
  sessionList: $("#session-list"),
  messageList: $("#message-list"),
  messageScroll: $("#message-scroll"),
  sessionTitle: $("#session-title"),
  sessionCount: $("#session-count"),
  traceList: $("#trace-list"),
  traceCount: $("#trace-count"),
  toolList: $("#tool-list"),
  toolsCount: $("#tools-count"),
  input: $("#message-input"),
  form: $("#chat-form"),
  send: $("#send-button"),
  characterCount: $("#character-count"),
  newSession: $("#new-session-button"),
  refreshSessions: $("#refresh-sessions-button"),
  reset: $("#reset-button"),
  resetDialog: $("#reset-dialog"),
  confirmReset: $("#confirm-reset-button"),
  health: $("#health-button"),
  healthLabel: $("#health-label"),
  modelLabel: $("#model-label"),
  configuration: $("#configuration-banner"),
  error: $("#error-banner"),
  errorMessage: $("#error-message"),
  backdrop: $("#drawer-backdrop"),
  toast: $("#toast"),
  emptyTemplate: $("#empty-state-template"),
};

/** 创建安全文本节点；模型与工具输出永远不通过 innerHTML 注入。 */
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function readActiveSession() {
  try { return sessionStorage.getItem(ACTIVE_SESSION_KEY); } catch { return null; }
}

function saveActiveSession(sessionId) {
  try {
    if (sessionId) sessionStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
    else sessionStorage.removeItem(ACTIVE_SESSION_KEY);
  } catch { /* 禁用存储时不影响本次对话。 */ }
}

function showError(error) {
  dom.errorMessage.textContent = error instanceof Error ? error.message : String(error);
  dom.error.hidden = false;
}

function clearError() {
  dom.error.hidden = true;
  dom.errorMessage.textContent = "";
}

let toastTimer;
function announce(message) {
  clearTimeout(toastTimer);
  dom.toast.textContent = message;
  dom.toast.hidden = false;
  toastTimer = setTimeout(() => { dom.toast.hidden = true; }, 2600);
}

function summaryFromSession(session) {
  return {
    id: session.id,
    messages: session.message_count,
    turns: session.turns,
    created: session.created,
    updated: session.updated,
  };
}

function upsertSessionSummary(session) {
  const summary = summaryFromSession(session);
  state.sessions = [summary, ...state.sessions.filter((item) => item.id !== session.id)]
    .sort((a, b) => b.updated.localeCompare(a.updated));
}

function renderHealth() {
  dom.health.classList.remove("is-online", "is-warning", "is-offline");
  if (!state.health) {
    dom.healthLabel.textContent = "正在连接";
    dom.modelLabel.textContent = "本地服务";
    dom.configuration.hidden = true;
    return;
  }
  if (state.health.status !== "ok") {
    dom.health.classList.add("is-offline");
    dom.healthLabel.textContent = "服务离线";
    dom.modelLabel.textContent = "连接失败";
    dom.configuration.hidden = true;
    return;
  }
  const configured = state.health.llm_configured;
  dom.health.classList.add(configured ? "is-online" : "is-warning");
  dom.healthLabel.textContent = configured ? "Agent 就绪" : "待配置 Key";
  dom.modelLabel.textContent = state.health.model || "unknown";
  dom.configuration.hidden = configured;
}

function renderSessions() {
  const fragment = document.createDocumentFragment();
  if (!state.sessions.length) {
    fragment.append(element("p", "session-empty", "还没有会话，点击上方开始。"));
  }

  for (const session of state.sessions) {
    const button = element("button", "session-item");
    button.type = "button";
    button.dataset.sessionId = session.id;
    button.disabled = state.sending || state.creating;
    if (session.id === state.currentSession?.id) {
      button.classList.add("is-active");
      button.setAttribute("aria-current", "page");
    }
    button.append(element("span", "session-item__icon", session.id === state.currentSession?.id ? "●" : "#"));
    const body = element("span", "session-item__body");
    body.append(element("span", "session-item__name", session.id));
    body.append(element("span", "session-item__meta", `${session.turns} 轮 · ${session.updated.slice(5, 16)}`));
    button.append(body);
    fragment.append(button);
  }
  dom.sessionList.replaceChildren(fragment);
}

function renderSessionHeader() {
  const session = state.currentSession;
  dom.sessionTitle.textContent = session?.id || "准备工作台";
  dom.sessionCount.textContent = `${session?.message_count || 0} 条消息`;
  dom.reset.disabled = !session || state.sending || state.loadingSession;
}

function appendUserMessage(container, content, pending = false) {
  const article = element("article", `message message--user${pending ? " is-pending" : ""}`);
  const body = element("div", "message__body");
  body.append(element("span", "message__label", pending ? "你 · 正在发送" : "你"));
  body.append(element("p", "message__content", content));
  article.append(body);
  container.append(article);
}

function appendAssistantMessage(container, content) {
  const article = element("article", "message message--assistant");
  article.append(element("span", "message__avatar", "A"));
  const body = element("div", "message__body");
  body.append(element("span", "message__label", "MINIMAL AGENT"));
  body.append(element("p", "message__content", content));
  article.append(body);
  container.append(article);
}

function appendToolMessage(container, summary, content, label) {
  const wrapper = element("div", "tool-message");
  const details = element("details", "tool-card");
  const summaryNode = element("summary", "", summary);
  summaryNode.append(element("span", "", label));
  details.append(summaryNode, element("pre", "", content));
  wrapper.append(details);
  container.append(wrapper);
}

function appendTypingIndicator(container) {
  const row = element("div", "typing-row");
  row.append(element("span", "message__avatar", "A"));
  const dots = element("span", "typing-dots");
  dots.setAttribute("aria-hidden", "true");
  dots.append(element("i"), element("i"), element("i"));
  row.append(dots, element("span", "", "Agent 正在思考并调用工具"));
  container.append(row);
}

function renderMessages({ scroll = false } = {}) {
  const fragment = document.createDocumentFragment();
  const session = state.currentSession;

  if (state.loadingSession) {
    const loading = element("div", "initial-loading");
    loading.append(element("span", "loader"), element("p", "", "正在载入会话"));
    fragment.append(loading);
  } else if (!session?.messages.length && !state.pendingMessage) {
    fragment.append(dom.emptyTemplate.content.cloneNode(true));
  } else {
    for (const message of session?.messages || []) {
      if (message.role === "user") {
        appendUserMessage(fragment, message.content);
      } else if (message.role === "assistant" && message.content) {
        appendAssistantMessage(fragment, message.content);
      } else if (message.role === "assistant" && message.tool_calls?.length) {
        for (const call of message.tool_calls) {
          appendToolMessage(
            fragment,
            `Agent 调用 ${call.name || "工具"}`,
            JSON.stringify(call.arguments || {}, null, 2),
            "PARAMETERS",
          );
        }
      } else if (message.role === "tool") {
        appendToolMessage(fragment, "工具执行结果", message.content || "(空结果)", "RESULT");
      }
    }
    if (state.pendingMessage) appendUserMessage(fragment, state.pendingMessage, true);
    if (state.sending) appendTypingIndicator(fragment);
  }

  dom.messageList.replaceChildren(fragment);
  dom.messageScroll.setAttribute("aria-busy", String(state.loadingSession || state.sending));
  if (scroll) requestAnimationFrame(() => { dom.messageScroll.scrollTop = dom.messageScroll.scrollHeight; });
}

function emptyPanel(title, description) {
  const empty = element("div", "panel-empty");
  empty.append(element("strong", "", title), element("p", "", description));
  return empty;
}

function renderTrace() {
  // 流式期间先展示实时推送的 trace，结束后以 session 中的完整轨迹为准。
  const trace = state.liveTrace.length ? state.liveTrace : (state.currentSession?.trace || []);
  dom.traceCount.textContent = trace.length;
  const fragment = document.createDocumentFragment();
  if (!trace.length) fragment.append(emptyPanel("暂无执行轨迹", "发送第一条消息后，这里会显示 ReAct 运行过程。"));

  trace.forEach((entry, index) => {
    if (/^=+$/.test(entry.trim())) return;
    const item = element("li", "trace-entry");
    if (entry.includes("Step")) item.classList.add("is-step");
    if (entry.includes("Tool call")) item.classList.add("is-tool");
    if (/失败|错误|超时/.test(entry)) item.classList.add("is-error");
    item.append(element("span", "trace-entry__number", String(index + 1).padStart(2, "0")));
    item.append(element("span", "trace-entry__content", entry));
    fragment.append(item);
  });
  dom.traceList.replaceChildren(fragment);
}

function renderTools() {
  dom.toolsCount.textContent = state.tools.length;
  const fragment = document.createDocumentFragment();
  if (!state.tools.length) fragment.append(emptyPanel("工具列表不可用", "请检查服务连接后刷新页面。"));
  for (const tool of state.tools) {
    const details = element("details", "tool-schema");
    const summary = element("summary");
    summary.append(element("strong", "", tool.name), element("span", "", "SCHEMA"));
    const body = element("div", "tool-schema__body");
    body.append(element("p", "", tool.description || "暂无描述"));
    body.append(element("pre", "", JSON.stringify(tool.parameters || {}, null, 2)));
    details.append(summary, body);
    fragment.append(details);
  }
  dom.toolList.replaceChildren(fragment);
}

function resizeComposer() {
  dom.input.style.height = "auto";
  dom.input.style.height = `${Math.min(dom.input.scrollHeight, 160)}px`;
}

function updateComposer() {
  const length = dom.input.value.length;
  dom.characterCount.textContent = `${length} / 4000`;
  dom.send.disabled = state.sending || state.loadingSession || !state.currentSession || !dom.input.value.trim();
  dom.send.classList.toggle("is-loading", state.sending);
  dom.send.querySelector("span").textContent = state.sending ? "运行中" : "发送";
  dom.input.disabled = state.sending || state.loadingSession || !state.currentSession;
  dom.newSession.disabled = state.sending || state.creating;
  dom.refreshSessions.disabled = state.sending || state.creating;
  dom.reset.disabled = !state.currentSession || state.sending || state.loadingSession;
}

function renderWorkspace(options) {
  renderSessions();
  renderSessionHeader();
  renderMessages(options);
  renderTrace();
  updateComposer();
}

async function refreshHealth({ reportError = false } = {}) {
  dom.health.disabled = true;
  try {
    state.health = await agentApi.health();
  } catch (error) {
    state.health = { status: "offline" };
    if (reportError) showError(error);
  } finally {
    dom.health.disabled = false;
    renderHealth();
  }
}

async function refreshSessions({ reportError = true } = {}) {
  dom.refreshSessions.disabled = true;
  try {
    const payload = await agentApi.listSessions();
    state.sessions = payload.sessions;
    renderSessions();
    return true;
  } catch (error) {
    if (reportError) showError(error);
    return false;
  } finally {
    updateComposer();
  }
}

async function selectSession(sessionId, { focus = true } = {}) {
  if (state.sending || state.loadingSession && state.currentSession?.id === sessionId) return;
  clearError();
  state.loadingSession = true;
  state.currentSession = null;
  renderWorkspace();
  closeDrawer();
  try {
    const { session } = await agentApi.getSession(sessionId);
    state.currentSession = session;
    saveActiveSession(session.id);
    if (focus) dom.input.focus();
  } catch (error) {
    saveActiveSession(null);
    showError(error);
  } finally {
    state.loadingSession = false;
    renderWorkspace({ scroll: true });
  }
}

async function createNewSession({ focus = true } = {}) {
  if (state.creating || state.sending) return null;
  clearError();
  state.creating = true;
  updateComposer();
  try {
    const { session } = await agentApi.createSession();
    state.currentSession = session;
    upsertSessionSummary(session);
    saveActiveSession(session.id);
    renderWorkspace({ scroll: true });
    closeDrawer();
    if (focus) dom.input.focus();
    announce("新会话已创建");
    return session;
  } catch (error) {
    showError(error);
    return null;
  } finally {
    state.creating = false;
    updateComposer();
    renderSessions();
  }
}

async function resetCurrentSession() {
  const sessionId = state.currentSession?.id;
  if (!sessionId || state.sending) return;
  dom.confirmReset.disabled = true;
  try {
    const { session } = await agentApi.resetSession(sessionId);
    state.currentSession = session;
    upsertSessionSummary(session);
    renderWorkspace({ scroll: true });
    dom.resetDialog.close();
    announce("对话已清空，执行轨迹已保留");
    dom.input.focus();
  } catch (error) {
    showError(error);
    dom.resetDialog.close();
  } finally {
    dom.confirmReset.disabled = false;
  }
}

async function sendCurrentMessage() {
  const message = dom.input.value.trim();
  if (!message || state.sending || state.loadingSession) return;
  if (!state.currentSession) {
    const session = await createNewSession({ focus: false });
    if (!session) return;
  }

  const sessionId = state.currentSession.id;
  clearError();
  state.sending = true;
  state.pendingMessage = message;
  state.liveTrace = [];
  dom.input.value = "";
  resizeComposer();
  renderWorkspace({ scroll: true });

  let streamedSession = null;
  try {
    await agentApi.sendMessageStream(sessionId, message, {
      onEvent: (event, data) => {
        if (event === "trace" && data?.entry) {
          state.liveTrace.push(data.entry);
          renderTrace();
        } else if (event === "done" && data?.session) {
          streamedSession = data.session;
          state.currentSession = data.session;
          state.pendingMessage = "";
          upsertSessionSummary(data.session);
        } else if (event === "error") {
          throw new APIError(data?.error?.message || "流式对话失败", data?.error || {});
        }
      },
    });

    if (streamedSession && window.matchMedia("(max-width: 1180px)").matches) {
      announce("回答已生成，可打开运行检查器查看轨迹");
    }
  } catch (error) {
    state.pendingMessage = "";
    dom.input.value = message;
    showError(error);
  } finally {
    state.sending = false;
    state.liveTrace = [];
    resizeComposer();
    renderWorkspace({ scroll: true });
    dom.input.focus();
  }
}

function switchInspectorTab(tab, { focus = false } = {}) {
  state.inspectorTab = tab;
  document.querySelectorAll("[data-inspector-tab]").forEach((button) => {
    const selected = button.dataset.inspectorTab === tab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    if (selected && focus) button.focus();
  });
  $("#trace-panel").hidden = tab !== "trace";
  $("#tools-panel").hidden = tab !== "tools";
}

function openDrawer(name, trigger) {
  closeDrawer({ restoreFocus: false });
  document.body.dataset.drawer = name;
  document.body.dataset.drawerTrigger = trigger.id;
  dom.backdrop.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  const drawer = name === "sessions" ? $("#session-sidebar") : $("#inspector");
  drawer.querySelector("button:not(:disabled)")?.focus();
}

function closeDrawer({ restoreFocus = true } = {}) {
  const triggerId = document.body.dataset.drawerTrigger;
  document.querySelectorAll(".topbar__actions [aria-expanded]").forEach((button) => button.setAttribute("aria-expanded", "false"));
  delete document.body.dataset.drawer;
  delete document.body.dataset.drawerTrigger;
  dom.backdrop.hidden = true;
  if (restoreFocus && triggerId) document.getElementById(triggerId)?.focus();
}

function trapDrawerFocus(event) {
  const name = document.body.dataset.drawer;
  if (!name || event.key !== "Tab") return;
  const drawer = name === "sessions" ? $("#session-sidebar") : $("#inspector");
  const focusable = [...drawer.querySelectorAll("button:not(:disabled), summary, a[href], textarea:not(:disabled)")]
    .filter((node) => node.getClientRects().length);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function bindEvents() {
  dom.form.addEventListener("submit", (event) => { event.preventDefault(); sendCurrentMessage(); });
  dom.input.addEventListener("input", () => { resizeComposer(); updateComposer(); });
  dom.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendCurrentMessage();
    }
  });
  dom.messageList.addEventListener("click", (event) => {
    const prompt = event.target.closest("[data-prompt]");
    if (!prompt || state.sending) return;
    dom.input.value = prompt.dataset.prompt;
    resizeComposer();
    updateComposer();
    dom.input.focus();
  });
  dom.sessionList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-session-id]");
    if (button && !button.disabled) selectSession(button.dataset.sessionId);
  });
  dom.newSession.addEventListener("click", () => createNewSession());
  dom.refreshSessions.addEventListener("click", async () => {
    if (await refreshSessions()) announce("会话列表已刷新");
  });
  dom.reset.addEventListener("click", () => dom.resetDialog.showModal());
  dom.confirmReset.addEventListener("click", resetCurrentSession);
  dom.health.addEventListener("click", async () => {
    await refreshHealth({ reportError: true });
    if (state.health.status === "ok") announce("服务状态已更新");
  });
  $("#dismiss-error-button").addEventListener("click", clearError);
  $("#sessions-toggle").addEventListener("click", (event) => openDrawer("sessions", event.currentTarget));
  $("#inspector-toggle").addEventListener("click", (event) => openDrawer("inspector", event.currentTarget));
  document.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", () => closeDrawer()));
  dom.backdrop.addEventListener("click", () => closeDrawer());
  document.querySelectorAll("[data-inspector-tab]").forEach((button) => {
    button.addEventListener("click", () => switchInspectorTab(button.dataset.inspectorTab));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      switchInspectorTab(state.inspectorTab === "trace" ? "tools" : "trace", { focus: true });
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.dataset.drawer) closeDrawer();
    trapDrawerFocus(event);
    if (event.key.toLowerCase() === "n" && !event.ctrlKey && !event.metaKey && !event.altKey
      && !["TEXTAREA", "INPUT"].includes(document.activeElement.tagName) && !dom.resetDialog.open) {
      event.preventDefault();
      createNewSession();
    }
  });
}

/** 首屏并行加载非阻塞信息，再恢复最近会话；失败时保留可用模块。 */
async function initialize() {
  bindEvents();
  switchInspectorTab("trace");
  resizeComposer();
  updateComposer();

  const [healthResult, toolsResult, sessionsResult] = await Promise.allSettled([
    agentApi.health(),
    agentApi.tools(),
    agentApi.listSessions(),
  ]);

  state.health = healthResult.status === "fulfilled" ? healthResult.value : { status: "offline" };
  state.tools = toolsResult.status === "fulfilled" ? toolsResult.value.tools : [];
  renderHealth();
  renderTools();

  if (sessionsResult.status === "rejected") {
    state.loadingSession = false;
    showError(sessionsResult.reason);
    renderWorkspace();
    return;
  }

  state.sessions = sessionsResult.value.sessions;
  const savedId = readActiveSession();
  const initial = state.sessions.find((session) => session.id === savedId) || state.sessions[0];
  if (initial) await selectSession(initial.id, { focus: false });
  else {
    state.loadingSession = false;
    await createNewSession({ focus: false });
  }
}

initialize();
