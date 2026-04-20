const DEFAULT_CONFIG = {
  serverUrl: "http://127.0.0.1:8765",
  token: "local-bridge-quickstart-2026",
  clientId: "",
  pollIntervalMs: 2000,
  heartbeatIntervalMs: 8000
};

const BRIDGE_CAPABILITIES = {
  background_commands: ["navigate", "new_tab", "reload", "activate_tab", "close_tab", "screenshot"],
  content_commands: [
    "back",
    "forward",
    "get_page_url",
    "context_click",
    "click_text",
    "clear_editable",
    "click",
    "fill",
    "focus",
    "extract_text",
    "get_html",
    "get_attribute",
    "wait_selector",
    "scroll",
    "scroll_by",
    "wheel",
    "run_script",
    "press_key"
  ]
};

let pollTimer = null;
let heartbeatTimer = null;

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(values) {
  return new Promise((resolve) => chrome.storage.local.set(values, resolve));
}

function normalizeServerUrl(url) {
  return (url || DEFAULT_CONFIG.serverUrl).replace(/\/+$/, "");
}

async function getConfig() {
  const raw = await storageGet(Object.keys(DEFAULT_CONFIG));
  const cfg = { ...DEFAULT_CONFIG, ...raw };
  if (!cfg.clientId) {
    cfg.clientId = `client-${crypto.randomUUID()}`;
    await storageSet({ clientId: cfg.clientId });
  }
  cfg.serverUrl = normalizeServerUrl(cfg.serverUrl);
  return cfg;
}

async function apiRequest(config, path, method = "GET", body = null) {
  const response = await fetch(`${normalizeServerUrl(config.serverUrl)}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Access-Token": config.token
    },
    body: body ? JSON.stringify(body) : undefined
  });

  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    payload = { ok: false, error: `Invalid JSON: ${String(error)}` };
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${payload.error || text || response.statusText}`);
  }
  return payload;
}

function tabsQuery(query) {
  return new Promise((resolve, reject) => {
    chrome.tabs.query(query, (tabs) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(tabs || []);
    });
  });
}

function tabsGet(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.get(tabId, (tab) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(tab || null);
    });
  });
}

function tabsUpdate(tabId, updateProperties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.update(tabId, updateProperties, (tab) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(tab || null);
    });
  });
}

function tabsCreate(createProperties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create(createProperties, (tab) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(tab || null);
    });
  });
}

function tabsReload(tabId, reloadProperties = {}) {
  return new Promise((resolve, reject) => {
    chrome.tabs.reload(tabId, reloadProperties, () => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(true);
    });
  });
}

function tabsRemove(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.remove(tabId, () => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(true);
    });
  });
}

function windowsUpdate(windowId, updateInfo) {
  return new Promise((resolve, reject) => {
    chrome.windows.update(windowId, updateInfo, (window) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(window || null);
    });
  });
}

function tabsSendMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(response);
    });
  });
}

function tabsExecuteScript(tabId, files) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript({ target: { tabId }, files }, (results) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(results || []);
    });
  });
}

async function sendCommandToTabWithAutoInject(tabId, command) {
  try {
    const response = await tabsSendMessage(tabId, {
      type: "site-control-command",
      command
    });
    return response;
  } catch (error) {
    const message = String(error?.message || error || "");
    const recoverable =
      message.includes("Receiving end does not exist") ||
      message.includes("Could not establish connection") ||
      message.includes("The message port closed before a response was received");
    if (!recoverable) {
      throw error;
    }

    await tabsExecuteScript(tabId, ["content.js"]);
    const retryResponse = await tabsSendMessage(tabId, {
      type: "site-control-command",
      command
    });
    return retryResponse;
  }
}

function captureVisibleTab(windowId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(dataUrl);
    });
  });
}

async function collectTabs() {
  const tabs = await tabsQuery({});
  return tabs.map((tab) => ({
    id: tab.id,
    windowId: tab.windowId,
    active: Boolean(tab.active),
    title: tab.title || "",
    url: tab.url || ""
  }));
}

async function resolveTargetTab(target) {
  const safeTarget = target || {};

  if (Number.isInteger(safeTarget.tab_id)) {
    try {
      return await tabsGet(safeTarget.tab_id);
    } catch {
      return null;
    }
  }

  if (typeof safeTarget.url_pattern === "string" && safeTarget.url_pattern.trim()) {
    const allTabs = await tabsQuery({});
    const pattern = safeTarget.url_pattern.trim();
    const found = allTabs.find((tab) => (tab.url || "").includes(pattern));
    if (found) {
      return found;
    }
  }

  if (safeTarget.active !== false) {
    const activeTabs = await tabsQuery({ active: true, lastFocusedWindow: true });
    if (activeTabs.length > 0) {
      return activeTabs[0];
    }
  }

  const tabs = await tabsQuery({});
  return tabs.length ? tabs[0] : null;
}

async function sendHeartbeat(config) {
  const tabs = await collectTabs();
  const payload = {
    client_id: config.clientId,
    extension_version: chrome.runtime.getManifest().version,
    user_agent: navigator.userAgent,
    tabs,
    meta: {
      extension: "site-control-bridge",
      platform: navigator.platform,
      capabilities: BRIDGE_CAPABILITIES
    }
  };

  const response = await apiRequest(config, "/api/clients/heartbeat", "POST", payload);
  await storageSet({
    lastHeartbeatAt: new Date().toISOString(),
    lastHeartbeatError: "",
    lastHeartbeatResponse: response
  });
}

async function postResult(config, commandId, result) {
  const payload = {
    client_id: config.clientId,
    ok: Boolean(result.ok),
    status: result.status || (result.ok ? "completed" : "failed"),
    data: result.data ?? null,
    error: result.error ?? null,
    logs: result.logs || []
  };

  await apiRequest(config, `/api/commands/${encodeURIComponent(commandId)}/result`, "POST", payload);

  await storageSet({
    lastCommandId: commandId,
    lastCommandAt: new Date().toISOString(),
    lastCommandStatus: payload.status,
    lastCommandError: payload.error ? JSON.stringify(payload.error) : ""
  });
}

async function executeCommandEnvelope(envelope) {
  const command = envelope.command || {};
  const type = command.type;
  const target = envelope.target || {};

  if (!type) {
    return { ok: false, status: "failed", error: { message: "command.type is required" } };
  }

  if (type === "navigate") {
    const tab = await resolveTargetTab(target);
    if (!tab || !Number.isInteger(tab.id)) {
      return { ok: false, status: "failed", error: { message: "No target tab found" } };
    }
    if (!command.url) {
      return { ok: false, status: "failed", error: { message: "navigate requires command.url" } };
    }

    const updated = await tabsUpdate(tab.id, { url: command.url });
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: updated?.id,
        url: updated?.url || command.url
      }
    };
  }

  if (type === "new_tab") {
    const created = await tabsCreate({
      url: command.url || "about:blank",
      active: command.active !== false
    });
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: created?.id ?? null,
        windowId: created?.windowId ?? null,
        url: created?.url || command.url || "about:blank",
        active: Boolean(created?.active)
      }
    };
  }

  if (type === "screenshot") {
    const tab = await resolveTargetTab(target);
    if (!tab || !Number.isInteger(tab.windowId)) {
      return { ok: false, status: "failed", error: { message: "No target tab for screenshot" } };
    }
    const imageDataUrl = await captureVisibleTab(tab.windowId);
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: tab.id,
        imageDataUrl
      }
    };
  }

  const tab = await resolveTargetTab(target);
  if (!tab || !Number.isInteger(tab.id)) {
    return { ok: false, status: "failed", error: { message: "No target tab found" } };
  }

  if (type === "reload") {
    await tabsReload(tab.id, { bypassCache: Boolean(command.ignore_cache) });
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: tab.id,
        reloaded: true
      }
    };
  }

  if (type === "activate_tab") {
    const updated = await tabsUpdate(tab.id, { active: true });
    if (Number.isInteger(updated?.windowId)) {
      await windowsUpdate(updated.windowId, { focused: true });
    }
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: updated?.id ?? tab.id,
        active: true
      }
    };
  }

  if (type === "close_tab") {
    await tabsRemove(tab.id);
    return {
      ok: true,
      status: "completed",
      data: {
        tabId: tab.id,
        closed: true
      }
    };
  }

  try {
    const response = await sendCommandToTabWithAutoInject(tab.id, command);

    if (!response) {
      return { ok: false, status: "failed", error: { message: "No response from content script" } };
    }

    return {
      ok: Boolean(response.ok),
      status: response.ok ? "completed" : "failed",
      data: response.data,
      error: response.error || null
    };
  } catch (error) {
    return {
      ok: false,
      status: "failed",
      error: {
        message: String(error?.message || error),
        hint: "Check tab permissions and whether this page allows content scripts"
      }
    };
  }
}

async function pollOnce(reason = "timer") {
  const config = await getConfig();
  if (!config.token) {
    await storageSet({
      lastPollAt: new Date().toISOString(),
      lastPollError: "Не задан токен в настройках расширения",
      lastPollReason: reason
    });
    return;
  }

  try {
    const query = new URLSearchParams({ client_id: config.clientId }).toString();
    const response = await apiRequest(config, `/api/commands/next?${query}`, "GET");

    await storageSet({
      lastPollAt: new Date().toISOString(),
      lastPollError: "",
      lastPollReason: reason
    });

    const envelope = response.command;
    if (!envelope) {
      return;
    }

    const result = await executeCommandEnvelope(envelope);
    await postResult(config, envelope.id, result);
  } catch (error) {
    await storageSet({
      lastPollAt: new Date().toISOString(),
      lastPollError: String(error?.message || error),
      lastPollReason: reason
    });
  }
}

async function heartbeatOnce(reason = "timer") {
  const config = await getConfig();
  if (!config.token) {
    await storageSet({
      lastHeartbeatAt: new Date().toISOString(),
      lastHeartbeatError: "Не задан токен в настройках расширения",
      lastHeartbeatReason: reason
    });
    return;
  }

  try {
    await sendHeartbeat(config);
    await storageSet({
      lastHeartbeatAt: new Date().toISOString(),
      lastHeartbeatError: "",
      lastHeartbeatReason: reason
    });
  } catch (error) {
    await storageSet({
      lastHeartbeatAt: new Date().toISOString(),
      lastHeartbeatError: String(error?.message || error),
      lastHeartbeatReason: reason
    });
  }
}

async function startTimers() {
  const config = await getConfig();
  const pollIntervalMs = Math.max(500, Number(config.pollIntervalMs || DEFAULT_CONFIG.pollIntervalMs));
  const heartbeatIntervalMs = Math.max(
    1000,
    Number(config.heartbeatIntervalMs || DEFAULT_CONFIG.heartbeatIntervalMs)
  );

  if (!pollTimer) {
    pollTimer = setInterval(() => {
      pollOnce("setInterval").catch(() => {});
    }, pollIntervalMs);
  }

  if (!heartbeatTimer) {
    heartbeatTimer = setInterval(() => {
      heartbeatOnce("setInterval").catch(() => {});
    }, heartbeatIntervalMs);
  }

  chrome.alarms.create("site-control-poll", { periodInMinutes: 1 });
}

function stopTimers() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await getConfig();
  await startTimers();
  await heartbeatOnce("onInstalled");
  await pollOnce("onInstalled");
});

chrome.runtime.onStartup.addListener(async () => {
  await getConfig();
  await startTimers();
  await heartbeatOnce("onStartup");
  await pollOnce("onStartup");
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "site-control-poll") {
    pollOnce("alarm").catch(() => {});
    heartbeatOnce("alarm").catch(() => {});
  }
});

chrome.runtime.onSuspend.addListener(() => {
  stopTimers();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return;
  }

  if (message.type === "poll_now") {
    pollOnce("popup").then(() => sendResponse({ ok: true })).catch((error) => {
      sendResponse({ ok: false, error: String(error?.message || error) });
    });
    return true;
  }

  if (message.type === "heartbeat_now") {
    heartbeatOnce("popup").then(() => sendResponse({ ok: true })).catch((error) => {
      sendResponse({ ok: false, error: String(error?.message || error) });
    });
    return true;
  }

  if (message.type === "restart_timers") {
    stopTimers();
    startTimers()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error?.message || error) }));
    return true;
  }
});

startTimers().catch(() => {});
