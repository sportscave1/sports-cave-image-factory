/**
 * Supported Computer Use runtime only. Pass the initialized sky client.
 * No hooks, subscriptions, input methods, activation, screenshots or file writes.
 * No document contents, field values, names or window titles leave this module.
 */
export function capabilities() {
  return {
    format: "sports-cave.desktop", version: 1,
    inspection: "selected-window snapshot through injected supported sky runtime",
    capture: false, playback: false, eventSubscriptions: false,
    passwordProperty: "not exposed by this runtime's structured API",
    dpiAndMonitorGeometry: "not exposed by this runtime's text-only API",
    productionIntegration: false
  };
}

export async function listWindows(client) {
  return (await client.list_windows()).map(({id, app}) => ({id, app}));
}

export async function inspectWindow(client, id) {
  if (!Number.isSafeInteger(id)) throw Error("Select a window ID from listWindows.");
  const matches = (await client.list_windows()).filter(w => w.id === id);
  if (matches.length !== 1) throw Error("Window missing or ambiguous; select again.");
  if (/OpenAI|ChatGPT|powershell|cmd\.exe|WindowsTerminal|LockApp/i.test(matches[0].app))
    throw Error("This application is outside diagnostic scope.");
  const start = performance.now();
  const state = await client.get_window_state({
    window: matches[0], include_screenshot: false, include_text: true
  });
  const controls = [];
  // Parse only indexed control lines; discard every value and free document text.
  for (const line of (state.accessibility?.tree || "").split("\n")) {
    const match = line.match(/^\s*(\d+)\s+(button|edit|document|menu item|menu bar|list|tab item|tab|check box|combo box|region|window)\b/);
    if (!match) continue;
    controls.push({index: Number(match[1]), role: match[2], disabled: line.includes("(disabled)")});
    if (controls.length === 100) break;
  }
  return {
    app: state.window.app, window: state.window.id,
    elapsed_ms: Math.round(performance.now() - start),
    accessibilityPresent: state.accessibility !== null,
    focusReported: Boolean(state.accessibility?.focused_element),
    controls, limit: 100, capabilities: capabilities()
  };
}
