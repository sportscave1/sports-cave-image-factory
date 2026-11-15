"""Verified source navigation. Static analysis only; no application imports or writes."""
import ast
import hashlib
import re
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path

import drafts
import studio

_documents = OrderedDict()
_pages = OrderedDict()
MAX_CACHE = 64


class Elements(HTMLParser):
    """Source-line spans of actual HTML elements, excluding scripts and selectors."""
    def __init__(self, text):
        super().__init__()
        self.stack, self.rows = [], []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        row = {"tag": tag, "id": attrs.get("id"), "classes": attrs.get("class", "").split(),
               "line": self.getpos()[0], "end_line": self.getpos()[0]}
        self.rows.append(row)
        if tag not in {"input", "img", "br", "hr", "meta", "link", "source", "area", "base", "embed", "wbr"}:
            self.stack.append(row)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]["tag"] == tag:
                for row in self.stack[i:]:
                    row["end_line"] = self.getpos()[0]
                del self.stack[i:]
                break


def document(root, path):
    target = drafts.safe_file(root, path)
    stat = target.stat()
    key = (str(root), path, stat.st_mtime_ns, stat.st_size)
    if key in _documents:
        _documents.move_to_end(key)
        return _documents[key]
    meta, raw = drafts.read_source(root, path)
    text = raw.decode("utf-8-sig")
    value = {"text": text, "hash": meta["sha256"], "tree": ast.parse(text) if path.endswith(".py") else None}
    if path.endswith(".html"):
        value["elements"] = Elements(text).rows
    _documents[key] = value
    while len(_documents) > 160:
        _documents.popitem(last=False)
    return value


def purpose(path, shared=False):
    if shared:
        return "Shared navigation / layouts"
    if path.endswith(".css"):
        return "Styles / CSS"
    if path.endswith(".js"):
        return "Scripts / JavaScript"
    if path.endswith(".html"):
        return "Page source / templates"
    if path.startswith("components/"):
        return "Components"
    return "Python / Streamlit"


def literal(node, constants):
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def location(path, node, relationship):
    return {"path": path, "line": node.lineno, "end_line": node.end_lineno,
            "relationship": relationship}


def page_model(root, page, draft_id="", revision=0):
    import dev_sources
    import source_editor
    root = Path(root)
    key = (str(root), draft_id, revision, page)
    cached = _pages.get(key)
    def stamp(path):
        try:
            stat = drafts.safe_file(root, path).stat()
            return stat.st_mtime_ns, stat.st_size
        except (OSError, ValueError):
            return None
    if cached and all(stamp(p) == value for p, value in cached["stamps"].items()):
        _pages.move_to_end(key)
        return cached["model"]
    base = dev_sources.route_sources(root, page)
    refs = base["references"]
    rows, regions, stamps, calls, functions_by_path = {}, {}, {}, [], {}
    # Route definitions can change without changing a previously mapped file.
    from page_catalog import MODULES
    for dependency in {"app.py", *(name + ".py" for name in MODULES)}:
        stamps[dependency] = stamp(dependency)
    allowed = source_editor.paths(root)
    def add(path, relation, line=1, end_line=None, shared=False):
        if path not in allowed or source_editor.protected(path):
            return
        try:
            doc = document(root, path)
            if studio.secret_findings(doc["text"]):
                return
            stat = drafts.safe_file(root, path).stat()
        except (OSError, ValueError, SyntaxError):
            return
        stamps[path] = (stat.st_mtime_ns, stat.st_size)
        rows.setdefault(path, {"path": path, "line": line, "end_line": end_line or line,
                              "relationship": relation, "group": purpose(path, shared),
                              "editable": path in source_editor.EDITABLE, "available": True,
                              "shared": shared, "hash": doc["hash"]})
        regions.setdefault(path, []).append((line, end_line or len(doc["text"].splitlines())))
    for ref in refs:
        add(ref["path"], ref["relationship"], ref["line"], ref.get("end_line"))
    # Traverse only direct local calls from verified route ranges. No filename guesses.
    for path in list(rows):
        doc = document(root, path)
        if not doc["tree"]:
            continue
        functions = {n.name: n for n in doc["tree"].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        functions_by_path[path] = functions
        for _ in range(5):
            before = set(regions[path])
            for node in ast.walk(doc["tree"]):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and any(a <= node.lineno <= b for a, b in regions[path]):
                    fn = functions[node.func.id]
                    pair = (fn.lineno, fn.end_lineno)
                    if pair not in regions[path]:
                        regions[path].append(pair)
            if set(regions[path]) == before:
                break
        constants = {}
        for node in doc["tree"].body:
            if isinstance(node, ast.Assign):
                for name in node.targets:
                    if isinstance(name, ast.Name):
                        constants[name.id] = literal(node.value, constants)
        nodes = [n for n in ast.walk(doc["tree"]) if hasattr(n, "lineno") and any(a <= n.lineno <= b for a, b in regions[path])]
        strings = {n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for candidate in source_editor.EDITABLE:
            if candidate in strings or ("/" not in candidate and candidate in strings):
                add(candidate, "Literal source dependency of " + path)
        for node in nodes:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and node.args:
                function_text = ast.get_source_segment(doc["text"], functions[node.func.id]) or ""
                label = literal(node.args[0], constants)
                if isinstance(label, str) and 'sc-section-title' in function_text and '.markdown(' in function_text:
                    calls.append({**location(path, node, "Verified call to the section-heading renderer"),
                                  "method": "header", "label": label, "key": None})
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if method not in {"text_input", "text_area", "button", "form_submit_button", "selectbox", "checkbox", "dataframe", "data_editor", "container", "form", "markdown", "header", "subheader", "title", "caption", "write"}:
                continue
            kwargs = {k.arg: literal(k.value, constants) for k in node.keywords}
            label = literal(node.args[0], constants) if node.args else None
            containers = [n for n in nodes if isinstance(n, ast.With) and n.lineno <= node.lineno <= n.end_lineno]
            parent_keys = []
            for container in containers:
                for item in container.items:
                    expr = item.context_expr
                    if isinstance(expr, ast.Call):
                        parent_keys.extend(literal(k.value, constants) for k in expr.keywords if k.arg == "key")
                        if isinstance(expr.func, ast.Attribute) and expr.func.attr == "form" and expr.args:
                            parent_keys.append(literal(expr.args[0], constants))
            calls.append({**location(path, node, "Verified Python rendering call"),
                          "method": method, "key": kwargs.get("key") or (label if method == "form" else None),
                          "parent_keys": [k for k in parent_keys if isinstance(k, str)],
                          "label": label if isinstance(label, str) else "", "placeholder": kwargs.get("placeholder")})
            # HTML emitted by st.markdown has source locations inside its literal,
            # even when the whole string is an f-string with dynamic neighbours.
            if method == "markdown" and node.args:
                chunks = [n for n in ast.walk(node.args[0]) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                for chunk in chunks:
                    for heading in re.finditer(r"<h[1-6][^>]*>([^<{]+)</h[1-6]>", chunk.value):
                        segment = ast.get_source_segment(doc["text"], node) or ""
                        if segment.count(heading[0]) != 1:
                            continue
                        line = node.lineno + segment[:segment.index(heading[0])].count("\n")
                        calls.append({"path": path, "line": line, "end_line": line,
                                      "relationship": "Verified literal heading in Python markup",
                                      "method": "header", "key": None, "label": heading[1].strip()})
    for row in base["files"]:
        if row["group"] != "Authorised source library":
            add(row["path"], row["group"], shared=row["group"] == "Header / shared navigation")
    # Track missing presentation candidates too so later additions invalidate the cache.
    limitations = []
    if page == "__signin__":
        for path in source_editor.PRESENTATION:
            stamps[path] = stamp(path)
        missing = [p for p in source_editor.PRESENTATION if p not in rows]
        if missing:
            limitations.append("Older draft: verified sign-in presentation files unavailable. Showing the original Python rendering source; app.py has not been migrated.")
    # Prefer the actual imported rendering module, then the route's rendering function.
    direct = [r for r in rows.values() if not r["shared"]]
    primary = next((r for r in direct if r["path"] != "app.py" and any(c["path"] == r["path"] for c in calls)), None)
    if page == "__signin__":
        primary = next((r for r in direct if r["path"] == "components/sign_in/presentation.html"), None)
    primary = primary or next((r for r in direct if r["path"] == "app.py"), None)
    if primary:
        funcs = functions_by_path.get(primary["path"], {})
        renderers = [n for n in funcs.values() if any(a <= n.lineno <= b for a, b in regions[primary["path"]])
                     and any(c["path"] == primary["path"] and n.lineno <= c["line"] <= n.end_lineno for c in calls)]
        # On app.py, use the direct verified route's rendering function.
        direct_lines = {r["line"] for r in refs if r["path"] == primary["path"]}
        direct_renderers = [n for n in renderers if n.lineno in direct_lines]
        chosen = next((n for n in renderers if n.name == "render_page"), None) or next(iter(direct_renderers), None)
        if chosen:
            primary = {**primary, **location(primary["path"], chosen, "Verified page rendering function")}
    model = {"page": page, "draft_id": draft_id, "revision": revision, "files": list(rows.values()),
             "references": [{k: v for k, v in r.items() if k in {"path", "line", "end_line", "relationship"}} for r in rows.values()],
             "primary": primary, "limitations": limitations, "components": [],
             "coverage": {"render_calls": len(calls), "verified_files": len(rows),
                          "exact_rules": ["unique Streamlit key", "unique typed literal label", "verified HTML ID/class", "verified sign-in presentation setting"],
                          "fallback": "Verified page rendering source; exact element mapping unavailable"},
             "notice": "Only verified references. Protected Python is read-only; no replacement HTML is generated.",
             "_calls": calls}
    _pages[key] = {"model": model, "stamps": stamps}
    while len(_pages) > MAX_CACHE:
        _pages.popitem(last=False)
    return model


def public_model(model):
    return {k: v for k, v in model.items() if not k.startswith("_")}


def resolve(root, page, hit, draft_id="", revision=0):
    model = page_model(root, page, draft_id, revision)
    rows = model["files"]
    candidates = []
    kind = hit.get("kind")
    methods = {"heading": {"markdown", "header", "subheader", "title"}, "button": {"button", "form_submit_button"},
               "input": {"text_input", "text_area"}, "table": {"dataframe", "data_editor"}}
    enclosing = []
    key = hit.get("streamlit_key")
    if key:
        candidates = [c for c in model["_calls"] if c["key"] == key]
        if kind in methods:
            enclosing = [c for c in candidates if c["method"] not in methods[kind]]
            candidates = [c for c in candidates if c["method"] in methods[kind]]
        nested = [c for c in candidates if set(c.get("parent_keys", [])) & set(hit.get("streamlit_keys", []))]
        if nested:
            candidates = nested
    # Duplicate rendering paths cannot be represented as an exact single location.
    exact = len(candidates) == 1
    chosen = candidates[0] if exact else None
    if len(candidates) > 1 and len({c["path"] for c in candidates}) == 1:
        path = candidates[0]["path"]
        tree = document(root, path)["tree"]
        common = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and all(n.lineno <= c["line"] <= n.end_lineno for c in candidates)]
        if common:
            chosen = location(path, min(common, key=lambda n:n.end_lineno-n.lineno),
                              "Verified rendering function with multiple conditional element locations")
    if not chosen and hit.get("text") and kind in methods:
        text = hit["text"].strip()
        candidates = []
        for call in model["_calls"]:
            label = re.sub("<[^>]+>", "", call["label"]).strip().lstrip("#").strip()
            if call["method"] in methods[kind] and label == text:
                candidates.append(call)
        if len(candidates) == 1:
            chosen, exact = candidates[0], True
    component = hit.get("component")
    if page == "__signin__" and component in {"title", "brand", "description"}:
        setting = {"title": "TITLE", "brand": "BRAND", "description": "DESCRIPTION"}[component]
        if any(r["path"] == "signin_presentation.py" for r in rows):
            tree = document(root, "signin_presentation.py")["tree"]
            node = next((n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == setting for t in n.targets)), None)
            if node:
                chosen, exact = location("signin_presentation.py", node, "Verified presentation setting " + setting), True
    if not chosen:
        # A selector must occur as an actual HTML attribute / CSS rule, not a filename hint.
        selector = hit.get("element_id")
        classes = hit.get("classes", [])
        if component in {"panel", "mobile_panel"}:
            classes = ["sc-login-wrap"]
        matches = []
        for row in rows:
            if not row["path"].endswith(".html"):
                continue
            elements = document(root, row["path"])["elements"]
            found = [n for n in elements if (selector and selector == n["id"]) or
                     (set(c for c in classes if c.startswith("sc-")) & set(n["classes"]))]
            if len(found) == 1:
                matches.append({"path": row["path"], "line": found[0]["line"], "end_line": found[0]["end_line"],
                                "relationship": "Verified HTML element attribute"})
        unique = {(m["path"], m["line"]): m for m in matches}
        if len(unique) == 1:
            chosen, exact = next(iter(unique.values())), True
    if not chosen and len(enclosing) == 1:
        chosen = {**enclosing[0], "relationship": "Verified enclosing keyed container; exact child location unavailable"}
    chosen = chosen or model["primary"]
    shared_selection = chosen and any(r["path"] == chosen["path"] and r["shared"] for r in rows)
    related = [r for r in rows if chosen and (r["path"] == chosen["path"] or (not shared_selection and (
               (r["path"].endswith((".html", ".css", ".js")) and not r["shared"]) or
               (page == "__signin__" and r["path"] == "signin_presentation.py"))))]
    loc = {k: chosen[k] for k in ("path", "line", "end_line") if k in chosen} if chosen else None
    if loc:
        loc["hash"] = document(root, loc["path"])["hash"]
    return {**hit, "supported": bool(chosen), "exact": exact, "location": loc,
            "related": related, "page": page, "draft_id": draft_id, "revision": revision,
            "reason": chosen["relationship"] if exact else "Exact element mapping unavailable. " + (chosen["relationship"] + "." if chosen else "No verified source reference for this page.")}


def copy_source(home, draft_id, owner, data):
    """Re-resolve server-side; a browser cannot grant itself paths or line ranges."""
    import source_editor
    if data.get("mode") not in {"section", "related"}:
        raise ValueError("Choose section or related source copy.")
    with studio.locked(home) as file:
        draft, _, root = drafts.draft_by_id(studio.read(file), draft_id, owner)
        revision = draft["revision"]
    if data.get("revision") != revision:
        raise ValueError("Source revision changed. Inspect again before copying.")
    hit = resolve(root, data.get("page"), data.get("inspection") or {}, draft_id, revision)
    if not hit["location"]:
        raise ValueError("No verified source to copy.")
    rows = hit["related"] if data.get("mode") == "related" else [hit["location"]]
    sections = []
    for row in rows:
        opened = source_editor.open_file(home, draft_id, owner, row["path"])
        text = opened["source"]
        if data.get("mode") == "section":
            loc = hit["location"]
            text = "\n".join(text.splitlines()[loc["line"] - 1:loc.get("end_line", loc["line"])])
        if studio.secret_findings(text):
            raise ValueError("Potential sensitive source withheld.")
        sections.append({"path": row["path"], "language": opened["language"], "source": text,
                         "complete_file": data.get("mode") == "related"})
    if sum(len(s["source"].encode()) for s in sections) > source_editor.MAX_BATCH:
        raise ValueError("Related source exceeds the safe copy limit; copy individual full files. Nothing truncated.")
    return {"sections": sections, "mapping": hit["reason"], "exact": hit["exact"], "revision": revision}
