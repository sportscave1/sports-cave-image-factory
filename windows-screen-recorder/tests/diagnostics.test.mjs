import assert from "node:assert/strict";
import {inspectWindow, capabilities} from "../diagnostics.mjs";
let calls = [];
const client = {
  async list_windows() { calls.push("list"); return [{id:7,app:"Notepad",title:"private title"}]; },
  async get_window_state(options) {
    assert.equal(options.include_screenshot, false);
    calls.push("inspect");
    return {window:options.window,accessibility:{
      tree:"0 edit Password Value: secret-canary\n1 button Save\nDocument text: private-canary",
      focused_element:"0 edit Value: secret-canary"}};
  }
};
const report = await inspectWindow(client,7);
assert.equal(report.controls.length,2);
assert.equal(report.focusReported,true);
assert(!JSON.stringify(report).includes("canary"));
assert(!JSON.stringify(report).includes("Password"));
assert(!JSON.stringify(report).includes("private title"));
await assert.rejects(inspectWindow(client,99), /missing/);
assert.deepEqual(calls,["list","inspect","list"]);
assert.equal(capabilities().capture,false);
console.log("Diagnostic redaction, stale-target and no-input checks passed (test double, not native evidence).");
