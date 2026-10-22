"""One browser, one run, fixed action dispatch. No app/worker imports."""
import asyncio
import contextlib
import copy
import os
import re
import time
import json
from pathlib import Path

from playwright.async_api import async_playwright
from .schema import Invalid, safe_url, validate_task, resolve_task
from .store import Store

AUTH_PATH = re.compile(r"login|log-in|signin|sign-in|oauth|authorize|authentication|/auth(?:/|$)", re.I)

class TargetProblem(Exception):
    pass

class Runner:
    def __init__(self, root, *, headless=False):
        self.store = Store(root)
        self.headless = headless
        self.pw = self.context = self.page = self.job = None
        self.mode = "idle"
        self.message = "Ready. Open the dedicated browser, sign in with recording stopped, then Record."
        self.index = 0
        self.current_action = ""
        self.recording = False
        self.privacy_pause = False
        self.pause_requested = False
        self.can_resume = False
        self.gate = asyncio.Event()
        self.gate.set()
        self.lock = asyncio.Lock()
        self.capture_lock = asyncio.Lock()
        self.draft = self.blank()
        self.last_click = 0
        self.run_id = None
        self.total = 0
        self.state_changed = None
        self.simple_recording = False
        self.recording_started = None
        self.recorded_ms = 0
        self.in_action = False
        self.file_selector = None
        self.selected_upload = None
        from .windows import Vault
        self.vault = Vault(root)
        checkpoint = self.store.root / "recording.json"
        if checkpoint.exists():
            try:
                record = json.loads(checkpoint.read_text(encoding="utf-8"))
                self.draft = validate_task(record["task"])
                if record.get("active"):
                    if len(self.draft["steps"])<500:
                        self.draft["steps"].append({"action":"unsupported","reason":"Recording was interrupted before Stop. Review the final actions before playback."})
                    self.draft = self.store.save(self.draft)
                    self.store.checkpoint(self.draft, False)
                    self.mode = "interrupted"
                    self.message = "Interrupted recording recovered and saved. Nothing was restarted."
                elif self.draft.get("id"):
                    self.draft = self.store.get(self.draft["id"])
            except (ValueError, KeyError):
                self.message = "A recording needs review in Advanced."
        if self.store.journal.exists():
            previous = json.loads(self.store.journal.read_text(encoding="utf-8"))
            if previous.get("status") == "interrupted":
                self.message = previous["message"]

    @staticmethod
    def blank():
        return {"version": 1, "name": "Untitled task", "inputs": [], "steps": []}

    def state(self):
        return {"mode": self.mode, "message": self.message, "step": self.index + 1 if self.total else 0,
                "total": self.total, "action": self.current_action, "can_resume": self.can_resume,
                "browser_open": bool(self.context and self.page and not self.page.is_closed()),
                "recording": self.recording, "privacy_pause": self.privacy_pause,
                "active_task_id": self.draft.get("id") if self.recording or self.mode == "recording_paused" else self.run_id if self.busy() else None,
                "active_task_name": self.draft.get("name") if self.recording or self.mode == "recording_paused" else getattr(self, "run_name", ""),
                "draft": self.draft, "tasks": self.store.list()}

    def notify_state(self):
        if self.state_changed:self.state_changed()

    def busy(self):
        return bool(self.job and not self.job.done())

    async def open_browser(self, url=None):
        if self.busy() or self.recording: raise Invalid("Stop the current run or recording before opening a URL.")
        if url: safe_url(url)
        if self.context and (not self.page or self.page.is_closed()):
            with contextlib.suppress(Exception):await self.context.close()
            self.context=self.page=None
        if not self.context:
            if not self.pw: self.pw = await async_playwright().start()
            options = {}
            # Installed Chrome/Edge is the stable headed Windows runtime; always
            # use our profile, never the user's ordinary browser profile.
            if not self.headless and os.name == "nt":
                if Path("C:/Program Files/Google/Chrome/Application/chrome.exe").is_file():
                    options["channel"] = "chrome"
                elif Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe").is_file():
                    options["channel"] = "msedge"
            self.context = await self.pw.chromium.launch_persistent_context(
                str(self.store.root / "browser-profile"), headless=self.headless,
                viewport={"width": 1280, "height": 800}, accept_downloads=False, **options)
            await self.context.expose_binding("__scRecord", self.record_event)
            await self.context.add_init_script(path=str(Path(__file__).with_name("record.js")))
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            self.page.on("domcontentloaded", lambda: asyncio.create_task(self.loaded()))
            self.page.on("framenavigated", lambda frame: asyncio.create_task(self.navigated(frame)))
            self.page.on("dialog", lambda dialog: asyncio.create_task(self.dialog(dialog)))
            self.page.on("download", lambda download: asyncio.create_task(self.download(download)))
            self.page.on("filechooser", lambda chooser: asyncio.create_task(self.filechooser(chooser)))
            self.context.on("page", lambda page: asyncio.create_task(self.extra_page(page)))
            self.page.on("close", self.closed)
            await self.page.evaluate(Path(__file__).with_name("record.js").read_text(encoding="utf-8"))
        if url:
            try: await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception: raise Invalid("Browser could not open that URL. Check the visible browser and address.")
        await self.page.bring_to_front()
        return self.state()

    async def filechooser(self, chooser):
        from .windows import choose_file
        page=self.page
        path = await asyncio.to_thread(self.file_selector or choose_file)
        if self.page!=page or not page or page.is_closed():return
        if not path:
            await chooser.set_files([])
            return
        if self.recording and self.simple_recording:
            frame = await chooser.element.owner_frame()
            loc = await frame.evaluate("(el)=>window.__scRecorder?.locator(el)", chooser.element)
            scope = await self.frame_scope(frame)
            if scope is None: loc = None
            elif loc and scope: loc["frames"] = scope
            if not loc:
                self.unsupported("This upload control has no reliable label.")
                return
            ref = self.vault.add_file(path)
            self.selected_upload = (loc, ref)
        await chooser.set_files(path)

    def closed(self):
        was_recording=self.recording or self.mode=="recording_paused"
        if was_recording:self.finish_recording_segment()
        self.recording = False
        if not self.busy():
            if was_recording:
                if len(self.draft["steps"])<500:
                    self.append({"action":"unsupported","reason":"Recorder browser closed before Stop. Review the final actions before playback."})
                self.draft=self.store.save(self.draft)
                self.store.checkpoint(self.draft,False)
                self.mode="interrupted"
                self.message="Recorder browser closed. The unfinished recording was saved for review. Press Stop."
            else:
                self.mode = "idle"
                self.message = "Recorder browser closed. Press Record to open it again."

    async def extra_page(self, page):
        if page == self.page: return
        if self.recording:
            self.unsupported("New tabs/popups are unsupported; recording remains on the original tab.")
        if self.busy():
            self.pause_requested = True
            self.can_resume = False
            self.gate.clear()
            self.mode = "paused"
            self.message = "A new tab opened. Inspect the browser and Stop; V1 cannot safely continue this run."

    async def dialog(self, dialog):
        await dialog.dismiss()
        if self.recording: self.unsupported("Browser dialog was dismissed; dialogs are unsupported.")
        if self.busy():
            self.pause_requested = True
            self.can_resume = False
            self.gate.clear()
            self.mode = "paused"
            self.message = "Browser dialog dismissed. Outcome may be uncertain; inspect and Stop."

    async def download(self, download):
        await download.cancel()
        if self.recording: self.unsupported("Downloads are unsupported and were cancelled.")

    async def loaded(self):
        if self.recording:
            for frame in self.page.frames:
                with contextlib.suppress(Exception):
                    await frame.evaluate("window.__scRecorder?.set(true)")
        if self.recording and self.page and await self.is_sensitive():
            await self.privacy()

    async def is_sensitive(self):
        if not self.page or self.page.is_closed(): return True
        try:
            for frame in self.page.frames:
                if AUTH_PATH.search(frame.url): return True
                if await frame.evaluate("!!window.__scRecorder?.sensitive()"): return True
            return False
        except Exception:
            return True

    async def navigated(self, frame):
        if not self.recording: return
        if frame != self.page.main_frame:
            # Embedded documents navigate while the site renders; that is not a
            # user action. Actual frame input still reaches record_event below.
            with contextlib.suppress(Exception):
                await frame.evaluate("window.__scRecorder?.set(true)")
            return
        if AUTH_PATH.search(frame.url):
            await self.privacy()
            return
        try:
            safe_url(frame.url)
            # Never issue a second navigation for a click/submission's result.
            # Keep an explicit checkpoint instead of silently dropping it.
            action = "wait_url" if time.monotonic() - self.last_click < 10 else "navigate"
            self.last_click = 0
            self.append({"action": action, "value": frame.url})
        except Invalid:
            self.unsupported("Navigation contains sign-in or secret information. Use an ordinary website address.")

    def unsupported(self, reason):
        self.append({"action": "unsupported", "reason": reason})
        self.message = "Unsupported action captured. Resolve flagged steps before Play."

    def append(self, step):
        if len(self.draft["steps"]) >= 500:
            self.recording = False
            self.mode = "idle"
            self.message = "500-step limit reached. Save this task."
            return
        old = self.draft["steps"]
        if old and old[-1] == step: return
        if old and step["action"] == "fill" and old[-1]["action"] == "fill" and old[-1]["locator"] == step["locator"]:
            old[-1] = step
        else: old.append(step)
        self.store.checkpoint(self.draft)

    def finish_recording_segment(self):
        if self.recording_started is not None:
            self.recorded_ms += max(0, round((time.monotonic() - self.recording_started) * 1000))
            self.recording_started = None
        if self.draft.get("id"):
            self.store.metadata(self.draft["id"], duration_ms=self.recorded_ms)

    async def privacy(self):
        self.finish_recording_segment()
        self.recording = False
        self.privacy_pause = True
        self.mode = "recording_paused"
        self.message = "Recording paused for sign-in or sensitive content. Sign in manually, leave the sign-in page, then Resume."
        with contextlib.suppress(Exception):
            await self.page.evaluate("window.__scRecorder?.set(false)")

    async def record_event(self, source, data):
        async with self.capture_lock:
            await self._record_event(source, data)

    async def frame_scope(self, frame):
        """Only uniquely identified same-origin frames; never frame positions."""
        from urllib.parse import urlsplit
        scopes = []
        while frame != self.page.main_frame:
            if not getattr(frame, "parent_frame", None) or len(scopes) >= 4: return None
            url = urlsplit(frame.url)
            top = urlsplit(self.page.url)
            if frame.url not in {"about:blank", "about:srcdoc"} and (url.scheme, url.netloc) != (top.scheme, top.netloc):
                return None
            element = await frame.frame_element()
            identity = await element.evaluate("""el => {
              for (const by of ['id','name','title']) {
                const value=el.getAttribute(by);
                if(value && [...el.ownerDocument.querySelectorAll('iframe,frame')].filter(x=>x.getAttribute(by)===value).length===1)
                  return {by,value};
              }
              return null;
            }""")
            if not identity: return None
            scopes.insert(0, identity)
            frame = frame.parent_frame
        return scopes

    async def _record_event(self, source, data):
        if not self.recording or source["page"] != self.page: return
        if isinstance(data, dict) and data.get("kind") == "privacy":
            await self.privacy()
            return
        if isinstance(data, dict) and data.get("kind")=="ready":
            # Init scripts notify us after their recorder is installed, including
            # dynamically created srcdoc/cross-origin frames. Check privacy before
            # enabling capture; never infer user interaction from a frame load.
            if AUTH_PATH.search(source["frame"].url):await self.privacy()
            else:
                # set(true) performs the frame-local sensitive-field check before
                # accepting input; its observer pauses on later sign-in fields.
                with contextlib.suppress(Exception):await source["frame"].evaluate("window.__scRecorder?.set(true)")
            return
        if not isinstance(data, dict): return
        if data.get("kind") == "privacy":
            await self.privacy()
        elif data.get("kind") == "unsupported":
            # Page scripts are untrusted; do not retain arbitrary messages.
            from .attention import CAPTURE_REASONS
            code=data.get("code") if isinstance(data.get("code"),str) else None
            self.unsupported(CAPTURE_REASONS.get(code,"Unsupported browser action. Record a simple labelled control in the main tab."))
        elif data.get("kind") == "step":
            step = copy.deepcopy(data.get("step"))
            if not isinstance(step, dict): return
            scope = await self.frame_scope(source["frame"])
            if scope is None:
                self.unsupported("An action inside an embedded page needs a unique same-origin frame id, name or title. Open it in the main page or ask the site to label the frame.")
                return
            if scope and isinstance(step.get("locator"), dict): step["locator"]["frames"] = scope
            if step.get("action") == "upload":
                if self.selected_upload and self.selected_upload[0] == step.get("locator"):
                    step["value"] = {"file": self.selected_upload[1]}
                    self.selected_upload = None
                    self.message = "File selected and remembered on this PC."
                else:
                    n = 1
                    names = {i["name"] for i in self.draft["inputs"]}
                    name = "image_path"
                    while name in names:
                        n += 1
                        name = "image_path_" + str(n)
                    self.draft["inputs"].append({"name": name, "required": True})
                    step["value"] = {"input": name}
                    self.message = "Choose this file again on the recorder PC before playback."
            try:
                validate_task({**self.draft, "steps": [step]})
            except Invalid:
                await self.privacy()
                return
            if "locator" in step:
                try:
                    if await self.locator(step["locator"]).count() > 1:
                        self.unsupported("The recorded target is missing or ambiguous. Record a uniquely labelled control after the page finishes loading.")
                        return
                except Exception:
                    # The click may already have navigated or removed its target.
                    # Uniqueness was checked synchronously in the capture script.
                    pass
            if step["action"] == "click": self.last_click = time.monotonic()
            self.append(step)

    async def set_recording(self, active):
        if active:
            if self.busy(): raise Invalid("Stop playback before recording.")
            if not self.page or self.page.is_closed(): raise Invalid("Open Browser first.")
            if await self.is_sensitive():
                await self.privacy()
                return
            if not self.draft["steps"]:
                self.append({"action": "navigate", "value": safe_url(self.page.url)})
            if self.recording_started is None:self.recording_started = time.monotonic()
            self.recording = True
            self.privacy_pause = False
            self.mode = "recording"
            self.message = "Recording this browser tab only. Stop Recording before sign-in."
            for frame in self.page.frames:
                with contextlib.suppress(Exception):
                    await frame.evaluate("window.__scRecorder?.set(true)")
        else:
            if self.page and not self.page.is_closed():
                for frame in list(self.page.frames):
                    try:
                        await asyncio.wait_for(frame.evaluate("window.__scRecorder?.flush()"), 5)
                        await frame.evaluate("window.__scRecorder?.set(false)")
                    except Exception:
                        self.unsupported("A page changed or capture delivery failed while stopping. Review and rerecord the final actions.")
            self.finish_recording_segment()
            self.recording = False
            self.privacy_pause = False
            self.mode = "idle"
            from .attention import issues
            problems = issues(self.draft)
            self.message = ("Recording stopped. Needs attention: " + problems[0]["explanation"]) if problems else "Recording stopped. Edit inputs/steps, name the task, then Save."
            self.store.checkpoint(self.draft, False)

    def locator(self, loc):
        p, value = self.page, loc["value"]
        for frame in loc.get("frames", []):
            p = p.frame_locator("iframe[" + frame["by"] + "=" + json.dumps(frame["value"]) + "]")
        if loc["by"] == "role": return p.get_by_role(loc["role"], name=value, exact=True)
        if loc["by"] == "label": return p.get_by_label(value, exact=True)
        if loc["by"] == "test_id": return p.get_by_test_id(value)
        if loc["by"] == "placeholder": return p.get_by_placeholder(value, exact=True)
        if loc["by"] == "text": return p.get_by_text(value, exact=True)
        # Escape an ID as an attribute value, never accept user-supplied CSS.
        return p.locator("[id=" + json.dumps(value) + "]")

    async def wait_gate(self):
        if self.pause_requested:
            self.mode = "paused"
            self.message = "Paused. Resume to continue at the next unfinished action."
            self.notify_state()
            await self.gate.wait()

    async def target(self, step):
        loc = self.locator(step["locator"])
        remaining = step.get("timeout_ms", 8000) / 1000
        while remaining > 0:
            await self.wait_gate()
            started = time.monotonic()
            try:
                count = await asyncio.wait_for(loc.count(), min(.5, remaining))
            except asyncio.TimeoutError:
                remaining -= time.monotonic() - started
                continue
            except Exception:
                raise TargetProblem("Embedded frame is missing or ambiguous. Check the named frame, then Resume; or Stop.")
            if count > 1: raise TargetProblem("Target is ambiguous (" + str(count) + " matches). Make the page unique, then Resume; or Stop and edit the locator.")
            if count == 1:
                if step["action"] == "upload" or await loc.is_visible():
                    return loc
            await asyncio.sleep(.1)
            remaining -= time.monotonic() - started
        raise TargetProblem("Target missing or hidden. Check the visible page, then Resume to retry only this step; or Stop and edit.")

    async def perform(self, step):
        action = step["action"]
        if action == "wait_url":
            await self.wait_gate()
            try:
                await self.page.wait_for_url(step["value"], wait_until="domcontentloaded", timeout=step.get("timeout_ms",8000))
            except Exception:
                raise TargetProblem("Expected navigation has not completed. Check the browser, then Resume; or Stop and edit the URL checkpoint.")
            return
        if action == "navigate":
            await self.wait_gate()
            await self.page.goto(step["value"], wait_until="domcontentloaded", timeout=step.get("timeout_ms", 8000))
            return
        loc = await self.target(step)
        await self.wait_gate()
        if step.get("locator", {}).get("frames"):
            element = await loc.element_handle(timeout=step.get("timeout_ms", 8000))
            if not element or await self.frame_scope(await element.owner_frame()) is None:
                raise TargetProblem("Embedded page origin or identity changed. Stop and record the supported same-origin page.")
        if await self.is_sensitive():
            raise TargetProblem("Sign-in detected. Sign in manually with recording off, then Resume.")
        if action == "wait": return
        if action == "click":
            # Trial can time out without dispatching a click; this is safe to retry.
            try: await loc.click(trial=True, timeout=step.get("timeout_ms", 8000))
            except Exception: raise TargetProblem("Target is not actionable (covered, moving or disabled). Resolve it, then Resume.")
        await self.wait_gate()
        self.can_resume = False
        timeout = step.get("timeout_ms", 8000)
        if action == "click": await loc.click(timeout=timeout, no_wait_after=True)
        elif action == "fill": await loc.fill(step["value"], timeout=timeout)
        elif action == "select": await loc.select_option(value=step["value"], timeout=timeout)
        elif action == "check": await loc.set_checked(step["value"], timeout=timeout)
        elif action == "upload":
            await loc.set_input_files(step["value"], timeout=timeout)
            # Confirms browser selection; remote processing needs an explicit wait step.
            await loc.evaluate("(el) => { if (!el.files || el.files.length !== 1) throw Error('Upload not selected'); }")

    async def run(self, task):
        try:
            for i, step in enumerate(task["steps"]):
                self.index, self.current_action = i, step["action"]
                label = step.get("locator", {}).get("value", "Open website")
                self.message = f"Step {i + 1} of {self.total} — {step['action'].replace('_', ' ')}: {label}"
                self.notify_state()
                await self.wait_gate()
                while True:
                    try:
                        self.store.result(self.run_id, "executing", i, "Step started; no automatic replay after interruption.")
                        self.in_action = True
                        try:
                            await self.perform(step)
                        finally:
                            self.in_action = False
                        break
                    except TargetProblem as exc:
                        self.mode = "paused"
                        self.can_resume = True
                        self.pause_requested = True
                        self.gate.clear()
                        self.message = f"Step {i + 1} of {self.total} — {label}: {exc}"
                        self.store.result(self.run_id, "paused", i, self.message)
                        self.notify_state()
                        await self.gate.wait()
                self.store.result(self.run_id, "running", i + 1, "Step completed.")
                self.message = "Completed step " + str(i + 1) + " of " + str(self.total)
                await self.wait_gate()
                # Yield so Stop/Pause is handled between fast actions.
                await asyncio.sleep(.05)
            self.mode = "completed"
            self.message = "Task completed. Verify the result in the browser."
            self.store.result(self.run_id, "completed", self.total, self.message)
            self.notify_state()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.mode = "paused"
            self.can_resume = False
            self.message = f"Step {self.index + 1} of {self.total} — {self.current_action} failed ({type(exc).__name__}). Outcome may be uncertain. Inspect the browser, then Stop."
            self.store.result(self.run_id, "interrupted", self.index, self.message)
            self.notify_state()
            # Keep the job owned until Stop; Play must not overwrite uncertain work.
            await asyncio.Event().wait()

    async def play(self, task_id, values, revision=None, operation_id=None):
        if self.busy() or self.recording or self.mode == "recording_paused":
            raise Invalid("Stop the current run/recording first.")
        saved = self.store.get(task_id)
        actual_revision = self.store.revision(saved)
        if revision and revision != actual_revision:
            raise Invalid("This recording changed. Select it again, then Play.")
        task = resolve_task(saved, values, self.vault.file)
        if not self.page or self.page.is_closed(): await self.open_browser()
        await self.page.bring_to_front()
        self.run_id = task_id
        self.run_name = saved["name"]
        self.store.run_context = {"operation_id": operation_id, "task_revision": actual_revision}
        self.total = len(task["steps"])
        self.index = 0
        self.mode = "running"
        self.message = "Playing saved task."
        self.can_resume = True
        self.pause_requested = False
        self.gate.set()
        self.job = asyncio.create_task(self.run(task))

    async def pause(self):
        if self.recording:
            await self.set_recording(False)
            self.mode = "recording_paused"
            self.message = "Recording paused. Sign in manually if needed, then Resume."
        elif self.busy() and self.mode == "running":
            self.pause_requested = True
            self.can_resume = True
            self.gate.clear()
            self.mode = "pausing" if self.in_action else "paused"
            self.message = "Pausing… The current action is finishing." if self.in_action else "Paused. Resume to continue."

    async def resume(self):
        if self.mode == "recording_paused":
            await self.set_recording(True)
        elif self.busy() and self.mode == "paused" and self.can_resume:
            self.pause_requested = False
            self.mode = "running"
            self.message = "Resuming at current step."
            self.gate.set()
        else: raise Invalid("This action cannot be safely resumed. Inspect the browser, then Stop.")

    async def stop(self):
        if self.recording or self.mode == "recording_paused":
            await self.set_recording(False)
            if self.simple_recording and self.draft["steps"]:
                self.draft = self.store.save(self.draft)
        self.recording = False
        self.privacy_pause = False
        self.pause_requested = False
        if self.job and not self.job.done():
            self.job.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.job
            self.store.result(self.run_id, "stopped", self.index, "Stopped. Pending browser actions cancelled; check any submitted result.")
        # Closing this dedicated context cancels Playwright commands still in flight.
        if self.context:
            with contextlib.suppress(Exception): await self.context.close()
        self.context = self.page = None
        self.job = None
        self.mode = "stopped"
        self.can_resume = False
        self.run_id = None
        self.message = "Stopped; dedicated browser closed to cancel pending actions. Session profile is retained."
        self.notify_state()

    async def preview(self):
        if not self.page or self.page.is_closed(): raise Invalid("Open Browser first.")
        if self.privacy_pause or await self.is_sensitive():
            return {"blocked": True, "boxes": []}
        # Layout only: no page strings, values, URLs, pixels, images or session data.
        return await self.page.evaluate("""() => ({
          blocked:false, width:innerWidth, height:innerHeight,
          boxes:[...document.querySelectorAll('input,button,select,textarea,a,img,canvas,video,iframe,h1,h2,p,form')]
            .map(e=>{const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,
              kind:['INPUT','TEXTAREA','SELECT'].includes(e.tagName)?'field':e.tagName==='BUTTON'?'button':'block'};})
            .filter(r=>r.w>0&&r.h>0&&r.y<innerHeight&&r.y+r.h>0).slice(0,250)
        })""")

    async def command(self, name, data):
        if name == "state": return self.state()
        if name == "preview": return await self.preview()
        if name == "stop":
            await self.stop()
            return self.state()
        async with self.lock:
            if name == "open": await self.open_browser(data.get("url"))
            elif name == "record":
                if self.busy() or self.recording: raise Invalid("Stop the active operation first.")
                if "task" in data: self.draft = validate_task(data["task"])
                await self.set_recording(True)
            elif name == "record-stop":
                if self.busy(): raise Invalid("Use Stop or Pause for playback.")
                await self.set_recording(False)
            elif name == "pause": await self.pause()
            elif name == "resume": await self.resume()
            elif name == "stop": await self.stop()
            elif name == "play": await self.play(data.get("id"), data.get("values", {}))
            elif name in {"new", "load", "save"}:
                if self.busy() or self.recording or self.mode == "recording_paused": raise Invalid("Stop playback/recording before editing tasks.")
                if name == "new": self.draft = self.blank()
                elif name == "load": self.draft = self.store.get(data.get("id"))
                else: self.draft = self.store.save(data.get("task"))
                self.total = 0
                self.index = 0
                self.current_action = ""
                self.mode = "idle"
                self.message = "Task saved locally." if name == "save" else "Task ready."
            else: raise Invalid("Unknown recorder command.")
            return self.state()

    async def close(self):
        await self.stop()
        if self.pw:
            await self.pw.stop()
            self.pw = None
