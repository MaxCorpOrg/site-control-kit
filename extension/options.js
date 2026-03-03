const DEFAULTS = {
  serverUrl: "http://127.0.0.1:8765",
  token: "local-bridge-quickstart-2026",
  clientId: "",
  pollIntervalMs: 2000,
  heartbeatIntervalMs: 8000
};

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(values) {
  return new Promise((resolve) => chrome.storage.local.set(values, resolve));
}

function $(id) {
  return document.getElementById(id);
}

function setStatus(message, isError = false) {
  const el = $("status");
  el.textContent = message;
  el.classList.toggle("error", isError);
}

async function load() {
  const cfg = { ...DEFAULTS, ...(await storageGet(Object.keys(DEFAULTS))) };
  $("serverUrl").value = cfg.serverUrl;
  $("token").value = cfg.token;
  $("clientId").value = cfg.clientId;
  $("pollIntervalMs").value = cfg.pollIntervalMs;
  $("heartbeatIntervalMs").value = cfg.heartbeatIntervalMs;
}

async function save() {
  const payload = {
    serverUrl: $("serverUrl").value.trim() || DEFAULTS.serverUrl,
    token: $("token").value.trim() || DEFAULTS.token,
    clientId: $("clientId").value.trim() || `client-${crypto.randomUUID()}`,
    pollIntervalMs: Number($("pollIntervalMs").value || DEFAULTS.pollIntervalMs),
    heartbeatIntervalMs: Number($("heartbeatIntervalMs").value || DEFAULTS.heartbeatIntervalMs)
  };

  await storageSet(payload);
  await chrome.runtime.sendMessage({ type: "restart_timers" });
  setStatus("Сохранено. Фоновый сервис перезапустил таймеры.");
}

async function reset() {
  await storageSet({ ...DEFAULTS, clientId: `client-${crypto.randomUUID()}` });
  await load();
  await chrome.runtime.sendMessage({ type: "restart_timers" });
  setStatus("Настройки сброшены к значениям по умолчанию.");
}

document.addEventListener("DOMContentLoaded", async () => {
  await load();

  $("saveBtn").addEventListener("click", () => {
    save().catch((error) => setStatus(String(error?.message || error), true));
  });

  $("resetBtn").addEventListener("click", () => {
    reset().catch((error) => setStatus(String(error?.message || error), true));
  });
});
