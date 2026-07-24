export const MIN_LONG_POLL_WAIT_MS = 1000;
export const MAX_LONG_POLL_WAIT_MS = 25000;

export function normalizeLongPollWaitMs(value, fallback = MAX_LONG_POLL_WAIT_MS) {
  const numeric = Number(value);
  const selected = Number.isFinite(numeric) ? numeric : Number(fallback);
  return Math.max(
    MIN_LONG_POLL_WAIT_MS,
    Math.min(MAX_LONG_POLL_WAIT_MS, Math.round(selected))
  );
}

export function buildNextCommandPath(clientId, waitMs) {
  const query = new URLSearchParams({
    client_id: String(clientId || ""),
    wait_ms: String(normalizeLongPollWaitMs(waitMs))
  });
  return `/api/commands/next?${query}`;
}

export function nextPollDelayMs(outcome, errorDelayMs) {
  if (outcome === "ok") return 0;
  if (outcome === "busy") return 100;
  return Math.max(500, Number(errorDelayMs) || 2000);
}
