/* Light/dark switch, copied from the lab site (lab.opcode-labs.com web/assets/theme.js). Load it in <head> (not deferred): it applies the
   saved choice before the page paints. With no saved choice the page follows the
   computer's setting (prefers-color-scheme); the button stores an explicit choice.
   The stylesheets already define :root[data-theme="light"|"dark"]. */
(function(){
  const KEY = 'opcode-theme', root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch(e){}
  if(saved === 'light' || saved === 'dark') root.dataset.theme = saved;

  const current = () => root.dataset.theme || (system.matches ? 'dark' : 'light');
  const SUN = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">' +
    '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';

  function paint(btn){
    const dark = current() === 'dark';
    btn.innerHTML = dark ? SUN : MOON;  // shows what a click switches to
    btn.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    btn.title = btn.getAttribute('aria-label');
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Button styles live in style.css (the strict CSP forbids injected <style>).
    // The session page keeps its session bar on screen during a session (its top bar hides):
    // the button goes there; the account pages have only the top bar.
    const slot = document.querySelector('.sbar .wrap') || document.querySelector('.gbar .wrap');
    if(!slot) return;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'theme-btn';
    paint(btn);
    btn.addEventListener('click', () => {
      const next = current() === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch(e){}
      paint(btn);
    });
    system.addEventListener('change', () => paint(btn));  // no saved choice: follow the system
    slot.append(btn);
  });
})();
