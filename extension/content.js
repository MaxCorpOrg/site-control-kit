function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function queryElement(selector) {
  if (!selector || typeof selector !== "string") {
    throw new Error("selector is required");
  }
  const nodes = Array.from(document.querySelectorAll(selector));
  if (!nodes.length) {
    throw new Error(`Element not found for selector: ${selector}`);
  }
  if (nodes.length === 1) {
    return nodes[0];
  }

  const cx = window.innerWidth / 2;
  const cy = window.innerHeight / 2;
  const visible = [];
  for (const node of nodes) {
    const rect = node.getBoundingClientRect();
    if (
      rect.width < 2 ||
      rect.height < 2 ||
      rect.bottom <= 0 ||
      rect.right <= 0 ||
      rect.top >= window.innerHeight ||
      rect.left >= window.innerWidth
    ) {
      continue;
    }
    const style = window.getComputedStyle(node);
    if (!style || style.display === "none" || style.visibility === "hidden" || style.pointerEvents === "none" || Number(style.opacity || "1") === 0) {
      continue;
    }
    const dx = rect.left + rect.width / 2 - cx;
    const dy = rect.top + rect.height / 2 - cy;
    const dist = Math.abs(dx) + Math.abs(dy);
    const z = Number(style.zIndex) || 0;
    visible.push({ node, dist, z });
  }
  if (!visible.length) {
    return nodes[nodes.length - 1];
  }
  visible.sort((a, b) => (b.z - a.z) || (a.dist - b.dist));
  return visible[0].node;
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

function bytesFromBase64(base64) {
  const binary = atob(String(base64 || ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function buildFileTransfer(command) {
  const fileName = String(command.file_name || "upload.bin");
  const mimeType = String(command.mime_type || "application/octet-stream");
  const bytes = bytesFromBase64(command.file_base64);
  const file = new File([bytes], fileName, {
    type: mimeType,
    lastModified: Number(command.last_modified || Date.now())
  });
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  return { file, dataTransfer };
}

function dispatchDropEvent(target, eventType, dataTransfer) {
  const rect = target.getBoundingClientRect();
  const clientX = Math.round(rect.left + Math.max(1, rect.width / 2));
  const clientY = Math.round(rect.top + Math.max(1, rect.height / 2));
  target.dispatchEvent(
    new DragEvent(eventType, {
      bubbles: true,
      cancelable: true,
      view: window,
      dataTransfer,
      clientX,
      clientY
    })
  );
}

function focusElement(element) {
  if (typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
  }
  if (typeof element.focus === "function") {
    element.focus();
  }
}

function keyCodeForKey(key) {
  const normalized = String(key || "");
  if (normalized.length === 1) {
    return normalized.toUpperCase().charCodeAt(0);
  }
  const mapping = {
    Enter: 13,
    Escape: 27,
    Tab: 9,
    Space: 32,
    ArrowUp: 38,
    ArrowDown: 40,
    ArrowLeft: 37,
    ArrowRight: 39,
    Backspace: 8,
    Delete: 46
  };
  return mapping[normalized] || 0;
}

function dispatchKeyboardSequence(target, command) {
  const key = String(command.key || "");
  if (!key) {
    throw new Error("key is required");
  }

  const eventInit = {
    key,
    code: command.code || key,
    ctrlKey: Boolean(command.ctrl),
    altKey: Boolean(command.alt),
    shiftKey: Boolean(command.shift),
    metaKey: Boolean(command.meta),
    bubbles: true,
    cancelable: true,
    keyCode: keyCodeForKey(key),
    which: keyCodeForKey(key)
  };

  target.dispatchEvent(new KeyboardEvent("keydown", eventInit));
  target.dispatchEvent(new KeyboardEvent("keypress", eventInit));
  target.dispatchEvent(new KeyboardEvent("keyup", eventInit));
}

function normalizedText(value) {
  return String(value || "").trim().toLowerCase();
}

let lastContextPoint = null;

function closestClickable(node) {
  if (!node || typeof node.closest !== "function") {
    return node || null;
  }
  return (
    node.closest("button, a, [role='menuitem'], [role='button'], .btn-menu-item, .MenuItem, .menu-item, [class*='menu-item'], .row") ||
    node
  );
}

function interactableRect(node) {
  if (!node) {
    return null;
  }
  const rect = node.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= window.innerHeight || rect.left >= window.innerWidth) {
    return null;
  }
  const style = window.getComputedStyle(node);
  if (!style || style.display === "none" || style.visibility === "hidden" || style.pointerEvents === "none" || Number(style.opacity || "1") === 0) {
    return null;
  }
  return { rect, style };
}

function findByText(terms, rootSelector, nearLastContext = false) {
  const root = rootSelector ? document.querySelector(rootSelector) : document;
  if (!root) {
    return null;
  }
  const needles = (Array.isArray(terms) ? terms : [terms]).map(normalizedText).filter(Boolean);
  if (!needles.length) {
    return null;
  }
  const nodes = Array.from(
    root.querySelectorAll(
      "button, a, [role='menuitem'], [role='button'], .btn-menu-item, .MenuItem, .menu-item, [class*='menu-item'], [class*='menu-item-text'], .btn-menu-item-text, .row, span.i18n"
    )
  );
  const cx =
    nearLastContext && lastContextPoint ? Number(lastContextPoint.x || window.innerWidth / 2) : window.innerWidth / 2;
  const cy =
    nearLastContext && lastContextPoint ? Number(lastContextPoint.y || window.innerHeight / 2) : window.innerHeight / 2;
  const candidates = [];
  const seen = new Set();
  for (const node of nodes) {
    const target = closestClickable(node);
    if (!target || seen.has(target)) {
      continue;
    }
    seen.add(target);
    const txt = normalizedText(target.textContent || node.textContent);
    if (!txt) {
      continue;
    }
    if (!needles.some((needle) => txt.includes(needle))) {
      continue;
    }
    const visible = interactableRect(target);
    if (!visible) {
      continue;
    }
    const { rect, style } = visible;
    const z = Number(style.zIndex) || 0;
    const dx = rect.left + rect.width / 2 - cx;
    const dy = rect.top + rect.height / 2 - cy;
    const dist = Math.abs(dx) + Math.abs(dy);
    candidates.push({ node: target, z, dist });
  }
  if (!candidates.length) {
    return null;
  }
  candidates.sort((a, b) => (b.z - a.z) || (a.dist - b.dist));
  return candidates[0].node;
}

function findMenuItemByText(terms, nearLastContext = false) {
  const needles = (Array.isArray(terms) ? terms : [terms]).map(normalizedText).filter(Boolean);
  if (!needles.length) {
    return null;
  }
  const cx =
    nearLastContext && lastContextPoint ? Number(lastContextPoint.x || window.innerWidth / 2) : window.innerWidth / 2;
  const cy =
    nearLastContext && lastContextPoint ? Number(lastContextPoint.y || window.innerHeight / 2) : window.innerHeight / 2;

  const menuRoots = Array.from(document.querySelectorAll(".btn-menu, [role='menu'], [class*='contextmenu'], [class*='popup'], [class*='dropdown']"));
  const visibleRoots = [];
  for (const root of menuRoots) {
    const visible = interactableRect(root);
    if (!visible) {
      continue;
    }
    const { rect, style } = visible;
    const z = Number(style.zIndex) || 0;
    const dx = rect.left + rect.width / 2 - cx;
    const dy = rect.top + rect.height / 2 - cy;
    const dist = Math.abs(dx) + Math.abs(dy);
    visibleRoots.push({ root, z, dist });
  }
  if (!visibleRoots.length) {
    return null;
  }
  visibleRoots.sort((a, b) => (b.z - a.z) || (a.dist - b.dist));

  const seen = new Set();
  const candidates = [];
  for (const { root, z: rootZ, dist: rootDist } of visibleRoots) {
    const nodes = Array.from(
      root.querySelectorAll(
        ".btn-menu-item, [role='menuitem'], button, a, .menu-item, [class*='menu-item'], .row, .btn-menu-item-text, [class*='menu-item-text'], .i18n, span"
      )
    );
    for (const node of nodes) {
      const target = closestClickable(node);
      if (!target || seen.has(target)) {
        continue;
      }
      seen.add(target);
      const txt = normalizedText(target.textContent || node.textContent);
      if (!txt || !needles.some((needle) => txt.includes(needle))) {
        continue;
      }
      const visible = interactableRect(target);
      if (!visible) {
        continue;
      }
      const { rect, style } = visible;
      const z = Math.max(rootZ, Number(style.zIndex) || 0);
      const dx = rect.left + rect.width / 2 - cx;
      const dy = rect.top + rect.height / 2 - cy;
      const dist = Math.abs(dx) + Math.abs(dy);
      candidates.push({ node: target, z, dist, rootDist });
    }
  }
  if (!candidates.length) {
    return null;
  }
  candidates.sort((a, b) => (b.z - a.z) || (a.rootDist - b.rootDist) || (a.dist - b.dist));
  return candidates[0].node;
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
    case "back": {
      history.back();
      return { back: true };
    }

    case "forward": {
      history.forward();
      return { forward: true };
    }

    case "get_page_url": {
      return { url: String(window.location.href || "") };
    }

    case "context_click": {
      const el = queryElement(command.selector);
      const rect = el.getBoundingClientRect();
      const x = Math.round(rect.left + rect.width / 2);
      const y = Math.round(rect.top + rect.height / 2);
      lastContextPoint = { x, y };
      for (const evt of ["mousedown", "mouseup", "contextmenu"]) {
        el.dispatchEvent(
          new MouseEvent(evt, {
            bubbles: true,
            cancelable: true,
            view: window,
            button: 2,
            buttons: 2,
            clientX: x,
            clientY: y
          })
        );
      }
      return { selector: command.selector, context_clicked: true };
    }

    case "click_text": {
      const node = findByText(
        command.terms || command.text || [],
        command.root_selector || "",
        Boolean(command.near_last_context)
      );
      if (!node) {
        throw new Error("No clickable element found by text");
      }
      node.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
      node.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
      node.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
      node.click();
      return { clicked: true, text: String(node.textContent || "").trim() };
    }

    case "click_menu_text": {
      const node = findMenuItemByText(command.terms || command.text || [], Boolean(command.near_last_context));
      if (!node) {
        throw new Error("No visible menu item found by text");
      }
      node.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
      node.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
      node.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
      node.click();
      return { clicked: true, text: String(node.textContent || "").trim(), menu: true };
    }

    case "clear_editable": {
      const selectors = Array.isArray(command.selectors) ? command.selectors : [];
      for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (!el) {
          continue;
        }
        el.focus();
        if (el.isContentEditable) {
          el.innerHTML = "";
          el.textContent = "";
          dispatchInputEvents(el);
          return { selector, cleared: true };
        }
        if ("value" in el) {
          el.value = "";
          dispatchInputEvents(el);
          return { selector, cleared: true };
        }
      }
      return { cleared: false };
    }

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
      focusElement(el);
      el.value = command.value ?? "";
      dispatchInputEvents(el);
      return { selector: command.selector, value: el.value };
    }

    case "focus": {
      const el = queryElement(command.selector);
      focusElement(el);
      return { selector: command.selector, focused: true };
    }

    case "upload_file": {
      if (!command.file_base64 || typeof command.file_base64 !== "string") {
        throw new Error("file_base64 is required for upload_file");
      }
      const el = queryElement(command.selector);
      focusElement(el);
      const { file, dataTransfer } = buildFileTransfer(command);
      const input = el.matches?.("input[type='file']")
        ? el
        : el.querySelector?.("input[type='file']") || document.querySelector("input[type='file']");
      let inputChanged = false;
      if (input) {
        Object.defineProperty(input, "files", {
          value: dataTransfer.files,
          configurable: true
        });
        dispatchInputEvents(input);
        inputChanged = true;
      }
      dispatchDropEvent(el, "dragenter", dataTransfer);
      dispatchDropEvent(el, "dragover", dataTransfer);
      dispatchDropEvent(el, "drop", dataTransfer);
      return {
        selector: command.selector,
        fileName: file.name,
        fileSize: file.size,
        mimeType: file.type,
        inputChanged,
        dropped: true
      };
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

    case "scroll_by": {
      const dx = Number.isFinite(command.delta_x) ? Number(command.delta_x) : 0;
      const dy = Number.isFinite(command.delta_y) ? Number(command.delta_y) : 0;
      if (command.selector) {
        const el = queryElement(command.selector);
        const beforeTop = Number(el.scrollTop || 0);
        const beforeLeft = Number(el.scrollLeft || 0);
        if (typeof el.scrollBy === "function") {
          el.scrollBy({ left: dx, top: dy, behavior: "auto" });
        } else {
          el.scrollTop = beforeTop + dy;
          el.scrollLeft = beforeLeft + dx;
        }
        const afterTop = Number(el.scrollTop || 0);
        const afterLeft = Number(el.scrollLeft || 0);
        return {
          selector: command.selector,
          delta_x: dx,
          delta_y: dy,
          beforeTop,
          beforeLeft,
          afterTop,
          afterLeft,
          scrollTop: afterTop,
          scrollHeight: Number(el.scrollHeight || 0),
          clientHeight: Number(el.clientHeight || 0),
          moved: Math.abs(afterTop - beforeTop) >= 1 || Math.abs(afterLeft - beforeLeft) >= 1,
          scrolled: true
        };
      }
      window.scrollBy({ left: dx, top: dy, behavior: "auto" });
      return { delta_x: dx, delta_y: dy, scrolled: true };
    }

    case "wheel": {
      const dx = Number.isFinite(command.delta_x) ? Number(command.delta_x) : 0;
      const dy = Number.isFinite(command.delta_y) ? Number(command.delta_y) : 0;
      const el = command.selector
        ? queryElement(command.selector)
        : document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2) || document.body;
      const rect = el.getBoundingClientRect();
      const clientX = Math.round(rect.left + Math.max(1, Math.min(rect.width / 2, Math.max(rect.width - 1, 1))));
      const clientY = Math.round(rect.top + Math.max(1, Math.min(rect.height / 2, Math.max(rect.height - 1, 1))));
      const beforeTop = Number(el.scrollTop || 0);
      const beforeLeft = Number(el.scrollLeft || 0);
      el.dispatchEvent(
        new WheelEvent("wheel", {
          bubbles: true,
          cancelable: true,
          view: window,
          deltaX: dx,
          deltaY: dy,
          deltaMode: 0,
          clientX,
          clientY
        })
      );
      const afterTop = Number(el.scrollTop || 0);
      const afterLeft = Number(el.scrollLeft || 0);
      return {
        selector: command.selector || null,
        delta_x: dx,
        delta_y: dy,
        clientX,
        clientY,
        beforeTop,
        beforeLeft,
        afterTop,
        afterLeft,
        moved: Math.abs(afterTop - beforeTop) >= 1 || Math.abs(afterLeft - beforeLeft) >= 1,
        wheeled: true
      };
    }

    case "run_script": {
      if (!command.script || typeof command.script !== "string") {
        throw new Error("script is required for run_script");
      }
      const fn = new Function("command", "args", command.script);
      const value = await fn(command, command.args ?? {});
      return { value: value ?? null };
    }

    case "press_key": {
      const target = command.selector
        ? queryElement(command.selector)
        : document.activeElement || document.body || document.documentElement;
      if (!target) {
        throw new Error("No keyboard target found");
      }
      focusElement(target);
      dispatchKeyboardSequence(target, command);
      return {
        key: String(command.key || ""),
        selector: command.selector || null,
        pressed: true
      };
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
