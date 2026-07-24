(() => {
  if (globalThis.__siteControlAgentDom) {
    return;
  }

  const refEntries = new Map();
  const elementRefs = new WeakMap();
  let nextRef = 1;

  const INTERACTIVE_SELECTOR = [
    "a[href]",
    "button",
    "input",
    "textarea",
    "select",
    "summary",
    "[role]",
    "[contenteditable='true']",
    "[contenteditable='']",
    "[tabindex]",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "output",
    "[aria-live]",
    "p",
    "li",
    "td",
    "th"
  ].join(",");

  class LocatorError extends Error {
    constructor(message, code, matches = []) {
      super(message);
      this.name = "LocatorError";
      this.code = code;
      this.candidate_count = matches.length;
      this.candidates = matches.slice(0, 10).map(({ element, healed = false }) => ({
        ...briefElement(element),
        healed
      }));
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function normalize(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function normalizedMatch(actual, expected, exact) {
    const haystack = normalize(actual).toLocaleLowerCase();
    const needle = normalize(expected).toLocaleLowerCase();
    return exact ? haystack === needle : haystack.includes(needle);
  }

  function attrSelector(name, value) {
    const escaped = String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    return `[${name}="${escaped}"]`;
  }

  function collectRoots(start = document) {
    const roots = [];
    const pending = [start];
    const visited = new Set();
    while (pending.length) {
      const root = pending.shift();
      if (!root || visited.has(root)) {
        continue;
      }
      visited.add(root);
      roots.push(root);
      let nodes = [];
      try {
        nodes = Array.from(root.querySelectorAll("*"));
      } catch {
        nodes = [];
      }
      for (const node of nodes) {
        if (node.shadowRoot?.mode === "open") {
          pending.push(node.shadowRoot);
        }
      }
    }
    return roots;
  }

  function queryAllDeep(selector, start = document) {
    if (!selector || typeof selector !== "string") {
      throw new LocatorError("CSS selector is required", "invalid_locator");
    }
    const found = [];
    const seen = new Set();
    for (const root of collectRoots(start)) {
      let nodes;
      try {
        nodes = root.querySelectorAll(selector);
      } catch (error) {
        throw new LocatorError(
          `Invalid CSS selector ${JSON.stringify(selector)}: ${String(error?.message || error)}`,
          "invalid_locator"
        );
      }
      for (const node of nodes) {
        if (!seen.has(node)) {
          seen.add(node);
          found.push(node);
        }
      }
    }
    return found;
  }

  function implicitRole(element) {
    const tag = String(element?.tagName || "").toLowerCase();
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "textarea") return "textbox";
    if (tag === "select") return element.multiple ? "listbox" : "combobox";
    if (tag === "summary") return "button";
    if (/^h[1-6]$/.test(tag)) return "heading";
    if (tag === "output" || element?.hasAttribute("aria-live")) return "status";
    if (tag === "p") return "paragraph";
    if (tag === "li") return "listitem";
    if (tag === "td") return "cell";
    if (tag === "th") return "columnheader";
    if (tag === "img") return "img";
    if (tag === "input") {
      const type = String(element.type || "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "range") return "slider";
      if (type === "number") return "spinbutton";
      if (type === "search") return "searchbox";
      if (!["hidden", "file"].includes(type)) return "textbox";
    }
    return "";
  }

  function roleOf(element) {
    const explicit = normalize(element?.getAttribute?.("role")).split(" ")[0];
    return explicit || implicitRole(element);
  }

  function findByIdDeep(id) {
    const documentMatch = document.getElementById(id);
    if (documentMatch) {
      return documentMatch;
    }
    const matches = queryAllDeep(attrSelector("id", id));
    return matches.length === 1 ? matches[0] : null;
  }

  function accessibleName(element) {
    if (!element) return "";
    const ariaLabel = normalize(element.getAttribute?.("aria-label"));
    if (ariaLabel) return ariaLabel;
    const labelledBy = normalize(element.getAttribute?.("aria-labelledby"));
    if (labelledBy) {
      const labelText = labelledBy
        .split(" ")
        .map((id) => findByIdDeep(id))
        .filter(Boolean)
        .map((node) => normalize(node.textContent))
        .join(" ");
      if (labelText) return normalize(labelText).slice(0, 240);
    }
    if (element.labels?.length) {
      const labelText = Array.from(element.labels)
        .map((label) => normalize(label.textContent))
        .filter(Boolean)
        .join(" ");
      if (labelText) return normalize(labelText).slice(0, 240);
    }
    const alt = normalize(element.getAttribute?.("alt"));
    if (alt) return alt;
    const type = String(element.type || "").toLowerCase();
    if (["button", "submit", "reset"].includes(type) && normalize(element.value)) {
      return normalize(element.value);
    }
    const title = normalize(element.getAttribute?.("title"));
    if (title) return title;
    return normalize(element.innerText ?? element.textContent).slice(0, 240);
  }

  function isVisible(element) {
    if (!element?.isConnected) return false;
    const rect = element.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return false;
    let current = element;
    while (current) {
      const style = getComputedStyle(current);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        style.visibility === "collapse" ||
        Number(style.opacity || "1") === 0
      ) {
        return false;
      }
      current = current.parentElement || current.getRootNode?.()?.host || null;
    }
    return true;
  }

  function isEnabled(element) {
    if (!element || element.matches?.(":disabled")) return false;
    return normalize(element.getAttribute?.("aria-disabled")).toLowerCase() !== "true";
  }

  function isEditable(element) {
    if (!isEnabled(element)) return false;
    if (element.isContentEditable) return true;
    if (!("value" in element) || element.readOnly) return false;
    const tag = String(element.tagName || "").toLowerCase();
    const type = String(element.type || "").toLowerCase();
    const excluded = new Set([
      "button",
      "checkbox",
      "color",
      "file",
      "hidden",
      "image",
      "radio",
      "range",
      "reset",
      "submit"
    ]);
    return tag === "textarea" || (tag === "input" && !excluded.has(type));
  }

  function elementFromPointDeep(x, y) {
    let current = document.elementFromPoint(x, y);
    const visited = new Set();
    while (current?.shadowRoot && !visited.has(current)) {
      visited.add(current);
      const nested = current.shadowRoot.elementFromPoint?.(x, y);
      if (!nested || nested === current) break;
      current = nested;
    }
    return current;
  }

  function composedContains(container, candidate) {
    let current = candidate;
    while (current) {
      if (current === container) return true;
      current = current.parentElement || current.getRootNode?.()?.host || null;
    }
    return false;
  }

  function receivesEvents(element) {
    if (!isVisible(element)) return false;
    const rect = element.getBoundingClientRect();
    const x = Math.max(0, Math.min(innerWidth - 1, rect.left + rect.width / 2));
    const y = Math.max(0, Math.min(innerHeight - 1, rect.top + rect.height / 2));
    const top = elementFromPointDeep(x, y);
    return Boolean(top && (composedContains(element, top) || composedContains(top, element)));
  }

  function actionability(element) {
    return {
      attached: Boolean(element?.isConnected),
      visible: isVisible(element),
      enabled: isEnabled(element),
      editable: isEditable(element),
      receives_events: receivesEvents(element)
    };
  }

  function fingerprint(element) {
    return {
      id: normalize(element.id),
      test_id: normalize(
        element.getAttribute?.("data-testid") ||
          element.getAttribute?.("data-test-id") ||
          element.getAttribute?.("data-test")
      ),
      role: roleOf(element),
      name: accessibleName(element),
      placeholder: normalize(element.getAttribute?.("placeholder")),
      tag: String(element.tagName || "").toLowerCase()
    };
  }

  function refFor(element) {
    const existing = elementRefs.get(element);
    if (existing) return existing;
    const ref = `e${nextRef}`;
    nextRef += 1;
    elementRefs.set(element, ref);
    refEntries.set(ref, { element, fingerprint: fingerprint(element) });
    return ref;
  }

  function briefElement(element) {
    const fp = fingerprint(element);
    return {
      ref: elementRefs.get(element) || null,
      role: fp.role || fp.tag || "element",
      name: fp.name,
      tag: fp.tag,
      placeholder: fp.placeholder,
      test_id: fp.test_id,
      visible: isVisible(element),
      enabled: isEnabled(element)
    };
  }

  function healRef(ref) {
    const entry = refEntries.get(ref);
    if (!entry) {
      throw new LocatorError(
        `Unknown element ref: ${ref}. Take a fresh snapshot.`,
        "unknown_ref"
      );
    }
    if (entry.element?.isConnected) {
      return { element: entry.element, healed: false };
    }
    const fp = entry.fingerprint || {};
    const groups = [];
    if (fp.id) groups.push(queryAllDeep(attrSelector("id", fp.id)));
    if (fp.test_id) {
      groups.push(
        queryAllDeep(
          [
            attrSelector("data-testid", fp.test_id),
            attrSelector("data-test-id", fp.test_id),
            attrSelector("data-test", fp.test_id)
          ].join(",")
        )
      );
    }
    if (fp.role && fp.name) {
      groups.push(
        queryAllDeep(INTERACTIVE_SELECTOR).filter(
          (element) =>
            roleOf(element) === fp.role &&
            normalizedMatch(accessibleName(element), fp.name, true)
        )
      );
    }
    if (fp.placeholder) {
      groups.push(queryAllDeep(attrSelector("placeholder", fp.placeholder)));
    }
    for (const candidates of groups) {
      const unique = Array.from(new Set(candidates));
      if (unique.length === 1) {
        entry.element = unique[0];
        entry.fingerprint = fingerprint(unique[0]);
        elementRefs.set(unique[0], ref);
        return { element: unique[0], healed: true };
      }
    }
    const all = groups.flat().map((element) => ({ element, healed: false }));
    throw new LocatorError(
      `Element ref ${ref} is detached and could not be healed uniquely.`,
      "ref_healing_failed",
      all
    );
  }

  function rootsForLocator(locator) {
    if (!locator?.root_selector) return [document];
    const roots = queryAllDeep(locator.root_selector);
    if (!roots.length) {
      throw new LocatorError(
        `Locator root not found: ${locator.root_selector}`,
        "root_not_found"
      );
    }
    return roots;
  }

  function candidatesForLocator(locator) {
    if (!locator || typeof locator !== "object") {
      throw new LocatorError("locator is required", "invalid_locator");
    }
    const strategy = String(locator.strategy || "");
    const value = String(locator.value ?? "");
    const exact = Boolean(locator.exact);
    if (!strategy || !value) {
      throw new LocatorError(
        "locator.strategy and locator.value are required",
        "invalid_locator"
      );
    }
    if (strategy === "ref") {
      const resolved = healRef(value);
      return [{ element: resolved.element, healed: resolved.healed }];
    }

    const found = [];
    const seen = new Set();
    const append = (element) => {
      if (element && !seen.has(element)) {
        seen.add(element);
        found.push({ element, healed: false });
      }
    };
    for (const root of rootsForLocator(locator)) {
      let candidates = [];
      if (strategy === "css") {
        candidates = queryAllDeep(value, root);
      } else if (strategy === "role") {
        candidates = queryAllDeep(INTERACTIVE_SELECTOR, root).filter((element) => {
          if (roleOf(element) !== value.toLowerCase()) return false;
          return !locator.name || normalizedMatch(accessibleName(element), locator.name, exact);
        });
      } else if (strategy === "text") {
        candidates = queryAllDeep(INTERACTIVE_SELECTOR, root).filter((element) =>
          normalizedMatch(element.innerText ?? element.textContent, value, exact)
        );
      } else if (strategy === "label") {
        const labels = queryAllDeep("label", root).filter((element) =>
          normalizedMatch(element.textContent, value, exact)
        );
        candidates = labels.map((label) => label.control).filter(Boolean);
        candidates.push(
          ...queryAllDeep("[aria-label]", root).filter((element) =>
            normalizedMatch(element.getAttribute("aria-label"), value, exact)
          )
        );
      } else if (strategy === "placeholder") {
        candidates = queryAllDeep("[placeholder]", root).filter((element) =>
          normalizedMatch(element.getAttribute("placeholder"), value, exact)
        );
      } else if (strategy === "test_id") {
        candidates = queryAllDeep(
          "[data-testid],[data-test-id],[data-test]",
          root
        ).filter((element) =>
          [
            element.getAttribute("data-testid"),
            element.getAttribute("data-test-id"),
            element.getAttribute("data-test")
          ].some((candidate) => normalizedMatch(candidate, value, true))
        );
      } else {
        throw new LocatorError(
          `Unsupported locator strategy: ${strategy}`,
          "unsupported_locator"
        );
      }
      candidates.forEach(append);
    }
    return found;
  }

  function resolveLocator(locator, options = {}) {
    const matches = candidatesForLocator(locator);
    const visibleOnly = options.visible_only !== false;
    const filtered = visibleOnly
      ? matches.filter(({ element }) => isVisible(element))
      : matches;
    const nth = Number.isInteger(locator.nth) ? locator.nth : null;
    if (nth !== null) {
      if (!filtered[nth]) {
        throw new LocatorError(
          `Locator matched ${filtered.length} elements; nth=${nth} is unavailable`,
          "nth_out_of_range",
          filtered
        );
      }
      const chosen = filtered[nth];
      return {
        ...chosen,
        ref: refFor(chosen.element),
        match_count: filtered.length,
        candidates: filtered.slice(0, 10).map(({ element }) => briefElement(element))
      };
    }
    if (!filtered.length) {
      throw new LocatorError(
        `No element matched locator ${JSON.stringify(locator)}`,
        "no_match",
        matches
      );
    }
    if (filtered.length > 1) {
      throw new LocatorError(
        `Locator matched ${filtered.length} elements. Add exact matching, nth, or a narrower locator.`,
        "ambiguous_match",
        filtered
      );
    }
    const chosen = filtered[0];
    return {
      ...chosen,
      ref: refFor(chosen.element),
      match_count: 1,
      candidates: [briefElement(chosen.element)]
    };
  }

  function rectSignature(element) {
    const rect = element.getBoundingClientRect();
    return [rect.x, rect.y, rect.width, rect.height]
      .map((value) => Math.round(value * 10) / 10)
      .join(":");
  }

  async function waitFor(locator, options = {}) {
    const timeoutMs = Math.max(0, Number(options.timeout_ms ?? 10000) || 10000);
    const pollMs = Math.max(25, Number(options.poll_ms ?? 100) || 100);
    const stableMs = Math.max(50, Number(options.stable_ms ?? 150) || 150);
    const state = String(options.state || "visible");
    const deadline = Date.now() + timeoutMs;
    let stableSince = 0;
    let lastSignature = "";
    let lastError = null;
    let healedDuringWait = false;

    while (Date.now() <= deadline) {
      let resolved = null;
      let missing = false;
      try {
        resolved = resolveLocator(locator, {
          visible_only: !["attached", "detached", "hidden"].includes(state)
        });
      } catch (error) {
        lastError = error;
        missing = ["no_match", "ref_healing_failed", "unknown_ref"].includes(error?.code);
      }
      healedDuringWait = healedDuringWait || Boolean(resolved?.healed);
      if (state === "detached" && missing) {
        return { state, found: false, ref: locator.strategy === "ref" ? locator.value : null };
      }
      if (state === "hidden" && (missing || (resolved && !isVisible(resolved.element)))) {
        return { state, found: Boolean(resolved), ref: resolved?.ref || null };
      }
      if (resolved) {
        const element = resolved.element;
        const checks = actionability(element);
        let ready = false;
        if (state === "attached") ready = element.isConnected;
        else if (state === "visible") ready = checks.visible;
        else if (state === "enabled") ready = checks.visible && checks.enabled;
        else if (state === "editable") ready = checks.visible && checks.editable;
        else if (state === "text") {
          ready =
            checks.visible &&
            normalizedMatch(
              element.innerText ?? element.textContent,
              options.expected_text ?? "",
              Boolean(options.exact)
            );
        } else if (state === "value") {
          ready =
            checks.visible &&
            normalizedMatch(
              element.value ?? "",
              options.expected_value ?? "",
              Boolean(options.exact)
            );
        } else if (state === "stable" || state === "actionable") {
          if (state === "actionable" && checks.visible) {
            element.scrollIntoView?.({ block: "center", inline: "nearest", behavior: "auto" });
          }
          const signature = rectSignature(element);
          if (signature !== lastSignature) {
            lastSignature = signature;
            stableSince = Date.now();
          } else if (!stableSince) {
            stableSince = Date.now();
          }
          const stable = Date.now() - stableSince >= stableMs;
          ready =
            state === "stable"
              ? checks.visible && stable
              : checks.visible && checks.enabled && checks.receives_events && stable;
        } else {
          throw new LocatorError(`Unsupported wait state: ${state}`, "unsupported_wait");
        }
        if (ready) {
          return {
            state,
            found: true,
            ref: resolved.ref,
            healed: healedDuringWait,
            match_count: resolved.match_count,
            candidates: resolved.candidates,
            role: roleOf(element),
            name: accessibleName(element),
            actionability: {
              ...checks,
              stable: state === "stable" || state === "actionable"
            }
          };
        }
      }
      await sleep(pollMs);
    }
    const error = new LocatorError(
      `Timeout after ${timeoutMs}ms waiting for state=${state}.`,
      "wait_timeout"
    );
    error.candidate_count = Number(lastError?.candidate_count || 0);
    error.candidates = Array.isArray(lastError?.candidates)
      ? lastError.candidates.slice(0, 10)
      : [];
    error.last_locator_error = lastError
      ? {
          message: String(lastError.message || lastError),
          code: lastError.code,
          candidate_count: lastError.candidate_count,
          candidates: lastError.candidates
        }
      : null;
    throw error;
  }

  function describeElement(element) {
    const fp = fingerprint(element);
    const ref = refFor(element);
    const checks = actionability(element);
    const value =
      "value" in element &&
      !["password", "hidden"].includes(String(element.type || "").toLowerCase())
        ? normalize(element.value).slice(0, 160)
        : "";
    return {
      ref,
      role: fp.role || fp.tag || "element",
      name: fp.name,
      tag: fp.tag,
      type: normalize(element.getAttribute?.("type")),
      value,
      placeholder: fp.placeholder,
      test_id: fp.test_id,
      visible: checks.visible,
      enabled: checks.enabled,
      editable: checks.editable,
      source: "dom"
    };
  }

  function formatSnapshotLine(item) {
    const parts = [`[${item.ref}]`, item.role];
    if (item.name) parts.push(JSON.stringify(item.name));
    if (item.value) parts.push(`value=${JSON.stringify(item.value)}`);
    if (item.placeholder) parts.push(`placeholder=${JSON.stringify(item.placeholder)}`);
    if (!item.enabled) parts.push("disabled");
    if (item.editable) parts.push("editable");
    return parts.join(" ");
  }

  function snapshot(options = {}) {
    const requestedLimit = Number(options.limit || 200);
    const limit = Number.isFinite(requestedLimit)
      ? Math.max(1, Math.min(1000, requestedLimit))
      : 200;
    const includeHidden = Boolean(options.include_hidden);
    const roots = options.root_selector ? queryAllDeep(options.root_selector) : [document];
    if (!roots.length) {
      throw new LocatorError(
        `Snapshot root not found: ${options.root_selector}`,
        "root_not_found"
      );
    }
    const nodes = [];
    const seen = new Set();
    for (const root of roots) {
      for (const element of queryAllDeep(INTERACTIVE_SELECTOR, root)) {
        if (seen.has(element) || (!includeHidden && !isVisible(element))) continue;
        seen.add(element);
        nodes.push(element);
      }
    }
    const elements = nodes.slice(0, limit).map(describeElement);
    return {
      url: String(location.href),
      title: String(document.title || ""),
      frame_name: String(window.name || ""),
      generated_at: new Date().toISOString(),
      element_count: elements.length,
      truncated: nodes.length > limit,
      lines: elements.map(formatSnapshotLine),
      elements,
      source: "dom"
    };
  }

  globalThis.__siteControlAgentDom = {
    LocatorError,
    accessibleName,
    actionability,
    isEditable,
    isEnabled,
    isVisible,
    queryAllDeep,
    refFor,
    resolveLocator,
    roleOf,
    snapshot,
    waitFor
  };
})();
