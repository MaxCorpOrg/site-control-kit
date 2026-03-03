function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function queryElement(selector) {
  if (!selector || typeof selector !== "string") {
    throw new Error("selector is required");
  }
  const node = document.querySelector(selector);
  if (!node) {
    throw new Error(`Element not found for selector: ${selector}`);
  }
  return node;
}

function isVisible(element) {
  if (!element) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function dispatchInputEvents(element) {
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

async function waitForSelector(selector, timeoutMs = 10000, visibleOnly = false) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = document.querySelector(selector);
    if (found) {
      if (!visibleOnly || isVisible(found)) {
        return found;
      }
    }
    await wait(100);
  }
  throw new Error(`Timeout waiting for selector: ${selector}`);
}

async function runCommand(command) {
  const type = command?.type;
  if (!type) {
    throw new Error("command.type is required");
  }

  switch (type) {
    case "click": {
      const el = queryElement(command.selector);
      el.click();
      return { selector: command.selector, clicked: true };
    }

    case "fill": {
      const el = queryElement(command.selector);
      if (!("value" in el)) {
        throw new Error("Target element does not support value");
      }
      el.focus();
      el.value = command.value ?? "";
      dispatchInputEvents(el);
      return { selector: command.selector, value: el.value };
    }

    case "extract_text": {
      if (command.selector) {
        const el = queryElement(command.selector);
        return { selector: command.selector, text: el.innerText ?? el.textContent ?? "" };
      }
      return { text: document.body?.innerText ?? "" };
    }

    case "get_html": {
      if (command.selector) {
        const el = queryElement(command.selector);
        return { selector: command.selector, html: el.outerHTML };
      }
      return { html: document.documentElement.outerHTML };
    }

    case "get_attribute": {
      const el = queryElement(command.selector);
      const attribute = command.attribute;
      if (!attribute) {
        throw new Error("attribute is required for get_attribute");
      }
      return {
        selector: command.selector,
        attribute,
        value: el.getAttribute(attribute)
      };
    }

    case "wait_selector": {
      const timeoutMs = Number(command.timeout_ms || 10000);
      const visibleOnly = Boolean(command.visible_only);
      const el = await waitForSelector(command.selector, timeoutMs, visibleOnly);
      return {
        selector: command.selector,
        found: true,
        visible: isVisible(el)
      };
    }

    case "scroll": {
      if (command.selector) {
        const el = queryElement(command.selector);
        el.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
        return { selector: command.selector, scrolled: true };
      }
      const x = Number.isFinite(command.x) ? Number(command.x) : window.scrollX;
      const y = Number.isFinite(command.y) ? Number(command.y) : 0;
      window.scrollTo({ top: y, left: x, behavior: "auto" });
      return { x, y, scrolled: true };
    }

    case "run_script": {
      if (!command.script || typeof command.script !== "string") {
        throw new Error("script is required for run_script");
      }
      const fn = new Function("command", "args", command.script);
      const value = await fn(command, command.args ?? {});
      return { value: value ?? null };
    }

    default:
      throw new Error(`Unsupported command type in content script: ${type}`);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "site-control-command") {
    return;
  }

  runCommand(message.command)
    .then((data) => {
      sendResponse({ ok: true, data });
    })
    .catch((error) => {
      sendResponse({
        ok: false,
        error: {
          message: String(error?.message || error),
          stack: error?.stack || ""
        }
      });
    });

  return true;
});
