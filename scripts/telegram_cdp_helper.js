#!/usr/bin/env node

"use strict";

const TELEGRAM_START_URL = "https://web.telegram.org/a/";
const CHAT_LIST_READY_SELECTOR =
  "#LeftColumn a.chatlist-chat, #column-left a.chatlist-chat, a.chatlist-chat, #LeftColumn, #column-left";
const CHAT_READY_SELECTOR =
  ".MessageList.custom-scroll, .messages-layout .MessageList, .chat.tabs-tab.active, .bubbles";
const CHAT_SCROLL_SELECTORS = [
  ".MessageList.custom-scroll .backwards-trigger",
  ".messages-layout .MessageList.custom-scroll .backwards-trigger",
  ".messages-container > :first-child",
  ".message-date-group.first-message-date-group",
  ".bubbles .sticky_sentinel--top",
  ".chat.tabs-tab.active .bubbles .bubbles-group-avatar",
  "#column-center .bubbles [data-mid]",
  ".chat.tabs-tab.active .bubbles",
];

function fail(message, detail = "") {
  const payload = { ok: false, error: detail ? `${message}: ${detail}` : message };
  process.stderr.write(`${payload.error}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) {
      args._.push(value);
      continue;
    }
    const key = value.slice(2);
    const next = argv[index + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = "1";
      continue;
    }
    args[key] = next;
    index += 1;
  }
  return args;
}

async function httpJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`);
  }
  return response.json();
}

async function waitForDebugger(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      return await httpJson(`http://127.0.0.1:${port}/json/version`);
    } catch (error) {
      lastError = String(error && error.message ? error.message : error);
    }
    await sleep(250);
  }
  throw new Error(lastError || `CDP port ${port} is not ready`);
}

async function listTargets(port) {
  const payload = await httpJson(`http://127.0.0.1:${port}/json/list`);
  return Array.isArray(payload) ? payload : [];
}

function selectTelegramTarget(targets) {
  const ranked = targets
    .filter(
      (target) =>
        target &&
        target.type === "page" &&
        typeof target.webSocketDebuggerUrl === "string" &&
        String(target.url || "").includes("web.telegram.org")
    )
    .map((target) => {
      const url = String(target.url || "");
      const hasDialog = url.includes("/#");
      return {
        score: [hasDialog ? 1 : 0, url.length],
        target,
      };
    })
    .sort((left, right) => {
      for (let index = 0; index < left.score.length; index += 1) {
        if (left.score[index] !== right.score[index]) {
          return right.score[index] - left.score[index];
        }
      }
      return String(right.target.url || "").localeCompare(String(left.target.url || ""));
    });
  return ranked.length > 0 ? ranked[0].target : null;
}

async function ensureTelegramTarget(port, url) {
  const existing = selectTelegramTarget(await listTargets(port));
  if (existing) {
    return existing;
  }
  await httpJson(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const created = selectTelegramTarget(await listTargets(port));
    if (created) {
      return created;
    }
    await sleep(250);
  }
  throw new Error("Telegram tab was not created on the CDP browser");
}

function compact(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeUsername(value) {
  const text = compact(value);
  if (!text) {
    return "";
  }
  const patterns = [
    /https?:\/\/t\.me\/([A-Za-z0-9_]{5,32})/i,
    /t\.me\/([A-Za-z0-9_]{5,32})/i,
    /@([A-Za-z0-9_]{5,32})/i,
    /^([A-Za-z0-9_]{5,32})$/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) {
      continue;
    }
    const candidate = String(match[1] || "").trim();
    if (/[A-Za-z]/.test(candidate)) {
      return `@${candidate}`;
    }
  }
  return "";
}

class CdpConnection {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 0;
    this.pending = new Map();
    this.eventHandlers = new Map();
  }

  async open() {
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = (event) => reject(new Error(event && event.message ? event.message : "WebSocket error"));
      ws.onmessage = (event) => this._handleMessage(event);
      ws.onclose = () => {
        for (const { reject: rejectPending } of this.pending.values()) {
          rejectPending(new Error("CDP socket closed"));
        }
        this.pending.clear();
      };
    });
  }

  close() {
    if (this.ws) {
      this.ws.close();
    }
  }

  _handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.id && this.pending.has(message.id)) {
      const entry = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) {
        entry.reject(new Error(message.error.message || "Unknown CDP error"));
      } else {
        entry.resolve(message.result || {});
      }
      return;
    }
    if (message.method && this.eventHandlers.has(message.method)) {
      for (const handler of this.eventHandlers.get(message.method)) {
        handler(message.params || {});
      }
    }
  }

  on(method, handler) {
    if (!this.eventHandlers.has(method)) {
      this.eventHandlers.set(method, []);
    }
    this.eventHandlers.get(method).push(handler);
  }

  async send(method, params = {}) {
    if (!this.ws) {
      throw new Error("CDP socket is not open");
    }
    const id = ++this.nextId;
    const payload = { id, method, params };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(payload));
    });
  }
}

async function withTelegramPage(port, targetUrl, callback) {
  await waitForDebugger(port, 15000);
  const target = await ensureTelegramTarget(port, targetUrl);
  const connection = new CdpConnection(target.webSocketDebuggerUrl);
  await connection.open();
  try {
    await connection.send("Page.enable");
    await connection.send("Runtime.enable");
    await connection.send("DOM.enable");
    return await callback(connection, target);
  } finally {
    connection.close();
  }
}

async function evaluate(connection, expression) {
  const response = await connection.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    const text = response.exceptionDetails.text || "Runtime evaluation failed";
    throw new Error(text);
  }
  return response.result ? response.result.value : null;
}

async function waitForExpression(connection, expression, timeoutMs, description) {
  const deadline = Date.now() + timeoutMs;
  let lastValue = null;
  while (Date.now() < deadline) {
    try {
      lastValue = await evaluate(connection, expression);
      if (lastValue) {
        return lastValue;
      }
    } catch (error) {
      lastValue = { error: String(error && error.message ? error.message : error) };
    }
    await sleep(300);
  }
  throw new Error(`${description} was not ready in time`);
}

async function navigate(connection, url) {
  const loadPromise = new Promise((resolve) => {
    let resolved = false;
    const handler = () => {
      if (!resolved) {
        resolved = true;
        resolve();
      }
    };
    connection.on("Page.loadEventFired", handler);
    setTimeout(handler, 5000);
  });
  await connection.send("Page.navigate", { url });
  await loadPromise;
  await sleep(800);
}

function visibleDialogsExpression() {
  return `(() => {
    const compact = (value) => String(value || "").replace(/\\s+/g, " ").trim();
    const visible = (node) => {
      if (!node) return false;
      const rect = node.getBoundingClientRect();
      if (rect.width < 6 || rect.height < 6) return false;
      if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= window.innerHeight || rect.left >= window.innerWidth) {
        return false;
      }
      const style = window.getComputedStyle(node);
      if (!style) return true;
      return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0;
    };
    const textOf = (root, selectors) => {
      for (const selector of selectors) {
        const node = root.querySelector(selector);
        const text = compact(node?.innerText || node?.textContent || node?.getAttribute?.("aria-label") || "");
        if (text) return text;
      }
      return "";
    };
    const modeMatch = String(window.location.href || "").match(/web\\.telegram\\.org\\/([ak])\\//i);
    const mode = modeMatch ? modeMatch[1].toLowerCase() : "a";
    const anchors = Array.from(document.querySelectorAll(
      [
        "#LeftColumn a.chatlist-chat",
        "#column-left a.chatlist-chat",
        "a.chatlist-chat",
        "a[href^='#'][data-peer-id]"
      ].join(",")
    ));
    const items = [];
    const seen = new Set();
    anchors.forEach((anchor, index) => {
      const href = compact(anchor.getAttribute("href") || "");
      const peerId = compact(anchor.getAttribute("data-peer-id") || "");
      const fragment = href.startsWith("#") ? href.slice(1) : peerId;
      if (!fragment || seen.has(fragment)) return;
      const title = textOf(anchor, [
        ".fullName",
        ".peer-title-inner",
        ".peer-title",
        ".user-title",
        "h3",
        "[dir='auto']"
      ]);
      const subtitle = textOf(anchor, [
        ".row-subtitle",
        ".subtitle",
        ".status",
        ".user-status",
        ".last-message"
      ]);
      const row = anchor.closest("a, .ListItem, .chatlist-chat") || anchor;
      const active = row.classList.contains("active") || anchor.classList.contains("active") || anchor.getAttribute("aria-current") === "true";
      const payload = {
        index,
        title: title || fragment,
        subtitle,
        fragment,
        peer_id: peerId,
        url: "https://web.telegram.org/" + mode + "/#" + fragment,
        active,
        visible: visible(anchor) || visible(row)
      };
      seen.add(fragment);
      items.push(payload);
    });
    return {
      current_url: String(window.location.href || ""),
      current_title: String(document.title || ""),
      auth_required: Boolean(
        document.querySelector("canvas[aria-label*='QR'], .auth-code-form, .input-field-phone, .LoginPage")
      ),
      items
    };
  })()`;
}

function captureSnapshotExpression() {
  return `(() => {
    const compact = (value) => String(value || "").replace(/\\s+/g, " ").trim();
    const normalizeUsername = (value) => {
      const text = compact(value);
      if (!text) return "";
      const patterns = [
        /https?:\\/\\/t\\.me\\/([A-Za-z0-9_]{5,32})/i,
        /t\\.me\\/([A-Za-z0-9_]{5,32})/i,
        /@([A-Za-z0-9_]{5,32})/i,
        /^([A-Za-z0-9_]{5,32})$/i
      ];
      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (!match) continue;
        const candidate = String(match[1] || "").trim();
        if (/[A-Za-z]/.test(candidate)) return "@" + candidate;
      }
      return "";
    };
    const textOf = (root, selectors) => {
      for (const selector of selectors) {
        const node = root.querySelector(selector);
        const text = compact(node?.innerText || node?.textContent || node?.getAttribute?.("aria-label") || "");
        if (text) return text;
      }
      return "";
    };
    const usernameFromNode = (root) => {
      if (!root) return "";
      const candidates = [];
      candidates.push(root.innerHTML || "");
      candidates.push(root.textContent || "");
      for (const link of root.querySelectorAll("a[href], [data-peer-id], [title], [aria-label]")) {
        candidates.push(link.getAttribute("href") || "");
        candidates.push(link.getAttribute("title") || "");
        candidates.push(link.getAttribute("aria-label") || "");
        candidates.push(link.textContent || "");
      }
      for (const item of candidates) {
        const username = normalizeUsername(item);
        if (username) return username;
      }
      return "";
    };
    const members = [];
    const infoMembers = [];
    const seen = new Set();
    const pushMember = (collection, value) => {
      const peerId = compact(value.peer_id || "");
      if (!peerId || peerId.startsWith("-")) return;
      const key = collection === infoMembers ? "info:" + peerId : "chat:" + peerId;
      if (seen.has(key)) return;
      seen.add(key);
      collection.push({
        peer_id: peerId,
        name: compact(value.name || "") || "—",
        username: normalizeUsername(value.username || "") || "—",
        status: compact(value.status || "") || "—",
        role: compact(value.role || "") || "—"
      });
    };
    for (const avatar of document.querySelectorAll(".sender-group-container .Avatar[data-peer-id], .MessageList .Avatar[data-peer-id], .bubbles .Avatar[data-peer-id]")) {
      const peerId = compact(avatar.getAttribute("data-peer-id") || "");
      const block = avatar.closest(".sender-group-container, .bubble, .message, .bubbles-group") || avatar.parentElement || avatar;
      const name = textOf(block, [
        ".sender-title",
        ".message-title-name",
        ".peer-title-inner",
        ".peer-title",
        "img.Avatar__media"
      ]) || compact(avatar.getAttribute("title") || avatar.getAttribute("aria-label") || "");
      const role = textOf(block, [".admin-title-badge", ".bubble-name-rank"]);
      pushMember(members, {
        peer_id: peerId,
        name,
        username: usernameFromNode(block),
        status: "из чата",
        role
      });
    }
    for (const node of document.querySelectorAll(".colored-name.floating-part[data-peer-id], .peer-title.bubble-name-first[data-peer-id], .bubbles .peer-title[data-peer-id]")) {
      const peerId = compact(node.getAttribute("data-peer-id") || "");
      const block = node.closest(".sender-group-container, .bubble, .message, .bubbles-group") || node.parentElement || node;
      const name = textOf(block, [".peer-title-inner", ".peer-title", ".message-title-name", ".sender-title"]) || compact(node.textContent || "");
      const role = textOf(block, [".bubble-name-rank", ".admin-title-badge"]);
      pushMember(members, {
        peer_id: peerId,
        name,
        username: usernameFromNode(block),
        status: "из чата",
        role
      });
    }
    for (const row of document.querySelectorAll("#RightColumn .content.members-list [data-peer-id], #column-right .content.members-list [data-peer-id]")) {
      const peerId = compact(row.getAttribute("data-peer-id") || "");
      const block = row.closest("a, .ListItem, .contact-list-item") || row;
      const name = textOf(block, [".fullName", ".peer-title-inner", ".peer-title", "h3", "[dir='auto']"]);
      const status = textOf(block, [".user-status", ".row-subtitle", ".subtitle"]);
      const role = textOf(block, [".bubble-name-rank", ".admin-title-badge"]);
      pushMember(infoMembers, {
        peer_id: peerId,
        name,
        username: usernameFromNode(block),
        status,
        role
      });
    }
    const mentions = [];
    const seenMentions = new Set();
    const bodyHtml = String(document.body?.innerHTML || "");
    for (const pattern of [
      /https?:\\/\\/t\\.me\\/([A-Za-z0-9_]{5,32})/ig,
      /href="[^"]*#@([A-Za-z0-9_]{5,32})"/ig,
      /class="mention"[^>]*>@([A-Za-z0-9_]{5,32})</ig,
      /@([A-Za-z0-9_]{5,32})/ig
    ]) {
      for (const match of bodyHtml.matchAll(pattern)) {
        const username = normalizeUsername(match[1] || "");
        if (!username || seenMentions.has(username.toLowerCase())) continue;
        seenMentions.add(username.toLowerCase());
        mentions.push(username);
      }
    }
    return {
      current_url: String(window.location.href || ""),
      current_title: String(document.title || ""),
      members,
      info_members: infoMembers,
      mentions
    };
  })()`;
}

function scrollChatExpression() {
  return `(() => {
    const selectors = ${JSON.stringify(CHAT_SCROLL_SELECTORS)};
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (!node) continue;
      if (typeof node.scrollIntoView === "function") {
        node.scrollIntoView({ block: "start", inline: "nearest" });
        return { ok: true, selector, method: "scrollIntoView" };
      }
    }
    for (const selector of [
      ".bubbles .scrollable.scrollable-y",
      ".chat.tabs-tab.active .bubbles .scrollable-y",
      "#column-center .bubbles .scrollable-y",
      ".MessageList.custom-scroll"
    ]) {
      const node = document.querySelector(selector);
      if (!node) continue;
      if (typeof node.scrollTop === "number") {
        node.scrollTop = Math.max(0, node.scrollTop - 900);
        return { ok: true, selector, method: "scrollTop" };
      }
    }
    window.scrollBy(0, -900);
    return { ok: true, selector: "window", method: "scrollBy" };
  })()`;
}

async function commandStatus(args) {
  const port = Number(args.port || "0");
  if (!port) {
    throw new Error("--port is required");
  }
  const version = await waitForDebugger(port, Number(args["timeout-ms"] || "15000"));
  const targets = await listTargets(port);
  const telegram = selectTelegramTarget(targets);
  return {
    ok: true,
    port,
    version,
    telegram_target: telegram
      ? {
          id: String(telegram.id || ""),
          title: String(telegram.title || ""),
          url: String(telegram.url || ""),
        }
      : null,
  };
}

async function commandListChats(args) {
  const port = Number(args.port || "0");
  if (!port) {
    throw new Error("--port is required");
  }
  const timeoutMs = Number(args["timeout-ms"] || "45000");
  const targetUrl = String(args.url || TELEGRAM_START_URL);
  return withTelegramPage(port, targetUrl, async (connection, target) => {
    if (!String(target.url || "").includes("web.telegram.org")) {
      await navigate(connection, targetUrl);
    }
    const readiness = await waitForExpression(
      connection,
      `(() => {
        const ready = Boolean(document.querySelector(${JSON.stringify(CHAT_LIST_READY_SELECTOR)}));
        const authRequired = Boolean(document.querySelector("canvas[aria-label*='QR'], .auth-code-form, .input-field-phone, .LoginPage"));
        return ready ? { ready: true } : authRequired ? { auth_required: true } : null;
      })()`,
      timeoutMs,
      "Telegram chat list"
    );
    if (readiness && readiness.auth_required) {
      throw new Error("Selected browser profile is not logged into Telegram Web");
    }
    const payload = await evaluate(connection, visibleDialogsExpression());
    return { ok: true, ...payload };
  });
}

async function commandOpenChat(args) {
  const port = Number(args.port || "0");
  const url = String(args.url || "");
  if (!port || !url) {
    throw new Error("--port and --url are required");
  }
  const timeoutMs = Number(args["timeout-ms"] || "30000");
  return withTelegramPage(port, url, async (connection) => {
    await navigate(connection, url);
    await waitForExpression(
      connection,
      `(() => {
        const href = String(window.location.href || "");
        const chatReady = Boolean(document.querySelector(${JSON.stringify(CHAT_READY_SELECTOR)}));
        return href.includes("/#") && chatReady ? { href, title: String(document.title || "") } : null;
      })()`,
      timeoutMs,
      "Telegram chat surface"
    );
    const snapshot = await evaluate(
      connection,
      `(() => ({ current_url: String(window.location.href || ""), current_title: String(document.title || "") }))()`
    );
    return { ok: true, ...snapshot };
  });
}

async function commandCollectChat(args) {
  const port = Number(args.port || "0");
  const url = String(args.url || "");
  if (!port || !url) {
    throw new Error("--port and --url are required");
  }
  const timeoutMs = Number(args["timeout-ms"] || "90000");
  const steps = Math.max(Number(args.steps || "20"), 0);
  const pauseMs = Math.max(Number(args["pause-ms"] || "450"), 100);
  return withTelegramPage(port, url, async (connection) => {
    await navigate(connection, url);
    await waitForExpression(
      connection,
      `(() => {
        const chatReady = Boolean(document.querySelector(${JSON.stringify(CHAT_READY_SELECTOR)}));
        return chatReady ? { ready: true } : null;
      })()`,
      timeoutMs,
      "Telegram chat surface"
    );
    const snapshots = [];
    for (let step = 0; step <= steps; step += 1) {
      const snapshot = await evaluate(connection, captureSnapshotExpression());
      snapshots.push({ step, ...snapshot });
      if (step >= steps) {
        break;
      }
      await evaluate(connection, scrollChatExpression());
      await sleep(pauseMs);
    }
    const finalMeta = await evaluate(
      connection,
      `(() => ({ current_url: String(window.location.href || ""), current_title: String(document.title || "") }))()`
    );
    return { ok: true, steps, snapshots, ...finalMeta };
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = String(args._[0] || "").trim();
  if (!command) {
    throw new Error("command is required");
  }
  let payload = null;
  switch (command) {
    case "status":
      payload = await commandStatus(args);
      break;
    case "list-chats":
      payload = await commandListChats(args);
      break;
    case "open-chat":
      payload = await commandOpenChat(args);
      break;
    case "collect-chat":
      payload = await commandCollectChat(args);
      break;
    default:
      throw new Error(`unsupported command: ${command}`);
  }
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => fail("telegram_cdp_helper failed", String(error && error.message ? error.message : error)));
