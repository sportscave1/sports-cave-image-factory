/* Shared exact-file clipboard boundary. Browsing and unsupported Copy fetch no originals. */
window.FilesOriginal = (() => {
  const limitation = "Native file copying is unavailable in this browser. Use Download Original to keep filenames, formats and bytes, then copy the downloaded files in Windows Explorer.";
  function snapshot(items) {
    return Object.freeze(items.map(item => Object.freeze({
      id: item.id || item.path, path: item.path, name: item.name,
      revision: item.revision || item.rev || "", url: item.url,
    })));
  }
  async function copy(items) {
    // The web runtime has no native file-list writer. ClipboardItem cannot encode
    // original filenames or a Windows file list; PNG pixels are not source files.
    // Fail before fetching originals, touching the clipboard, or copying a subset.
    if (!Array.isArray(items) || !items.length) throw new Error("Select files to copy.");
    throw new Error(limitation);
  }
  let closeMenu = () => {};
  function menu(event, copyAction, downloadAction) {
    closeMenu();
    const panel = document.createElement("div");
    panel.setAttribute("role", "menu");
    panel.style.cssText = "position:fixed;z-index:10000;display:grid;padding:6px;background:#20252d;border:1px solid #88909c;border-radius:6px;box-shadow:0 4px 20px #0008";
    const dismiss = e => { if (!panel.contains(e.target)) closeMenu(); };
    const keydown = e => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeMenu(); } };
    closeMenu = () => {
      panel.remove(); document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", keydown);
    };
    for (const [label, action] of [["Copy", copyAction], ["Download Original", downloadAction]]) {
      const button = document.createElement("button");
      button.type = "button"; button.textContent = label; button.setAttribute("role", "menuitem");
      button.style.cssText = "padding:10px;text-align:left;background:transparent;color:white;border:0;cursor:pointer";
      button.onclick = () => { closeMenu(); action(); };
      panel.appendChild(button);
    }
    document.body.appendChild(panel);
    panel.style.left = Math.max(0, Math.min(event.clientX || 0, innerWidth-panel.offsetWidth)) + "px";
    panel.style.top = Math.max(0, Math.min(event.clientY || 0, innerHeight-panel.offsetHeight)) + "px";
    document.addEventListener("pointerdown", dismiss); document.addEventListener("keydown", keydown);
    panel.firstChild.focus();
  }
  return {copy, snapshot, menu};
})();
