"""Authenticated local draft operations; application execution is Docker-contained."""
import hmac
import json
import secrets
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import drafts
import studio

ASSETS = {
    "/code-editor.js": ("code-editor.js", "text/javascript; charset=utf-8"),"/workspace": ("workspace.html", "text/html; charset=utf-8"),
          "/workspace-local.js": ("workspace-local.js", "text/javascript; charset=utf-8"),
          "/workspace.js": ("workspace.js", "text/javascript; charset=utf-8"),
          "/workspace.css": ("workspace.css", "text/css; charset=utf-8"),"/pair": ("pair.html", "text/html; charset=utf-8"),
          "/pair.js": ("pair.js", "text/javascript; charset=utf-8"),
          "/pair.css": ("pair.css", "text/css; charset=utf-8"),"/": ("index.html", "text/html; charset=utf-8"),
          "/drafts.js": ("drafts.js", "text/javascript; charset=utf-8"),
          "/drafts.css": ("drafts.css", "text/css; charset=utf-8"),
          "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
          "/editor.css": ("editor.css", "text/css; charset=utf-8")}
BLOCKER = "Full-application preview disabled: OS isolation and safety probes are not verified."

class DraftServer(HTTPServer):
    allow_reuse_address = False
    def get_request(self):
        client,address=super().get_request()
        client.settimeout(5)  # Idle browser preconnects cannot block the serial companion.
        return client,address

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, home, task_id, owner, idle_seconds=900, *, persistent=False, port=0):
        with studio.locked(home) as file:
            drafts.assigned(studio.read(file), task_id, owner)
        self.home, self.task_id, self.owner = home, task_id, owner
        self.persistent = persistent
        self.last_preview_activity = time.monotonic()
        self.device = None
        if persistent:
            from device_trust import Trust
            self.device = Trust(home, task_id, owner)
        self.token = secrets.token_urlsafe(32)
        self.idle_seconds = idle_seconds
        self.last_activity = time.monotonic()
        self.stopping = False
        self.preview_runtime = None
        self.release_preview = None
        self.release_candidate = None
        self.children = {}
        self.pairing_setups = {}
        self.workspace_grants = {}
        self.application_plans = {}
        super().__init__(("127.0.0.1", port), Handler)
        self.timeout = 1
        self.origin = "http://127.0.0.1:" + str(self.server_port)

    def state(self):
        with studio.locked(self.home) as file:
            registry = studio.read(file)
            task, _ = drafts.assigned(registry, self.task_id, self.owner)
            found = next((d for d in registry.get("drafts", []) if d["task_id"] == self.task_id), None)
        draft = drafts.inspect(self.home, found["id"], self.owner) if found else None
        return {"task": {k: task[k] for k in ("id", "owner", "branch", "worktree_path", "category")},
                "draft": draft, "test": (draft or {}).get("test") or task.get("last_verified_test"), "task_status": task.get("status", "Unknown"), "preview": {"enabled": True, "status": "Running" if self.preview_runtime and self.preview_runtime.name else "Stopped", "reason": "Synthetic raster preview; safety probes run before startup"},
                "idle_seconds": self.idle_seconds}

    def catalog(self, technical=False):
        # Metadata only: no whole-worktree scans and no credential/path export.
        with studio.locked(self.home) as file:
            registry = studio.read(file)
            drafts.assigned(registry, self.task_id, self.owner)
            tasks = {t["id"]: t for t in registry["tasks"]}
            rows = []
            for draft in registry.get("drafts", []):
                ordinary = draft.get("kind") == "application" and not draft.get("archived_at")
                if technical == ordinary:
                    continue
                task = tasks.get(draft["task_id"])
                if not task:
                    continue
                test = task.get("last_verified_test") or {}
                rows.append({**{k: draft.get(k) for k in
                    ("id", "name", "kind", "category", "owner", "branch", "revision", "task_id", "editing_status", "base_commit", "created_at", "archived_at", "metadata_version")},
                    "status": task.get("status", "Unknown"),
                    "updated_at": max(draft.get("updated_at") or "", task.get("updated_at") or ""),
                    "review_status": draft.get("review_status", "Unreviewed"),
                    "actionable": ordinary and draft.get("owner") == self.owner == task.get("owner"),
                    "action_reason": "" if draft.get("owner") == self.owner == task.get("owner") else "Open this draft with its assigned owner companion; this connection cannot edit another owner\'s workspace.",
                    "test": {**{k: test.get(k) for k in ("passed", "verified_at", "evidence")},
                             "snapshot": {k: (test.get("snapshot") or {}).get(k) for k in ("commit", "files_hash")}}})
            if technical:
                represented = {d["task_id"] for d in registry.get("drafts", [])}
                for task in registry["tasks"]:
                    if task["id"] not in represented:
                        rows.append({"id": task["id"], "task_id": task["id"], "kind": "technical-task",
                                     "name": task["name"], "owner": task["owner"], "category": task["category"],
                                     "branch": task["branch"], "status": task["status"], "actionable": False,
                                     "action_reason": "Technical development record; use its assigned owner workflow.",
                                     "history": task.get("history", []), "test": task.get("last_verified_test")})
            import application_drafts
            try:
                live = application_drafts.verified_live(self.home, registry)
                live_error = None
            except (ValueError, OSError, KeyError):
                live = None
                live_error = "Verify GitHub main and running production locally before creating a new application copy."
            if not technical:
                for row in rows:
                    if row["actionable"]:
                        try:
                            draft = next(d for d in registry["drafts"] if d["id"] == row["id"])
                            row.update(application_drafts.revision_status(self.home, registry, draft, self.owner, live))
                        except (ValueError, RuntimeError, OSError, KeyError):
                            row["actionable"] = False
                            row["action_reason"] = "Registered application identity could not be verified."
            default_id = application_drafts.default_selection(self.home, registry, self.owner) if not technical else None
            return {"categories": list(studio.CATEGORIES), "rows": rows, "workspace_v6": True,
                    "application_drafts": True, "default_draft_id": default_id,
                    "live": live, "live_error": live_error}

    def application_prepare(self, data):
        import application_drafts as apps
        operation = data.get("operation")
        if operation not in {"configure", "create", "duplicate", "rename", "archive", "update"}:
            raise ValueError("Unsupported application draft operation.")
        with studio.locked(self.home) as file:
            registry = studio.read(file)
            drafts.assigned(registry, self.task_id, self.owner)
            if operation in {"configure", "create"}:
                detail = {"production_base": apps.verified_live(self.home, registry, fresh=True)}
            else:
                apps.assigned(registry, data.get("draft_id"), self.owner)
                detail = None
        if detail is None:
            detail = apps.update_plan(self.home, data["draft_id"], self.owner) if operation == "update" else apps.review(self.home, data["draft_id"], self.owner)
        if operation == "update" and detail["conflicts"]:
            paths = detail["conflicting_files"] + detail["unfinished_files"]
            raise ValueError(" ".join(detail["conflicts"]) + (" Review: " + ", ".join(paths) if paths else ""))
        plan = {"operation": operation, "draft_id": data.get("draft_id"), "name": data.get("name"),
                "detail": detail, "expires": time.monotonic()+300}
        self.application_plans = {k:v for k,v in self.application_plans.items() if v["expires"] > time.monotonic()}
        if len(self.application_plans) >= 8:
            raise ValueError("Finish or cancel a pending local draft operation first.")
        ticket = secrets.token_urlsafe(32)
        self.application_plans[ticket] = plan
        return {"ticket": ticket, **{k:plan[k] for k in ("operation", "name", "detail")}}

    def application_run(self, data):
        import application_drafts as apps
        plan = self.application_plans.pop(data.get("ticket"), None)
        if not plan or plan["expires"] <= time.monotonic():
            raise ValueError("Local draft review expired. Review again.")
        op, detail = plan["operation"], plan["detail"]
        if op in {"configure", "create", "duplicate"}:
            if op != "duplicate":
                with studio.locked(self.home) as file:
                    live = apps.verified_live(self.home, studio.read(file), fresh=True)
                if live["revision"] != detail["production_base"]["revision"]:
                    raise ValueError("Live changed after review.")
            result = apps.create(self.home, self.task_id, self.owner, plan["name"], default=op=="configure",
                                 source_id=plan["draft_id"] if op=="duplicate" else None,
                                 expected=detail.get("fingerprint"))
            return {"id": result["id"], "name": result["name"], "operation": op}
        if op == "update":
            return apps.update_from_live(self.home, plan["draft_id"], self.owner, detail["fingerprint"], data.get("confirmation"))
        return apps.rename_or_archive(self.home, plan["draft_id"], self.owner, op,
                                      detail["fingerprint"], name=plan["name"], confirmation=data.get("confirmation"))

    def handoff(self, draft_id, intent):
        if intent not in {"open", "edit", "preview", "changes"}:
            raise ValueError("Unsupported local handoff.")
        with studio.locked(self.home) as file:
            draft, task, _ = drafts.draft_by_id(studio.read(file), draft_id, self.owner)
            task_id = task["id"]
        target = self
        if task_id != self.task_id:
            child = self.children.get(task_id)
            if child and child[1].is_alive() and not child[0].stopping:
                target = child[0]
            else:
                target = DraftServer(self.home, task_id, self.owner, self.idle_seconds, persistent=self.persistent)
                thread = threading.Thread(target=target.run, daemon=True)
                self.children[task_id] = (target, thread)
                thread.start()
        # Only returned to same-origin, authenticated localhost caller. Never sent to OS.
        return {"url": target.origin + "/workspace#token=" + target.token + "&intent=" + intent,
                "draft_id": draft["id"], "task_id": task_id}

    def workspace_grant(self,draft_id):
        self.handoff(draft_id,"edit")
        with studio.locked(self.home) as file:
            draft,task,_=drafts.draft_by_id(studio.read(file),draft_id,self.owner)
        self.workspace_grants={k:v for k,v in self.workspace_grants.items() if v["expires"]>time.monotonic()}
        if len(self.workspace_grants)>=8:raise ValueError("Close an existing editor session first.")
        import application_drafts
        with studio.locked(self.home) as file:
            chosen = next(d for d in studio.read(file).get("drafts", []) if d["id"] == draft_id)
        if chosen.get("kind") == "application":
            application_drafts.remember_selection(self.home, draft_id, self.owner)
        capability=secrets.token_urlsafe(32)
        self.workspace_grants[capability]={"task":task["id"],"draft":draft_id,"expires":time.monotonic()+900}
        return {"capability":capability,"draft_id":draft_id}

    def workspace_request(self,data):
        grant=self.workspace_grants.get(data.get("capability"))
        if not grant or grant["expires"]<=time.monotonic():raise ValueError("Local editor permission expired. Confirm the selected draft locally again.")
        with studio.locked(self.home) as file:
            registry=studio.read(file)
            # Fresh initiating-owner/worktree and selected immutable-draft validation.
            # Catalogue revision comparisons are presentation work, not authorization.
            drafts.assigned(registry,self.task_id,self.owner)
            _,task,_=drafts.draft_by_id(registry,grant["draft"],self.owner)
            if task['id']!=grant['task']:
                raise RuntimeError('Local editor grant task changed. Confirm the draft again.')
        allowed={"workspace-model","editor-reference","source-copy","editor-files","editor-open","source-open","source-history","editor-save","editor-save-all","editor-diff","start-preview","stop-preview","restart-preview","preview-event","application-tests"}
        command=data.get("command")
        if not isinstance(command,dict) or command.get("action") not in allowed:raise ValueError("Editor operation not allowlisted")
        if any(k in command for k in ("owner","task_id","draft_id","home","root","url","command")):raise ValueError("Editor scope cannot be overridden")
        target=self if grant["task"]==self.task_id else self.children[grant["task"]][0]
        grant["expires"]=time.monotonic()+900
        return target.action(command)

    def workspace_model(self):
        import editor,page_catalog
        state=self.state();draft=state["draft"]
        if not draft:raise ValueError("No named draft assigned")
        with studio.locked(self.home) as file:
            _,_,root=drafts.draft_by_id(studio.read(file),draft["id"],self.owner)
        try:pages=page_catalog.pages(root);page_error=None
        except (ValueError,OSError) as exc:pages=[];page_error=str(exc)
        return {"capabilities":{"code_first_source":1,"save_all":True,"source_navigation":1},"draft":{k:draft.get(k) for k in ("id","name","kind","category","owner","branch","revision","revisions","production_base","editing_status","metadata_version","release_readiness")},
                "task":{k:state["task"][k] for k in ("id","owner","branch","category")},
                "files":__import__("source_editor").files(self.home,draft["id"],self.owner)["files"],"pages":pages,"page_error":page_error,
                "test":state["test"],"preview":state["preview"],"status":state["task_status"]}

    def action(self, data):
        # Validate scope again on EVERY request; never accept owner/home/task from browser.
        action = data.get("action")
        if action == "application-prepare":return self.application_prepare(data)
        if action == "application-run":return self.application_run(data)
        if action == "technical-catalog":return self.catalog(technical=True)
        if action=="workspace-grant":return self.workspace_grant(data.get("draft_id"))
        if action=="workspace-request":return self.workspace_request(data)
        if action=="workspace-revoke":
            self.workspace_grants.pop(data.get("capability"),None)
            return {"revoked":True}
        if action=="workspace-model":return self.workspace_model()
        if action in {"editor-reference","source-copy"}:
            import source_navigation
            state=self.state()
            with studio.locked(self.home) as file:
                _,_,root=drafts.draft_by_id(studio.read(file),state['draft']['id'],self.owner)
            if action=="source-copy":return source_navigation.copy_source(self.home,state['draft']['id'],self.owner,data)
            return source_navigation.public_model(source_navigation.page_model(root,data.get('page'),state['draft']['id'],state['draft']['revision']))
        if action in {"start-preview", "restart-preview", "preview-event", "release-preview"}:
            self.last_preview_activity = time.monotonic()
        if action in {"release-catalog","release-operation","release-preview"}:
            import releases
            if action=="release-catalog":return releases.catalog(self.home,self.task_id,self.owner)
            if action=="release-operation":return releases.action(self.home,self.task_id,self.owner,data)
            candidate,root=releases.read_candidate(self.home,self.task_id,self.owner,data.get("id"))
            operation=data.get("operation")
            if operation=="start":
                if self.release_preview and self.release_preview.name:raise ValueError("Stop the current combined preview first.")
                from preview_runtime import Preview
                from preview_export import capture_objects
                source=capture_objects(releases.GitObjects(root),candidate)
                self.release_preview=Preview(self.home,self.task_id,self.owner,source_provider=lambda:source)
                self.release_candidate=candidate["id"]
                try:
                    frame=self.release_preview.start()
                    logged=self.release_preview.event({"action":"login-synthetic"})
                    if "Synthetic Preview Admin" not in logged.get("text",""):
                        logged=self.release_preview.event({"action":"frame"})
                    okay="Synthetic Preview Admin" in logged.get("text","") and "Traceback" not in logged.get("text","")
                    result=releases.runtime_result(self.home,self.task_id,self.owner,candidate["id"],candidate["fingerprint"],{"isolated_preview":True,"combined_runtime":okay},self.release_preview.evidence)
                    return {"record":result,"frame":logged,"safety":self.release_preview.evidence}
                except Exception:
                    self.release_preview.stop()
                    releases.runtime_result(self.home,self.task_id,self.owner,candidate["id"],candidate["fingerprint"],{"isolated_preview":False,"combined_runtime":False})
                    raise
            if self.release_candidate!=candidate["id"] or not self.release_preview:raise ValueError("Preview does not belong to the selected candidate.")
            if operation=="stop":self.release_preview.stop();return {"stopped":True}
            if operation=="event":return {"frame":self.release_preview.event(data.get("event",{}))}
            raise ValueError("Unknown combined preview operation.")
        if action == "catalog":
            return self.catalog()
        if action == "handoff":
            self.catalog()  # Revalidate the initiating owner before selected-task lookup.
            return self.handoff(data.get("draft_id"), data.get("intent"))
        state = self.state()
        if action == "new":
            return drafts.new(self.home, self.task_id, self.owner, data.get("name"))
        if action == "close":
            self.stopping = True
            return {"stopped": True}
        draft = state["draft"]
        if not draft:
            raise ValueError("Create a named draft first.")
        if action == "application-tests":
            import application_drafts
            return application_drafts.check(self.home, draft["id"], self.owner)
        if action == "save":
            files = data.get("files")
            revision = data.get("expected_revision")
            if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                raise ValueError("Files must be explicit source paths.")
            if type(revision) is not int:
                raise ValueError("Expected revision must be an integer.")
            return drafts.save(self.home, draft["id"], self.owner, revision, files)
        if action == "recover":
            revision = data.get("revision")
            if type(revision) is not int:
                raise ValueError("Choose an integer revision.")
            return drafts.recover_copy(self.home, draft["id"], self.owner, revision)
        if action in {"source-open","source-history","editor-save-all"}:
            import source_editor
            if action=="source-open":return source_editor.open_file(self.home,draft["id"],self.owner,data.get("path"))
            if action=="source-history":return source_editor.history_source(self.home,draft["id"],self.owner,data.get("path"),data.get("id"),data.get("side"))
            result=source_editor.write_all(self.home,draft["id"],self.owner,data.get("expected_revision"),data.get("files"))
            if result["changed"] and self.preview_runtime and self.preview_runtime.name:
                try:
                    result["frame"]=self.preview_runtime.refresh_source(result["paths"])
                    self.last_preview_activity=time.monotonic()
                except (ValueError,RuntimeError,OSError) as exc:
                    result["preview_error"]="Source saved; preview refresh failed: "+str(exc)
            return result
        if action in {"editor-files","editor-open","source-open","source-history","editor-save","editor-save-all","editor-diff"}:
            import editor
            if action=="editor-files":return editor.files(self.home,draft["id"],self.owner)
            path=data.get("path",editor.VISUAL_FILE)
            if action=="editor-open":
                return editor.open_file(self.home,draft["id"],self.owner,path)
            if action=="editor-diff":
                return editor.view_changes(self.home,draft["id"],self.owner,path)
            result=editor.write(self.home,draft["id"],self.owner,path,
                data.get("expected_hash"),data.get("expected_revision"),
                source=data.get("source"),component=data.get("component"),
                changes=data.get("changes"),restore=data.get("restore"))
            if result["changed"] and self.preview_runtime and self.preview_runtime.name:
                try:
                    result["frame"]=self.preview_runtime.refresh_source([path])
                    self.last_preview_activity=time.monotonic()
                except (ValueError,RuntimeError,OSError) as exc:
                    result["preview_error"]="Source saved; preview refresh failed: "+str(exc)
            return result
        if action in {"start-preview", "stop-preview", "restart-preview", "preview-event"}:
            if self.preview_runtime is None:
                from preview_runtime import Preview
                self.preview_runtime=Preview(self.home,self.task_id,self.owner)
            if action=="stop-preview":
                if not self.preview_runtime.name:
                    raise ValueError("Preview is already stopped.")
                self.preview_runtime.stop()
                return {"stopped":True}
            if action=="restart-preview":
                if not self.preview_runtime.name:
                    raise ValueError("No active preview to restart.")
                self.preview_runtime.stop()
            if action in {"start-preview","restart-preview"}:
                frame = self.preview_runtime.start()
                if draft.get("kind") == "application":
                    with studio.locked(self.home) as file:
                        registry = studio.read(file)
                        selected, _, _ = drafts.draft_by_id(registry, draft["id"], self.owner)
                        selected["preview_result"] = {"at": studio.now(), "revision": draft["revision"],
                            "manifest": self.preview_runtime.manifest, "isolation": self.preview_runtime.evidence}
                        studio.atomic(file, registry)
                return frame
            return self.preview_runtime.event(data.get("event",{}))
        if action == "close":
            self.stopping = True
            return {"stopped": True}
        raise ValueError("Unsupported action.")

    def idle_previews(self):
        if time.monotonic() - self.last_preview_activity >= self.idle_seconds:
            for preview in (self.preview_runtime, self.release_preview):
                if preview and preview.name:
                    preview.stop()

    def run(self):
        try:
            while not self.stopping and (self.persistent or time.monotonic() - self.last_activity < self.idle_seconds):
                self.handle_request()
                self.idle_previews()
        finally:
            for child, thread in self.children.values():
                child.stopping = True
                thread.join(4)
            if self.release_preview:
                self.release_preview.stop()
            if self.preview_runtime:
                self.preview_runtime.stop()
            self.server_close()

class Handler(BaseHTTPRequestHandler):
    # A stalled local client cannot indefinitely prevent idle shutdown.
    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, *args):
        pass  # Never log bearer tokens or user source paths.

    def reply(self, status, data, content_type="application/json", cookie=None):
        body = json.dumps(data).encode() if content_type == "application/json" else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def guard(self, authenticated=False):
        if self.headers.get_all("Host") != [self.server.origin.removeprefix("http://")]:
            self.reply(403, {"error": "Host rejected."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self.reply(403, {"error": "Origin rejected."})
            return False
        if authenticated:
            token = self.headers.get("X-Studio-Token", "")
            if not (hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("ascii")) or (self.server.device and self.server.device.valid(token))):
                self.reply(401, {"error": "Reopen the launcher URL to authenticate."})
                return False
            self.server.last_activity = time.monotonic()
        return True

    def do_GET(self):
        if not self.guard(authenticated=self.path.startswith("/api/")):
            return
        if self.path == "/api/ping":
            try:
                with studio.locked(self.server.home) as file:
                    studio.task_by_id(studio.read(file), self.server.task_id, self.server.owner)
                self.reply(200, {"connected": True})
            except (ValueError, RuntimeError, OSError) as exc:
                self.reply(403, {"error": str(exc)})
        elif self.path == "/api/state":
            try:
                self.reply(200, self.server.state())
            except (ValueError, RuntimeError, OSError) as exc:
                self.reply(409, {"error": str(exc)})
        elif self.path.startswith("/pair/setup/"):
            ticket = self.path.removeprefix("/pair/setup/")
            setup = self.server.pairing_setups.get(ticket)
            if not setup or setup["expires"] <= time.monotonic():
                self.reply(403, {"error": "Setup session expired or already used. Open a fresh local launcher session."})
                return
            import html
            page = (Path(__file__).parent / "ui" / "pair.html").read_text(encoding="utf-8")
            page = page.replace('value="https://sports-cave-image-factory.onrender.com"',
                                'value="'+html.escape(setup["origin"], quote=True)+'"')
            self.reply(200, page.encode(), "text/html; charset=utf-8")
        elif self.path in ASSETS:
            name, mime = ASSETS[self.path]
            self.reply(200, (Path(__file__).parent / "ui" / name).read_bytes(), mime)
        else:
            self.reply(404, {"error": "Not found."})

    def device_request(self):
        if not self.guard() or not self.server.device:
            return
        if self.headers.get("Origin") != self.server.origin or self.headers.get("X-Studio-Local") != "1":
            self.reply(403, {"error": "Same-origin local confirmation required."})
            return
        try:
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("Bounded JSON required.")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Bounded JSON required.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Expected a device operation object.")
            self.server.state()  # Recheck real registry ownership on renewal too.
            from http.cookies import SimpleCookie
            from device_trust import exact_origin, digest
            origin = exact_origin(data.get("origin"))
            legacy_name = "studio_device_" + str(self.server.server_port)
            name = legacy_name + "_" + digest(origin)[:16]
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            secret = cookie[name].value if name in cookie else (cookie[legacy_name].value if legacy_name in cookie else "")
            if data.get("operation") == "prepare":
                if not hmac.compare_digest(self.headers.get("X-Studio-Token", ""), self.server.token):
                    raise ValueError("Authenticated local launcher required.")
                if origin == self.server.origin:
                    raise ValueError("Use the OS website origin, not the companion address.")
                self.server.pairing_setups = {k:v for k,v in self.server.pairing_setups.items() if v["expires"] > time.monotonic()}
                if len(self.server.pairing_setups) >= 8:
                    raise ValueError("Too many pending setup sessions. Wait five minutes before opening another.")
                ticket = secrets.token_urlsafe(32)
                self.server.pairing_setups[ticket] = {"origin": origin, "expires": time.monotonic()+300}
                self.reply(200, {"url": self.server.origin+"/pair/setup/"+ticket, "expires_in": 300})
                return
            if data.get("operation") == "renew":
                if not secret:
                    raise ValueError("This browser profile has no saved cookie for the requesting OS origin. Use the same browser/profile and companion port, or approve that exact OS origin once in the local launcher. Windows trust records were not deleted.")
                secret, token = self.server.device.renew(secret, data.get("origin"))
            else:
                setup_ticket = data.get("setup_ticket", "")
                setup = self.server.pairing_setups.get(setup_ticket) if isinstance(setup_ticket,str) else None
                setup_allowed = (data.get("operation") == "trust" and setup and
                                 setup["expires"] > time.monotonic() and setup["origin"] == origin)
                if setup_ticket and not setup_allowed:
                    raise ValueError("Setup session expired, already used, or wrong OS origin.")
                if not setup_allowed and not self.guard(authenticated=True):
                    return
                if data.get("operation") == "trust":
                    # Enrollment/replacement requires the local bootstrap, never a renewed session.
                    if not setup_allowed and not hmac.compare_digest(self.headers.get("X-Studio-Token", ""), self.server.token):
                        raise ValueError("Fresh local launcher approval required.")
                    if origin == self.server.origin:
                        raise ValueError("Approve the Sports Cave OS website origin, not this companion's localhost address.")
                    secret, token = self.server.device.enroll(origin, secret)
                    if setup_allowed:
                        del self.server.pairing_setups[setup_ticket]
                elif data.get("operation") == "revoke":
                    self.server.device.revoke()
                    self.reply(200, {"revoked": True}, cookie=name+"=; HttpOnly; SameSite=Strict; Path=/api/device; Max-Age=0")
                    return
                elif data.get("operation") == "stop":
                    self.server.stopping = True
                    self.reply(200, {"stopped": True})
                    return
                else:
                    raise ValueError("Unknown device operation.")
            self.reply(200, {"token": token, "expires_in": 300}, cookie=name+"="+secret+"; HttpOnly; SameSite=Strict; Path=/api/device; Max-Age=2592000")
        except (ValueError, RuntimeError, OSError) as exc:
            self.reply(403, {"error": str(exc)})

    def do_POST(self):
        if self.path == "/api/device":
            if not self.server.device:
                self.reply(404, {"error": "Use the V5 persistent companion for device trust."})
            else:
                self.device_request()
            return
        if not self.guard(authenticated=True):
            return
        if self.path != "/api/action":
            self.reply(404, {"error": "Not found."})
            return
        try:
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise ValueError("A single Content-Length is required.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8 * 1024 * 1024 + 65536 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("Expected bounded application/json.")
            data = json.loads(self.rfile.read(length))
            if length > 2 * 1024 * 1024 + 16384 and data.get("action") != "editor-save-all" and not (data.get("action")=="workspace-request" and data.get("command",{}).get("action")=="editor-save-all"):raise ValueError("Oversized non-batch request.")
            if not isinstance(data, dict):
                raise ValueError("Expected an object.")
            self.reply(200, self.server.action(data))
        except (ValueError, RuntimeError, OSError) as exc:
            self.reply(409, {"error": str(exc)})

def launch(home, task_id, owner, open_browser=False):
    server = DraftServer(home, task_id, owner)
    url = server.origin + "/#" + server.token
    print("Draft Studio: on-demand synthetic Docker previews; security probes required.", flush=True)
    print("Private session URL (do not share): " + url, flush=True)
    print("Stops after 15 minutes without authenticated requests or Ctrl+C.", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.run()
    except KeyboardInterrupt:
        server.server_close()
