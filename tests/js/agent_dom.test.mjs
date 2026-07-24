import assert from "node:assert/strict";
import test from "node:test";

await import("../../extension/agent_dom.js");

const agent = globalThis.__siteControlAgentDom;

function fakeElement(tagName, attributes = {}, extra = {}) {
  return {
    tagName,
    type: attributes.type || "",
    value: attributes.value || "",
    readOnly: false,
    isContentEditable: false,
    matches: () => false,
    getAttribute: (name) => attributes[name] ?? null,
    hasAttribute: (name) => Object.hasOwn(attributes, name),
    ...extra
  };
}

test("определяет неявную роль кнопки", () => {
  assert.equal(agent.roleOf(fakeElement("BUTTON")), "button");
});

test("использует aria-label как доступное имя", () => {
  const element = fakeElement("BUTTON", { "aria-label": "Сохранить" });
  assert.equal(agent.accessibleName(element), "Сохранить");
});

test("не считает checkbox текстовым полем", () => {
  assert.equal(agent.isEditable(fakeElement("INPUT", { type: "checkbox" })), false);
  assert.equal(agent.isEditable(fakeElement("INPUT", { type: "text" })), true);
});
