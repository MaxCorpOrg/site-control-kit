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

function focusElement(element) {
  if (typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
  }
  if (typeof element.focus === "function") {
    element.focus();
  }
}

function elementCenter(element) {
  const rect = element.getBoundingClientRect();
  return {
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top + rect.height / 2)
  };
}

function dispatchPointerEvent(element, type, init) {
  if (typeof window.PointerEvent === "function") {
    element.dispatchEvent(new PointerEvent(type, init));
    return;
  }
  if (type.startsWith("pointer")) {
    return;
  }
  element.dispatchEvent(new MouseEvent(type, init));
}

function dispatchMouseClickSequence(element, options = {}) {
  const button = Number.isFinite(options.button) ? Number(options.button) : 0;
  const buttons = Number.isFinite(options.buttons) ? Number(options.buttons) : (button === 2 ? 2 : 1);
  const { x, y } = elementCenter(element);
  const common = {
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    button,
    buttons,
    clientX: x,
    clientY: y,
    pointerId: 1,
    pointerType: "mouse",
    isPrimary: true
  };

  if (!options.skipFocus) {
    focusElement(element);
  }

  for (const type of ["pointerover", "pointerenter", "mouseover", "mouseenter", "pointermove", "mousemove"]) {
    dispatchPointerEvent(element, type, common);
  }

  for (const type of ["pointerdown", "mousedown"]) {
    dispatchPointerEvent(element, type, common);
  }

  for (const type of ["pointerup", "mouseup"]) {
    dispatchPointerEvent(element, type, common);
  }

  if (button === 2) {
    dispatchPointerEvent(element, "contextmenu", common);
    return { x, y };
  }

  if (typeof element.click === "function") {
    element.click();
  } else {
    dispatchPointerEvent(element, "click", common);
  }
  return { x, y };
}

function dispatchWheelSequence(target, deltaX, deltaY) {
  const { x, y } = elementCenter(target);
  const init = {
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    clientX: x,
    clientY: y,
    deltaX,
    deltaY,
    deltaMode: typeof window.WheelEvent === "function" ? window.WheelEvent.DOM_DELTA_PIXEL : 0
  };
  if (typeof window.WheelEvent === "function") {
    target.dispatchEvent(new WheelEvent("wheel", init));
  } else {
    target.dispatchEvent(new Event("wheel", { bubbles: true, cancelable: true }));
  }
}

function isScrollableElement(node) {
  if (!(node instanceof Element)) {
    return false;
  }
  const canScrollY = Number(node.scrollHeight || 0) > Number(node.clientHeight || 0) + 2;
  const canScrollX = Number(node.scrollWidth || 0) > Number(node.clientWidth || 0) + 2;
  return (canScrollY || canScrollX) && (Number(node.clientHeight || 0) > 0 || Number(node.clientWidth || 0) > 0);
}

function preferredScrollableElement(startNode, rootNode) {
  let node = startNode;
  let match = null;
  while (node) {
    if (node instanceof Element) {
      if (isScrollableElement(node)) {
        match = node;
      }
      if (node === rootNode) {
        break;
      }
    }
    node = node?.parentElement || null;
  }
  if (match) {
    return match;
  }
  return isScrollableElement(rootNode) ? rootNode : rootNode;
}

function resolveScrollTargets(element) {
  const point = elementCenter(element);
  if (isScrollableElement(element)) {
    return { point, wheelTarget: element, scrollTarget: element };
  }
  const pointTarget = document.elementFromPoint(point.x, point.y);
  const wheelTarget =
    pointTarget instanceof Element && element.contains(pointTarget)
      ? pointTarget
      : element;
  const scrollTarget = preferredScrollableElement(wheelTarget, element);
  const effectiveWheelTarget = scrollTarget === element ? element : wheelTarget;
  return { point, wheelTarget: effectiveWheelTarget, scrollTarget };
}

async function performSteppedScroll(wheelTarget, scrollTarget, deltaX, deltaY) {
  const total = Math.max(Math.abs(deltaX), Math.abs(deltaY));
  const steps = Math.max(1, Math.ceil(total / 160));
  const stepX = deltaX / steps;
  const stepY = deltaY / steps;
  for (let i = 0; i < steps; i += 1) {
    dispatchWheelSequence(wheelTarget, stepX, stepY);
    if (typeof scrollTarget.scrollBy === "function") {
      scrollTarget.scrollBy({ left: stepX, top: stepY, behavior: "auto" });
    } else {
      scrollTarget.scrollTop = Number(scrollTarget.scrollTop || 0) + stepY;
      scrollTarget.scrollLeft = Number(scrollTarget.scrollLeft || 0) + stepX;
    }
    scrollTarget.dispatchEvent(new Event("scroll", { bubbles: false }));
    window.dispatchEvent(new Event("scroll"));
    await wait(24);
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

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeTelegramUsername(value) {
  const text = compactText(value);
  if (!text) {
    return "";
  }
  const patterns = [
    /https?:\/\/t\.me\/([A-Za-z0-9_]{5,32})/i,
    /t\.me\/([A-Za-z0-9_]{5,32})/i,
    /@([A-Za-z0-9_]{5,32})/i
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) {
      continue;
    }
    const username = match[1];
    if (/[A-Za-z]/.test(username)) {
      return `@${username}`;
    }
  }
  return "";
}

function firstText(root, selector) {
  const node = root && typeof root.querySelector === "function" ? root.querySelector(selector) : null;
  return compactText(node ? node.innerText || node.textContent || "" : "");
}

function telegramAuthorFromElement(element, point = null) {
  if (!element || typeof element.closest !== "function") {
    return null;
  }

  let avatar = element.closest(".Avatar[data-peer-id], .bubbles-group-avatar[data-peer-id]");
  let group =
    element.closest(".sender-group-container, [id^='message-group-'], .Message, .message-list-item") ||
    (avatar && avatar.closest(".sender-group-container, [id^='message-group-'], .Message, .message-list-item"));

  if (!avatar && !point && group && typeof group.querySelector === "function") {
    avatar = group.querySelector(".Avatar[data-peer-id], .bubbles-group-avatar[data-peer-id]");
  }
  if (!avatar) {
    return null;
  }

  const peerId = compactText(avatar.getAttribute("data-peer-id"));
  if (!peerId || peerId.startsWith("-")) {
    return null;
  }
  const senderGroup = avatar.closest(".sender-group-container, [id^='message-group-']");
  const messageAncestor = avatar.closest(".Message, .message-list-item");
  if (senderGroup && messageAncestor && senderGroup.contains(messageAncestor)) {
    return null;
  }
  if (!group) {
    group = senderGroup || avatar.closest(".Message, .message-list-item") || avatar.parentElement;
  }

  const visible = interactableRect(avatar);
  if (!visible) {
    return null;
  }

  const imageAltNode = avatar.querySelector("img[alt]");
  const imageAlt = compactText(imageAltNode ? imageAltNode.getAttribute("alt") : "");
  const name =
    firstText(group, ".sender-title") ||
    firstText(group, ".message-title-name") ||
    firstText(group, ".peer-title-inner") ||
    firstText(group, ".peer-title") ||
    imageAlt ||
    compactText(avatar.getAttribute("aria-label") || avatar.getAttribute("title"));
  const role =
    firstText(group, ".admin-title-badge") ||
    firstText(group, ".bubble-name-rank") ||
    firstText(group, ".message-title-meta") ||
    "";
  const authorText = [
    firstText(group, ".sender-title"),
    firstText(group, ".message-title-name"),
    firstText(group, ".peer-title-inner"),
    firstText(group, ".peer-title"),
    imageAlt,
    compactText(avatar.getAttribute("aria-label") || avatar.getAttribute("title"))
  ].join(" ");
  const username = normalizeTelegramUsername(authorText);
  const { rect } = visible;

  return {
    node: avatar,
    peer_id: peerId,
    name,
    role,
    username,
    point,
    rect: {
      left: Math.round(rect.left),
      top: Math.round(rect.top),
      right: Math.round(rect.right),
      bottom: Math.round(rect.bottom),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    }
  };
}

function telegramStickyAuthorCandidates() {
  const root =
    document.querySelector("#column-center, .chat.tabs-tab.active, #column-center .MessageList, .MessageList, .chat.tabs-tab.active .bubbles, #column-center .bubbles") ||
    document.body ||
    document.documentElement;
  const rootRect = root.getBoundingClientRect();
  const left = Math.max(0, rootRect.left);
  const right = Math.min(window.innerWidth, rootRect.right || window.innerWidth);
  const bottom = Math.min(window.innerHeight, rootRect.bottom || window.innerHeight);
  const width = Math.max(1, right - left);
  const xOffsets = [
    28,
    34,
    42,
    50,
    58,
    70,
    86,
    108,
    136,
    174,
    186,
    198,
    210,
    Math.round(width * 0.18),
    Math.round(width * 0.20),
    Math.round(width * 0.22),
    Math.round(width * 0.28)
  ];
  const yOffsets = [34, 46, 58, 70, 82, 96, 112, 136, 168, 210, 280];
  const candidates = [];
  const seen = new Set();

  function push(candidate, source, sampleIndex) {
    if (!candidate || seen.has(candidate.peer_id)) {
      return;
    }
    seen.add(candidate.peer_id);
    candidates.push({ ...candidate, source, sample_index: sampleIndex });
  }

  let sampleIndex = 0;
  for (const yOffset of yOffsets) {
    const y = Math.round(bottom - yOffset);
    if (y <= 0 || y >= window.innerHeight) {
      continue;
    }
    for (const xOffset of xOffsets) {
      const x = Math.round(left + xOffset);
      if (x <= 0 || x >= window.innerWidth) {
        continue;
      }
      const stack = typeof document.elementsFromPoint === "function" ? document.elementsFromPoint(x, y) : [];
      for (const element of stack) {
        push(telegramAuthorFromElement(element, { x, y }), "point", sampleIndex);
      }
      sampleIndex += 1;
    }
  }

  const visibleAvatars = Array.from(
    root.querySelectorAll(
      ".sender-group-container .Avatar[data-peer-id], .MessageList .Avatar[data-peer-id], .bubbles-group-avatar[data-peer-id]"
    )
  );
  visibleAvatars
    .map((node) => telegramAuthorFromElement(node))
    .filter(Boolean)
    .sort((a, b) => (b.rect.bottom - a.rect.bottom) || (a.rect.left - b.rect.left))
    .forEach((candidate, index) => push(candidate, "visible_fallback", sampleIndex + index));

  candidates.sort((a, b) => {
    const aSmall = a.rect.width < 30 || a.rect.height < 30 ? 1 : 0;
    const bSmall = b.rect.width < 30 || b.rect.height < 30 ? 1 : 0;
    return (aSmall - bSmall) || (a.sample_index - b.sample_index) || (b.rect.bottom - a.rect.bottom) || (a.rect.left - b.rect.left);
  });
  return candidates;
}

function publicTelegramAuthor(candidate, clicked = false) {
  if (!candidate) {
    return null;
  }
  return {
    found: true,
    clicked,
    peer_id: candidate.peer_id,
    name: candidate.name,
    role: candidate.role,
    username: candidate.username,
    source: candidate.source,
    point: candidate.point,
    rect: candidate.rect
  };
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
      const { x, y } = dispatchMouseClickSequence(el, { button: 2, buttons: 2 });
      lastContextPoint = { x, y };
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
      dispatchMouseClickSequence(node);
      return { clicked: true, text: String(node.textContent || "").trim() };
    }

    case "click_menu_text": {
      const node = findMenuItemByText(command.terms || command.text || [], Boolean(command.near_last_context));
      if (!node) {
        throw new Error("No visible menu item found by text");
      }
      dispatchMouseClickSequence(node);
      return { clicked: true, text: String(node.textContent || "").trim(), menu: true };
    }

    case "telegram_sticky_author": {
      const expectedPeerId = compactText(command.expected_peer_id || "");
      const candidates = telegramStickyAuthorCandidates();
      const shouldInteract = Boolean(command.click) || Boolean(command.context_click);
      const pointIconCandidates = candidates.filter((candidate) => (
        candidate.source === "point" && candidate.rect.width >= 30 && candidate.rect.height >= 30
      ));
      const candidatePool = shouldInteract ? pointIconCandidates : (pointIconCandidates.length ? pointIconCandidates : candidates);
      const selected = expectedPeerId
        ? candidatePool.find((candidate) => candidate.peer_id === expectedPeerId) || null
        : candidatePool[0] || null;
      if (!selected) {
        return {
          found: false,
          clicked: false,
          context_clicked: false,
          candidates: candidates.slice(0, 5).map((candidate) => publicTelegramAuthor(candidate, false))
        };
      }
      const click = Boolean(command.click);
      const contextClick = Boolean(command.context_click);
      if (click) {
        const { x, y } = dispatchMouseClickSequence(selected.node, { skipFocus: true });
        lastContextPoint = { x, y };
      }
      if (contextClick) {
        const { x, y } = dispatchMouseClickSequence(selected.node, { button: 2, buttons: 2, skipFocus: true });
        lastContextPoint = { x, y };
      }
      return {
        ...publicTelegramAuthor(selected, click || contextClick),
        context_clicked: contextClick,
        candidates: candidates.slice(0, 5).map((candidate) => publicTelegramAuthor(candidate, false))
      };
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
      dispatchMouseClickSequence(el);
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
        focusElement(el);
        const { wheelTarget, scrollTarget } = resolveScrollTargets(el);
        await performSteppedScroll(wheelTarget, scrollTarget, dx, dy);
        return {
          selector: command.selector,
          delta_x: dx,
          delta_y: dy,
          wheelTarget: wheelTarget.className || wheelTarget.tagName,
          scrollTarget: scrollTarget.className || scrollTarget.tagName,
          scrollTop: Number(scrollTarget.scrollTop || 0),
          scrolled: true
        };
      }
      const pageTarget = document.scrollingElement || document.documentElement || document.body;
      await performSteppedScroll(pageTarget, pageTarget, dx, dy);
      return { delta_x: dx, delta_y: dy, scrolled: true };
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
