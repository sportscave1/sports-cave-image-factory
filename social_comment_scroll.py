"""One small inline viewport observer; no iframe, polling or external assets."""
import streamlit.components.v2 as components

SCROLL_JS = """
export default function({parentElement, data, setTriggerValue}) {
  const target = parentElement.querySelector('[data-comment-sentinel]');
  const memory = parentElement.__commentScroll ||
    (parentElement.__commentScroll = {last: null, waiting: false, position: 0});
  const main = document.querySelector('[data-testid="stMain"]');
  const position = () => (main?.scrollTop || 0) + window.scrollY;
  const near = () => target.getBoundingClientRect().top <= window.innerHeight + 160;
  const load = () => {
    if (document.hidden || !data?.enabled || memory.waiting || memory.last === data.token || !near()) return;
    memory.last = data.token;
    memory.waiting = true;
    memory.position = position();
    setTriggerValue('load', data.token);
  };
  const scroll = () => {
    const current = position();
    if (current > memory.position + 8) memory.waiting = false;
    memory.position = current;
    load();
  };
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) load();
  }, {rootMargin: '160px'});
  observer.observe(target);
  document.addEventListener('scroll', scroll, {passive:true, capture:true});
  return () => {
    observer.disconnect();
    document.removeEventListener('scroll', scroll, true);
  };
}
"""

def scroll_request(token, enabled):
    # Registration is idempotent for these fixed assets and must occur in the
    # active runtime (including fresh test sessions and recovered connections).
    sentinel = components.component("social_comment_scroll",
        html='<div data-comment-sentinel role="status" aria-label="Load more comments when scrolling"></div>',
        css='div { height: 2px; }\n', js=SCROLL_JS)
    result = sentinel(data={"token": token, "enabled": enabled}, key="community-comment-scroll",
                       on_load_change=lambda: None, height=2)
    return result.load == token
