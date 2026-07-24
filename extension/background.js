const DEFAULT_CONFIG = {
  serverUrl: "http://127.0.0.1:8765",
  token: "local-bridge-quickstart-2026",
  clientId: "",
  pollIntervalMs: 2000,
  heartbeatIntervalMs: 8000
};

const PROTOCOL_VERSION = "2.0";
const RESULT_OUTBOX_KEY = "pendingCommandResultsV2";
const BRIDGE_CAPABILITIES = {
  protocol_version: PROTOCOL_VERSION,
  background_commands: [
    "navigate",
    "new_tab",
    "reload",
    "activate_tab",
    "close_tab",
    "screenshot",
    "wait_for_navigation",
    "wait_for_new_tab"
  ],
  content_commands: [
    "back",
    "forward",
    "get_page_url",
    "describe_frame",
    "context_click",
    "click_menu_text",
    "telegram_sticky_author",
    "click_text",
    "clear_editable",
    "click",
    "smart_click",
    "fill",
    "set_editable_text",
    "focus",
    "extract_text",
    "get_html",
    "get_attribute",
    "snapshot",
    "wait_for",
    "wait_selector",
    "scroll",
    "scroll_by",
    "run_script",
    "press_key"
  ],
  frames: ["frame_id", "url", "name", "css", "nested"],
  shadow_dom: ["open"],
  result_outbox: true,
  delivery_acknowledgement: true
};

let pollTimer = null;
let heartbeatTimer = null;
let pollInFlight = false;
let heartbeatInFlight = false;
const cdpAttachedTabs = new Set();

class ApiError extends Error {
  constructor(status, payload, fallback) {
    super(`HTTP ${status}: ${payload?.error || fallback || "request failed"}`);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = payload?.error_code || "";
    this.payload = payload || {};
  }
}

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
  const config = { ...DEFAULT_CONFIG, ...raw };
  if (!config.clientId) {
    config.clientId = `client-${crypto.randomUUID()}`;
    await storageSet({ clientId: config.clientId });
  }
  config.serverUrl = normalizeServerUrl(config.serverUrl);
  return config;
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
    throw new ApiError(response.status, payload, text || response.statusText);
  }
  return payload;
}

function tabsQuery(query) {
  return new Promise((resolve, reject) => {
    chrome.tabs.query(query, (tabs) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(tabs || []);
    });
  });
}

function tabsGet(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.get(tabId, (tab) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(tab || null);
    });
  });
}

function tabsUpdate(tabId, updateProperties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.update(tabId, updateProperties, (tab) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(tab || null);
    });
  });
}

function tabsCreate(createProperties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create(createProperties, (tab) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(tab || null);
    });
  });
}

function tabsReload(tabId, reloadProperties = {}) {
  return new Promise((resolve, reject) => {
    chrome.tabs.reload(tabId, reloadProperties, () => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(true);
    });
  });
}

function tabsRemove(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.remove(tabId, () => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(true);
    });
  });
}

function windowsUpdate(windowId, updateInfo) {
  return new Promise((resolve, reject) => {
    chrome.windows.update(windowId, updateInfo, (window) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(window || null);
    });
  });
}

function tabsSendMessage(tabId, message, options = {}) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, options, (response) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(response);
    });
  });
}

function tabsExecuteScript(tabId, files, frameId = null) {
  const target = { tabId };
  if (Number.isInteger(frameId)) {
    target.frameIds = [frameId];
  }
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript({ target, files }, (results) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(results || []);
    });
  });
}

function webNavigationGetAllFrames(tabId) {
  if (!chrome.webNavigation?.getAllFrames) {
    return Promise.resolve([{ frameId: 0, parentFrameId: -1, url: "" }]);
  }
  return new Promise((resolve, reject) => {
    chrome.webNavigation.getAllFrames({ tabId }, (frames) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(frames || []);
    });
  });
}

async function sendCommandToFrameWithAutoInject(tabId, command, frameId = 0) {
  const options = Number.isInteger(frameId) ? { frameId } : {};
  try {
    return await tabsSendMessage(
      tabId,
      { type: "site-control-command", command },
      options
    );
  } catch (error) {
    const message = String(error?.message || error || "");
    const recoverable =
      message.includes("Receiving end does not exist") ||
      message.includes("Could not establish connection") ||
      message.includes("message port closed");
    if (!recoverable) throw error;
    await tabsExecuteScript(tabId, ["agent_dom.js", "content.js"], frameId);
    return tabsSendMessage(
      tabId,
      { type: "site-control-command", command },
      options
    );
  }
}

function captureVisibleTab(windowId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(dataUrl);
    });
  });
}

function debuggerAttach(tabId, protocolVersion = "1.3") {
  if (!chrome.debugger?.attach) {
    return Promise.reject(new Error("Chrome debugger API is unavailable"));
  }
  if (cdpAttachedTabs.has(tabId)) {
    return Promise.reject(new Error(`CDP is already attached to tab ${tabId} by Site Control Bridge`));
  }
  return new Promise((resolve, reject) => {
    chrome.debugger.attach({ tabId }, protocolVersion, () => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(
          new Error(
            `Cannot attach CDP to tab ${tabId}; another debugger may already be attached: ${error.message}`
          )
        );
        return;
      }
      cdpAttachedTabs.add(tabId);
      storageSet({
        lastCdpEvent: {
          event: "attach",
          tabId,
          at: new Date().toISOString()
        }
      }).finally(() => resolve(true));
    });
  });
}

function debuggerDetach(tabId) {
  if (!chrome.debugger?.detach || !cdpAttachedTabs.has(tabId)) {
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    chrome.debugger.detach({ tabId }, () => {
      const error = chrome.runtime.lastError;
      cdpAttachedTabs.delete(tabId);
      storageSet({
        lastCdpEvent: {
          event: "detach",
          tabId,
          at: new Date().toISOString(),
          error: error?.message || ""
        }
      }).finally(() => resolve(!error));
    });
  });
}

function debuggerSendCommand(tabId, method, params = {}) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
      const error = chrome.runtime.lastError;
      if (error) reject(new Error(error.message));
      else resolve(result || {});
    });
  });
}

async function captureTabScreenshot(tab, fullPage = false) {
  await debuggerAttach(tab.id);
  try {
    await debuggerSendCommand(tab.id, "Page.enable");
    const params = {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: Boolean(fullPage)
    };
    if (fullPage) {
      const metrics = await debuggerSendCommand(tab.id, "Page.getLayoutMetrics");
      const size = metrics?.cssContentSize || metrics?.contentSize;
      if (size?.width && size?.height) {
        params.clip = {
          x: 0,
          y: 0,
          width: Math.max(1, Number(size.width)),
          height: Math.max(1, Number(size.height)),
          scale: 1
        };
      }
    }
    const result = await debuggerSendCommand(tab.id, "Page.captureScreenshot", params);
    if (!result?.data) {
      throw new Error("Chrome DevTools Protocol returned no screenshot data");
    }
    return {
      imageDataUrl: `data:image/png;base64,${result.data}`,
      captureMode: fullPage ? "cdp-full-page" : "cdp-viewport"
    };
  } finally {
    await debuggerDetach(tab.id);
  }
}

async function startCdpObservation(tabId, capture = {}) {
  if (!capture.capture_console && !capture.capture_network) {
    return null;
  }
  if (!capture.allow_cdp) {
    throw new Error("Session capture policy requires CDP but allow_cdp is false");
  }
  await debuggerAttach(tabId);
  const consoleTail = [];
  const networkErrors = [];
  const requests = new Map();
  const onEvent = (source, method, params) => {
    if (source?.tabId !== tabId) return;
    if (method === "Runtime.consoleAPICalled" && capture.capture_console) {
      const text = (params.args || [])
        .map((item) => item.value ?? item.description ?? "")
        .join(" ");
      consoleTail.push({
        at: new Date().toISOString(),
        level: params.type || "log",
        text: String(text).slice(0, 4000)
      });
    } else if (method === "Runtime.exceptionThrown" && capture.capture_console) {
      consoleTail.push({
        at: new Date().toISOString(),
        level: "exception",
        text: String(params.exceptionDetails?.text || "JavaScript exception").slice(0, 4000),
        url: params.exceptionDetails?.url || ""
      });
    } else if (method === "Network.requestWillBeSent" && capture.capture_network) {
      requests.set(params.requestId, {
        url: params.request?.url || "",
        method: params.request?.method || "",
        started: Number(params.timestamp || 0)
      });
    } else if (method === "Network.responseReceived" && capture.capture_network) {
      const status = Number(params.response?.status || 0);
      if (status >= 400) {
        const request = requests.get(params.requestId) || {};
        networkErrors.push({
          at: new Date().toISOString(),
          kind: "http_error",
          url: params.response?.url || request.url || "",
          method: request.method || "",
          status,
          status_text: params.response?.statusText || ""
        });
      }
    } else if (method === "Network.loadingFailed" && capture.capture_network) {
      const request = requests.get(params.requestId) || {};
      networkErrors.push({
        at: new Date().toISOString(),
        kind: "loading_failed",
        url: request.url || "",
        method: request.method || "",
        error_text: params.errorText || "",
        blocked_reason: params.blockedReason || "",
        cors_error: params.corsErrorStatus || null
      });
    } else if (method === "Network.loadingFinished" && capture.capture_network) {
      const request = requests.get(params.requestId);
      if (request) {
        request.duration_ms = Math.max(
          0,
          Math.round((Number(params.timestamp || 0) - request.started) * 1000)
        );
      }
    }
  };
  chrome.debugger.onEvent.addListener(onEvent);
  try {
    if (capture.capture_console) await debuggerSendCommand(tabId, "Runtime.enable");
    if (capture.capture_network) await debuggerSendCommand(tabId, "Network.enable");
  } catch (error) {
    chrome.debugger.onEvent.removeListener(onEvent);
    await debuggerDetach(tabId);
    throw error;
  }
  return {
    async stop() {
      chrome.debugger.onEvent.removeListener(onEvent);
      await debuggerDetach(tabId);
      return {
        console_tail: consoleTail.slice(-100),
        network_errors: networkErrors.slice(-100)
      };
    }
  };
}

async function collectTabs() {
  const tabs = await tabsQuery({});
  return tabs.map((tab) => ({
    id: tab.id,
    windowId: tab.windowId,
    active: Boolean(tab.active),
    title: tab.title || "",
    url: tab.url || "",
    status: tab.status || ""
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
    if (found) return found;
  }
  if (safeTarget.active !== false) {
    const activeTabs = await tabsQuery({ active: true, lastFocusedWindow: true });
    if (activeTabs.length) return activeTabs[0];
  }
  const tabs = await tabsQuery({});
  return tabs.length ? tabs[0] : null;
}

function cloneCommand(command) {
  return JSON.parse(JSON.stringify(command || {}));
}

async function resolveFrame(tabId, command) {
  const normalized = cloneCommand(command);
  let frameId = null;
  const locator = normalized.locator;
  if (Number.isInteger(locator?.frame_id)) {
    frameId = locator.frame_id;
  }
  if (locator?.strategy === "ref") {
    const matched = /^f(\d+):(e\d+)$/.exec(String(locator.value || ""));
    if (matched) {
      frameId = Number(matched[1]);
      normalized.locator.value = matched[2];
      normalized.locator.frame_id = frameId;
    }
  }
  if (Number.isInteger(normalized.frame_id)) {
    frameId = normalized.frame_id;
  }
  const frame = normalized.frame;
  if (frameId === null && frame && typeof frame === "object") {
    const frames = await webNavigationGetAllFrames(tabId);
    if (Number.isInteger(frame.frame_id)) {
      frameId = frame.frame_id;
    } else if (frame.url) {
      const matches = frames.filter((item) =>
        String(item.url || "").includes(String(frame.url))
      );
      if (matches.length !== 1) {
        throw new Error(`Frame URL locator matched ${matches.length} frames`);
      }
      frameId = matches[0].frameId;
    } else if (frame.name) {
      const matches = [];
      for (const candidate of frames) {
        try {
          const response = await sendCommandToFrameWithAutoInject(
            tabId,
            { type: "describe_frame" },
            candidate.frameId
          );
          if (response?.ok && response.data?.name === String(frame.name)) {
            matches.push(candidate);
          }
        } catch {
          // Недоступный фрейм остаётся видимым в диагностике snapshot.
        }
      }
      if (matches.length !== 1) {
        throw new Error(`Frame name locator matched ${matches.length} frames`);
      }
      frameId = matches[0].frameId;
    } else if (frame.css) {
      const described = await sendCommandToFrameWithAutoInject(
        tabId,
        { type: "describe_frame_element", selector: String(frame.css) },
        0
      );
      if (!described?.ok) {
        throw new Error(described?.error?.message || "Frame CSS locator failed");
      }
      const source = String(described.data?.src || "");
      const name = String(described.data?.name || "");
      const matches = frames.filter((item) => {
        const url = String(item.url || "");
        return (source && (url === source || url.includes(source))) || false;
      });
      if (matches.length === 1) {
        frameId = matches[0].frameId;
      } else if (name) {
        normalized.frame = { name };
        return resolveFrame(tabId, normalized);
      } else {
        throw new Error(`Frame CSS locator matched ${matches.length} navigable frames`);
      }
    }
  }
  return { command: normalized, frameId: frameId ?? 0 };
}

function prefixFrameRefs(snapshot, frameId) {
  const prefix = `f${frameId}:`;
  const elements = (snapshot.elements || []).map((item) => ({
    ...item,
    ref: item.ref ? `${prefix}${item.ref}` : null,
    frame_id: frameId
  }));
  return {
    ...snapshot,
    frame_id: frameId,
    elements,
    lines: elements.map((item) => {
      const parts = [`[${item.ref}]`, item.role || item.tag || "element"];
      if (item.name) parts.push(JSON.stringify(item.name));
      if (item.value) parts.push(`value=${JSON.stringify(item.value)}`);
      return parts.join(" ");
    })
  };
}

async function snapshotAllFrames(tabId, command) {
  const frames = command.include_frames === false
    ? [{ frameId: 0, parentFrameId: -1, url: "" }]
    : await webNavigationGetAllFrames(tabId);
  const snapshots = [];
  const frameErrors = [];
  for (const frame of frames) {
    try {
      const response = await sendCommandToFrameWithAutoInject(tabId, command, frame.frameId);
      if (!response?.ok) {
        throw new Error(response?.error?.message || "Frame snapshot failed");
      }
      snapshots.push({
        ...prefixFrameRefs(response.data || {}, frame.frameId),
        parent_frame_id: frame.parentFrameId,
        frame_url: frame.url || response.data?.url || ""
      });
    } catch (error) {
      frameErrors.push({
        frame_id: frame.frameId,
        parent_frame_id: frame.parentFrameId,
        url: frame.url || "",
        error: String(error?.message || error)
      });
    }
  }
  const elements = snapshots.flatMap((item) => item.elements || []);
  return {
    url: snapshots.find((item) => item.frame_id === 0)?.url || "",
    title: snapshots.find((item) => item.frame_id === 0)?.title || "",
    generated_at: new Date().toISOString(),
    frame_count: snapshots.length,
    inaccessible_frame_count: frameErrors.length,
    element_count: elements.length,
    frames: snapshots,
    frame_errors: frameErrors,
    elements,
    lines: snapshots.flatMap((item) =>
      (item.lines || []).map((line) => `[frame=${item.frame_id}] ${line}`)
    )
  };
}

function waitForTab(tabId, options = {}) {
  const timeoutMs = Math.max(100, Number(options.timeout_ms || 15000));
  const expectedUrl = String(options.expected_url || "");
  const expectedTitle = String(options.expected_title || "");
  const waitUntil = String(options.wait_until || "document_loaded");
  const initialUrl = String(options.initial_url || "");
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      clearTimeout(timer);
    };
    const finish = (tab) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve({
        tabId,
        url: tab?.url || "",
        title: tab?.title || "",
        status: tab?.status || "",
        wait_until: waitUntil
      });
    };
    const evaluate = (tab) => {
      const url = String(tab?.url || "");
      const title = String(tab?.title || "");
      if (expectedUrl && !url.includes(expectedUrl)) return false;
      if (expectedTitle && !title.includes(expectedTitle)) return false;
      if (waitUntil === "url_changed" && url === initialUrl) return false;
      if (waitUntil === "document_loaded" && tab?.status !== "complete") return false;
      return true;
    };
    const onUpdated = (updatedTabId, _changeInfo, tab) => {
      if (updatedTabId === tabId && evaluate(tab)) finish(tab);
    };
    chrome.tabs.onUpdated.addListener(onUpdated);
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(new Error(`Navigation wait timed out after ${timeoutMs}ms`));
    }, timeoutMs);
    tabsGet(tabId).then((tab) => {
      if (evaluate(tab)) finish(tab);
    }).catch(() => {});
  });
}

async function waitForNetworkIdle(tabId, options = {}) {
  const timeoutMs = Math.max(100, Number(options.timeout_ms || 15000));
  const quietMs = Math.max(100, Number(options.quiet_ms || 500));
  await debuggerAttach(tabId);
  const inflight = new Set();
  let lastActivityAt = Date.now();
  const onEvent = (source, method, params) => {
    if (source?.tabId !== tabId) return;
    if (method === "Network.requestWillBeSent") {
      inflight.add(params.requestId);
      lastActivityAt = Date.now();
    } else if (method === "Network.loadingFinished" || method === "Network.loadingFailed") {
      inflight.delete(params.requestId);
      lastActivityAt = Date.now();
    }
  };
  chrome.debugger.onEvent.addListener(onEvent);
  try {
    await debuggerSendCommand(tabId, "Network.enable");
    const deadline = Date.now() + timeoutMs;
    while (Date.now() <= deadline) {
      if (!inflight.size && Date.now() - lastActivityAt >= quietMs) {
        return {
          wait_until: "network_idle",
          ready: true,
          quiet_ms: quietMs
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`Network did not become idle within ${timeoutMs}ms`);
  } finally {
    chrome.debugger.onEvent.removeListener(onEvent);
    await debuggerDetach(tabId);
  }
}

async function waitForNavigationReadiness(tabId, options = {}) {
  const waitUntil = String(options.wait_until || "document_loaded");
  if (!["dom_quiet", "network_idle", "loading_gone"].includes(waitUntil)) {
    return waitForTab(tabId, options);
  }
  const documentState = await waitForTab(tabId, {
    ...options,
    wait_until: "document_loaded"
  });
  let detail;
  if (waitUntil === "network_idle") {
    detail = await waitForNetworkIdle(tabId, options);
  } else {
    const response = await sendCommandToFrameWithAutoInject(
      tabId,
      {
        type: "wait_page_state",
        state: waitUntil,
        selector: options.loading_selector,
        quiet_ms: options.quiet_ms,
        timeout_ms: options.timeout_ms
      },
      0
    );
    if (!response?.ok) {
      throw new Error(response?.error?.message || `Page wait failed: ${waitUntil}`);
    }
    detail = response.data;
  }
  return {
    ...documentState,
    wait_until: waitUntil,
    detail
  };
}

async function waitForNewTab(previousTabIds, timeoutMs = 10000) {
  const previous = new Set(previousTabIds);
  const deadline = Date.now() + Math.max(100, Number(timeoutMs));
  while (Date.now() <= deadline) {
    const tabs = await tabsQuery({});
    const created = tabs.find((tab) => !previous.has(tab.id));
    if (created) {
      return {
        tabId: created.id,
        windowId: created.windowId,
        url: created.url || "",
        title: created.title || ""
      };
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`New tab did not appear within ${timeoutMs}ms`);
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

async function acknowledgeEnvelope(config, envelope) {
  return apiRequest(
    config,
    `/api/commands/${encodeURIComponent(envelope.command_id || envelope.id)}/ack`,
    "POST",
    {
      client_id: config.clientId,
      delivery_id: envelope.delivery_id,
      lease_token: envelope.lease_token,
      protocol_version: PROTOCOL_VERSION
    }
  );
}

async function markEnvelopeRunning(config, envelope) {
  return apiRequest(
    config,
    `/api/commands/${encodeURIComponent(envelope.command_id || envelope.id)}/status`,
    "POST",
    {
      client_id: config.clientId,
      delivery_id: envelope.delivery_id,
      lease_token: envelope.lease_token,
      status: "running",
      reason: "browser_execution_started",
      protocol_version: PROTOCOL_VERSION
    }
  );
}

function buildResultPayload(config, envelope, result) {
  return {
    client_id: config.clientId,
    command_id: envelope.command_id || envelope.id,
    delivery_id: envelope.delivery_id,
    lease_token: envelope.lease_token,
    result_id: crypto.randomUUID(),
    protocol_version: PROTOCOL_VERSION,
    attempt_number: envelope.attempt_number,
    ok: Boolean(result.ok),
    status: result.status || (result.ok ? "completed" : "failed"),
    data: result.data ?? null,
    error: result.error ?? null,
    logs: result.logs || [],
    diagnostics: result.diagnostics || {},
    finished_at: new Date().toISOString()
  };
}

async function enqueuePendingResult(config, envelope, result) {
  const stored = await storageGet([RESULT_OUTBOX_KEY]);
  const outbox = stored[RESULT_OUTBOX_KEY] && typeof stored[RESULT_OUTBOX_KEY] === "object"
    ? stored[RESULT_OUTBOX_KEY]
    : {};
  const key = `${envelope.command_id || envelope.id}:${envelope.delivery_id}`;
  if (!outbox[key]) {
    outbox[key] = {
      commandId: envelope.command_id || envelope.id,
      deliveryId: envelope.delivery_id,
      queuedAt: new Date().toISOString(),
      attempts: 0,
      payload: buildResultPayload(config, envelope, result)
    };
  }
  await storageSet({ [RESULT_OUTBOX_KEY]: outbox });
}

async function flushPendingResults(config) {
  const stored = await storageGet([RESULT_OUTBOX_KEY]);
  const outbox = stored[RESULT_OUTBOX_KEY] && typeof stored[RESULT_OUTBOX_KEY] === "object"
    ? stored[RESULT_OUTBOX_KEY]
    : {};
  const entries = Object.entries(outbox).sort(([, left], [, right]) =>
    String(left?.queuedAt || "").localeCompare(String(right?.queuedAt || ""))
  );
  for (const [key, entry] of entries) {
    if (!entry?.commandId || !entry?.payload) {
      delete outbox[key];
      continue;
    }
    try {
      await apiRequest(
        config,
        `/api/commands/${encodeURIComponent(entry.commandId)}/result`,
        "POST",
        entry.payload
      );
      delete outbox[key];
      await storageSet({
        [RESULT_OUTBOX_KEY]: outbox,
        lastCommandId: entry.commandId,
        lastCommandAt: new Date().toISOString(),
        lastCommandStatus: entry.payload.status,
        lastCommandError: entry.payload.error ? JSON.stringify(entry.payload.error) : ""
      });
    } catch (error) {
      if (
        error instanceof ApiError &&
        [400, 404, 409, 410].includes(error.status)
      ) {
        delete outbox[key];
        await storageSet({
          [RESULT_OUTBOX_KEY]: outbox,
          lastOrphanedCommandResult: {
            commandId: entry.commandId,
            deliveryId: entry.deliveryId,
            resultId: entry.payload.result_id,
            droppedAt: new Date().toISOString(),
            status: error.status,
            errorCode: error.errorCode,
            reason: error.message
          }
        });
        continue;
      }
      entry.attempts = Number(entry.attempts || 0) + 1;
      entry.lastError = String(error?.message || error);
      entry.lastAttemptAt = new Date().toISOString();
      outbox[key] = entry;
      await storageSet({ [RESULT_OUTBOX_KEY]: outbox });
      break;
    }
  }
  return Object.keys(outbox).length;
}

async function collectFailureDiagnostics(tab, command, envelope, error) {
  const diagnostics = {
    collected_at: new Date().toISOString(),
    command_id: envelope.command_id || envelope.id,
    delivery_id: envelope.delivery_id,
    attempt_number: envelope.attempt_number,
    tab: {
      id: tab?.id ?? null,
      windowId: tab?.windowId ?? null,
      url: tab?.url || "",
      title: tab?.title || "",
      active: Boolean(tab?.active),
      status: tab?.status || ""
    },
    locator: command?.locator || (command?.selector ? { strategy: "css", value: command.selector } : null),
    candidates: error?.candidates || [],
    candidate_count: Number(error?.candidate_count || 0),
    console_tail: [],
    network_errors: [],
    collection_notes: []
  };
  if (!tab?.id) return diagnostics;
  try {
    diagnostics.semantic_snapshot = await snapshotAllFrames(tab.id, {
      type: "snapshot",
      limit: 100,
      include_frames: true
    });
  } catch (snapshotError) {
    diagnostics.collection_notes.push(`semantic snapshot: ${String(snapshotError?.message || snapshotError)}`);
  }
  const capture = envelope.capture || {};
  if (capture.capture_screenshots) try {
    let screenshot;
    try {
      if (!capture.allow_cdp) throw new Error("CDP capture is disabled by session policy");
      screenshot = await captureTabScreenshot(tab, false);
    } catch (cdpError) {
      if (!tab.active || !Number.isInteger(tab.windowId)) throw cdpError;
      screenshot = {
        imageDataUrl: await captureVisibleTab(tab.windowId),
        captureMode: "visible-tab-fallback"
      };
    }
    diagnostics.screenshot_data_url = screenshot.imageDataUrl;
    diagnostics.screenshot_mode = screenshot.captureMode;
  } catch (screenshotError) {
    diagnostics.collection_notes.push(`screenshot: ${String(screenshotError?.message || screenshotError)}`);
  }
  return diagnostics;
}

async function executeCommandEnvelope(envelope) {
  const command = envelope.command || {};
  const type = command.type;
  const target = envelope.target || {};
  if (!type) {
    return { ok: false, status: "failed", error: { message: "command.type is required" } };
  }
  const previousTabs = command.proof?.new_tab
    ? (await tabsQuery({})).map((tab) => tab.id)
    : [];
  let targetTab = null;
  let observation = null;
  let observationData = { console_tail: [], network_errors: [] };
  try {
    if (type === "new_tab") {
      const created = await tabsCreate({
        url: command.url || "about:blank",
        active: command.active !== false
      });
      let readiness = null;
      if (command.wait_until || command.expected_url || command.expected_title) {
        readiness = await waitForNavigationReadiness(created.id, {
          ...command,
          initial_url: "about:blank"
        });
      }
      return {
        ok: true,
        status: "completed",
        data: {
          tabId: created?.id ?? null,
          windowId: created?.windowId ?? null,
          url: created?.url || command.url || "about:blank",
          active: Boolean(created?.active),
          readiness
        }
      };
    }

    targetTab = await resolveTargetTab(target);
    if (!targetTab || !Number.isInteger(targetTab.id)) {
      return { ok: false, status: "failed", error: { message: "No target tab found" } };
    }

    if (type === "navigate") {
      if (!command.url) {
        return { ok: false, status: "failed", error: { message: "navigate requires command.url" } };
      }
      const initialUrl = targetTab.url || "";
      const updated = await tabsUpdate(targetTab.id, { url: command.url });
      const readiness = await waitForNavigationReadiness(targetTab.id, {
        wait_until: command.wait_until || "document_loaded",
        timeout_ms: command.timeout_ms,
        expected_url:
          command.expected_url ||
          (command.allow_redirects === false ? command.url : ""),
        expected_title: command.expected_title,
        quiet_ms: command.quiet_ms,
        loading_selector: command.loading_selector,
        initial_url: initialUrl
      });
      return {
        ok: true,
        status: "completed",
        data: {
          tabId: updated?.id,
          url: readiness.url || updated?.url || command.url,
          readiness
        }
      };
    }

    if (type === "wait_for_navigation") {
      const readiness = await waitForNavigationReadiness(targetTab.id, {
        ...command,
        initial_url: targetTab.url || ""
      });
      return { ok: true, status: "completed", data: readiness };
    }

    if (type === "wait_for_new_tab") {
      const created = await waitForNewTab(
        Array.isArray(command.previous_tab_ids) ? command.previous_tab_ids : [],
        command.timeout_ms || 10000
      );
      return { ok: true, status: "completed", data: created };
    }

    if (type === "screenshot") {
      let screenshot;
      try {
        screenshot = await captureTabScreenshot(targetTab, Boolean(command.full_page));
      } catch (error) {
        if (!targetTab.active || !Number.isInteger(targetTab.windowId)) throw error;
        screenshot = {
          imageDataUrl: await captureVisibleTab(targetTab.windowId),
          captureMode: "visible-tab-fallback"
        };
      }
      return {
        ok: true,
        status: "completed",
        data: {
          tabId: targetTab.id,
          imageDataUrl: screenshot.imageDataUrl,
          captureMode: screenshot.captureMode
        }
      };
    }

    if (type === "reload") {
      const initialUrl = targetTab.url || "";
      await tabsReload(targetTab.id, { bypassCache: Boolean(command.ignore_cache) });
      const readiness = await waitForNavigationReadiness(targetTab.id, {
        wait_until: command.wait_until || "document_loaded",
        timeout_ms: command.timeout_ms,
        expected_url: command.expected_url,
        expected_title: command.expected_title,
        quiet_ms: command.quiet_ms,
        loading_selector: command.loading_selector,
        initial_url: initialUrl
      });
      return {
        ok: true,
        status: "completed",
        data: { tabId: targetTab.id, reloaded: true, readiness }
      };
    }

    if (type === "activate_tab") {
      const updated = await tabsUpdate(targetTab.id, { active: true });
      if (Number.isInteger(updated?.windowId)) {
        await windowsUpdate(updated.windowId, { focused: true });
      }
      return {
        ok: true,
        status: "completed",
        data: { tabId: updated?.id ?? targetTab.id, active: true }
      };
    }

    if (type === "close_tab") {
      await tabsRemove(targetTab.id);
      return {
        ok: true,
        status: "completed",
        data: { tabId: targetTab.id, closed: true }
      };
    }

    if (type === "snapshot") {
      const snapshot = await snapshotAllFrames(targetTab.id, command);
      return { ok: true, status: "completed", data: snapshot };
    }

    observation = await startCdpObservation(targetTab.id, envelope.capture || {});
    const resolvedFrame = await resolveFrame(targetTab.id, command);
    const response = await sendCommandToFrameWithAutoInject(
      targetTab.id,
      resolvedFrame.command,
      resolvedFrame.frameId
    );
    if (!response) {
      throw new Error("No response from content script");
    }
    if (!response.ok) {
      const error = new Error(response.error?.message || "Content command failed");
      Object.assign(error, response.error || {});
      throw error;
    }
    const data = {
      ...(response.data || {}),
      frame_id: resolvedFrame.frameId
    };
    if (observation) {
      observationData = await observation.stop();
      observation = null;
    }
    if (command.proof?.new_tab) {
      data.proof = {
        ...(data.proof || {}),
        requested: true,
        verified: true,
        new_tab: await waitForNewTab(previousTabs, command.proof.timeout_ms || 10000)
      };
    }
    return {
      ok: true,
      status: "completed",
      data,
      diagnostics: observationData
    };
  } catch (error) {
    if (observation) {
      try {
        observationData = await observation.stop();
      } catch (observationError) {
        observationData = {
          console_tail: [],
          network_errors: [],
          observation_error: String(observationError?.message || observationError)
        };
      }
      observation = null;
    }
    const diagnostics = await collectFailureDiagnostics(targetTab, command, envelope, error);
    diagnostics.console_tail = observationData.console_tail || [];
    diagnostics.network_errors = observationData.network_errors || [];
    if (observationData.observation_error) {
      diagnostics.collection_notes.push(observationData.observation_error);
    }
    return {
      ok: false,
      status: "failed",
      error: {
        message: String(error?.message || error),
        code: error?.code || "browser_command_failed",
        stack: error?.stack || "",
        candidate_count: Number(error?.candidate_count || 0),
        candidates: Array.isArray(error?.candidates) ? error.candidates : [],
        hint: "Проверьте вкладку, права расширения, локатор и диагностический пакет."
      },
      diagnostics
    };
  }
}

async function pollOnce(reason = "timer") {
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    const config = await getConfig();
    if (!config.token) {
      await storageSet({
        lastPollAt: new Date().toISOString(),
        lastPollError: "Не задан токен в настройках расширения",
        lastPollReason: reason
      });
      return;
    }
    const pendingResults = await flushPendingResults(config);
    if (pendingResults > 0) {
      throw new Error(`В очереди результатов осталось записей: ${pendingResults}`);
    }
    const query = new URLSearchParams({ client_id: config.clientId }).toString();
    const response = await apiRequest(config, `/api/commands/next?${query}`, "GET");
    await storageSet({
      lastPollAt: new Date().toISOString(),
      lastPollError: "",
      lastPollReason: reason
    });
    const envelope = response.command;
    if (!envelope) return;
    if (!envelope.delivery_id || !envelope.lease_token) {
      throw new Error("Хаб вернул команду без идентификаторов аренды");
    }
    await acknowledgeEnvelope(config, envelope);
    await markEnvelopeRunning(config, envelope);
    const result = await executeCommandEnvelope(envelope);
    await enqueuePendingResult(config, envelope, result);
    await flushPendingResults(config);
  } catch (error) {
    await storageSet({
      lastPollAt: new Date().toISOString(),
      lastPollError: String(error?.message || error),
      lastPollReason: reason
    });
  } finally {
    pollInFlight = false;
  }
}

async function heartbeatOnce(reason = "timer") {
  if (heartbeatInFlight) return;
  heartbeatInFlight = true;
  try {
    const config = await getConfig();
    if (!config.token) {
      await storageSet({
        lastHeartbeatAt: new Date().toISOString(),
        lastHeartbeatError: "Не задан токен в настройках расширения",
        lastHeartbeatReason: reason
      });
      return;
    }
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
  } finally {
    heartbeatInFlight = false;
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

if (chrome.runtime?.onSuspend?.addListener) {
  chrome.runtime.onSuspend.addListener(stopTimers);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") return;
  if (message.type === "poll_now") {
    pollOnce("popup")
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error?.message || error) }));
    return true;
  }
  if (message.type === "heartbeat_now") {
    heartbeatOnce("popup")
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error?.message || error) }));
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
