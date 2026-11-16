/* Runs only after the user clicks the extension and grants activeTab access. */
function captureFacebook() {
  if (location.protocol !== "https:" || !(location.hostname === "facebook.com" || location.hostname.endsWith(".facebook.com"))) {
    throw new Error("Open your Facebook dashboard tab first.");
  }
  const limit = 24000;
  const selection = window.getSelection()?.toString().trim() || "";
  let text = selection;
  let truncated = selection.length > limit;
  if (!selection) {
    const root = document.querySelector('[role="main"],main') || document.body;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const parts = [];
    let length = 0, visited = 0;
    while (walker.nextNode()) {
      if (++visited > 15000) { truncated = true; break; }
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || parent.closest('script,style,noscript,textarea,input,[contenteditable="true"],[aria-hidden="true"]')) continue;
      const style = getComputedStyle(parent);
      if (style.visibility === "hidden" || style.display === "none" || !parent.getClientRects().length) continue;
      const value = node.textContent.replace(/\s+/g, " ").trim();
      if (!value) continue;
      parts.push(value); length += value.length + 1;
      if (length > limit) { truncated = true; break; }
    }
    text = parts.join("\n");
  }
  if (!text.trim()) throw new Error("No readable text found. Wait for the dashboard to load, then try again.");
  return { type: "facebook_capture", url: location.origin + location.pathname, title: document.title.slice(0,300),
    text: text.slice(0,limit), selection: Boolean(selection), truncated };
}
