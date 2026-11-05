// Finds elements marked data-rb="..." and mounts the matching React Bits component.
// Pages are fully usable before this runs; each component's code is fetched only if the page uses it.
const loaders = {
  threads: () => import('./islands/threads.jsx'),
  spotlight: () => import('./islands/spotlight.jsx'),
  shiny: () => import('./islands/shiny.jsx'),
  gradient: () => import('./islands/gradient.jsx'),
  counter: () => import('./islands/counter.jsx'),
};

function mountAll() {
  const groups = {};
  document.querySelectorAll('[data-rb]').forEach((el) => {
    if (el.dataset.rbMounted) return;
    el.dataset.rbMounted = '1';
    (groups[el.dataset.rb] ||= []).push(el);
  });
  for (const [type, els] of Object.entries(groups)) {
    loaders[type]?.().then((m) => els.forEach((el) => m.default(el))).catch(() => {});
  }
}

const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 120));
if (document.readyState === 'complete') idle(mountAll);
else window.addEventListener('load', () => idle(mountAll), { once: true });
