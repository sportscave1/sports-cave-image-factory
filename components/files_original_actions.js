/* Originals are fetched only inside an explicit clipboard action, never for browsing. */
window.FilesOriginal = (() => {
  const limitation = "This format cannot be copied losslessly by this browser.";
  function singleGifFrame(bytes) {
    // Walk blocks rather than searching compressed pixels for frame markers.
    let offset = 13 + ((bytes[10] & 128) ? 3 * (1 << ((bytes[10] & 7) + 1)) : 0);
    let frames = 0;
    const skipBlocks = () => {
      while (offset < bytes.length) {
        const length = bytes[offset++];
        if (!length) return;
        offset += length;
      }
    };
    while (offset < bytes.length) {
      const marker = bytes[offset++];
      if (marker === 59) return frames === 1;
      if (marker === 33) { offset++; skipBlocks(); }
      else if (marker === 44) {
        if (++frames > 1 || offset + 9 > bytes.length) return false;
        const packed = bytes[offset + 8];
        offset += 9 + ((packed & 128) ? 3 * (1 << ((packed & 7) + 1)) : 0);
        offset++; skipBlocks();
      } else return false;
    }
    return false;
  }
  async function pngFromOriginal(url) {
    const response = await fetch(url, {credentials:"same-origin", cache:"no-store"});
    if (!response.ok) throw new Error("The original file is unavailable or access has expired.");
    const blob = await response.blob();
    // Animation cannot be represented by the browser's still-image clipboard.
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const ascii = (start, length) => String.fromCharCode(...bytes.subarray(start, start + length));
    const png = ascii(1, 3) === "PNG";
    const jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
    const webp = ascii(0, 4) === "RIFF" && ascii(8, 4) === "WEBP";
    const gif = ascii(0, 3) === "GIF";
    const bmp = ascii(0, 2) === "BM";
    if (png) {
      const view = new DataView(bytes.buffer);
      for (let offset = 8; offset + 12 <= bytes.length;) {
        if (ascii(offset + 4, 4) === "acTL") throw new Error("Animated images require Download Original.");
        offset += 12 + view.getUint32(offset);
      }
      return blob.type === "image/png" ? blob : new Blob([blob], {type:"image/png"});
    }
    if (webp && ascii(12, 4) === "VP8X" && (bytes[20] & 2)) {
      throw new Error("Animated images require Download Original.");
    }
    if (gif && !singleGifFrame(bytes)) throw new Error("Animated or unreadable GIFs require Download Original.");
    if (!jpeg && !webp && !gif && !bmp) throw new Error(limitation);
    let bitmap;
    try {
      bitmap = await createImageBitmap(blob);
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d");
      if (!context || !bitmap.width || !bitmap.height) throw new Error(limitation);
      context.drawImage(bitmap, 0, 0);
      return await new Promise((resolve, reject) => canvas.toBlob(
        result => result ? resolve(result) : reject(new Error(limitation)), "image/png"));
    } catch (_) {
      throw new Error(limitation);
    } finally {
      bitmap?.close();
    }
  }
  function copy(url) {
    if (!navigator.clipboard?.write || typeof ClipboardItem !== "function" ||
        (ClipboardItem.supports && !ClipboardItem.supports("image/png"))) {
      return Promise.reject(new Error("Image clipboard access is unavailable in this browser."));
    }
    // Call write during user activation, before the asynchronous original fetch finishes.
    const png = pngFromOriginal(url);
    png.catch(() => {});
    return navigator.clipboard.write([new ClipboardItem({"image/png":png})]);
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
    for (const [label, action] of [["Copy Image", copyAction], ["Download Original", downloadAction]]) {
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
  return {copy, menu};
})();
