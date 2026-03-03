const KEYS = [
  "clientId",
  "serverUrl",
  "lastPollAt",
  "lastPollError",
  "lastHeartbeatAt",
  "lastHeartbeatError",
  "lastCommandId",
  "lastCommandStatus",
  "lastCommandError"
];

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function $(id) {
  return document.getElementById(id);
}

async function refresh() {
  const st = await storageGet(KEYS);
  $("clientLine").textContent = `Клиент: ${st.clientId || "-"} | Хаб: ${st.serverUrl || "-"}`;
  $("lastPoll").textContent = st.lastPollAt || "-";
  $("lastHeartbeat").textContent = st.lastHeartbeatAt || "-";
  $("lastCommand").textContent = st.lastCommandId || "-";
  $("lastResult").textContent = st.lastCommandStatus || "-";

  const errors = [st.lastPollError, st.lastHeartbeatError, st.lastCommandError].filter(Boolean).join(" | ");
  $("errorLine").textContent = errors;
}

async function runAction(type) {
  const response = await chrome.runtime.sendMessage({ type });
  if (!response?.ok) {
    throw new Error(response?.error || "Действие не выполнено");
  }
  await refresh();
}

document.addEventListener("DOMContentLoaded", async () => {
  await refresh();

  $("pollNowBtn").addEventListener("click", () => {
    runAction("poll_now").catch((error) => {
      $("errorLine").textContent = String(error?.message || error);
    });
  });

  $("heartbeatNowBtn").addEventListener("click", () => {
    runAction("heartbeat_now").catch((error) => {
      $("errorLine").textContent = String(error?.message || error);
    });
  });

  $("openOptionsBtn").addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });
});
