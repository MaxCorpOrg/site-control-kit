import assert from "node:assert/strict";
import test from "node:test";

import {
  buildNextCommandPath,
  nextPollDelayMs,
  normalizeLongPollWaitMs
} from "../../extension/transport.js";

test("ограничивает время долгого запроса безопасным диапазоном", () => {
  assert.equal(normalizeLongPollWaitMs(10), 1000);
  assert.equal(normalizeLongPollWaitMs(12000), 12000);
  assert.equal(normalizeLongPollWaitMs(99999), 25000);
});

test("кодирует клиента и время ожидания в URL", () => {
  assert.equal(
    buildNextCommandPath("browser one", 12000),
    "/api/commands/next?client_id=browser+one&wait_ms=12000"
  );
});

test("после успеха продолжает сразу, а после ошибки использует задержку", () => {
  assert.equal(nextPollDelayMs("ok", 2000), 0);
  assert.equal(nextPollDelayMs("busy", 2000), 100);
  assert.equal(nextPollDelayMs("error", 2000), 2000);
});
