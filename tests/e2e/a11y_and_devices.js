// Accessibility (axe-core), console errors, mobile layout and slow-network checks for key pages, per role.
//   AXE_PATH=/path/to/axe.min.js BASE_URL=http://localhost node tests/e2e/a11y_and_devices.js
// Needs the seeded staging accounts (tests/seed_staging.py). Chromium only: Safari/Firefox engines are not in this container.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');
const B = process.env.BASE_URL || 'http://localhost';
const PW = process.env.QA_PASSWORD || 'QaPass#2026';
const AXE = fs.readFileSync(process.env.AXE_PATH || require.resolve('axe-core/axe.min.js'), 'utf8');
const out = { axe: [], console: [], layout: [], slow: [] };

const roles = {
  anon: [null, ['/', '/login/', '/password/forgot/', '/newsletters/', '/competitions/', '/gallery/', '/verify/00000000-0000-0000-0000-000000000000/', '/nope-404/']],
  student: ['lt0001', ['/dashboard/', '/courses/', '/courses/qa-course-1/', '/courses/qa-course-1/lessons/{lesson}/', '/courses/qa-course-1/quizzes/{quiz}/', '/doubts/', '/doubts/ask/', '/certificates/']],
  instructor: ['qa_inst1', ['/dashboard/', '/doubts/', '/students/', '/courses/qa-course-1/lessons/new/']],
  owner: ['qa_owner', ['/dashboard/', '/users/', '/users/generate/', '/students/', '/courses/qa-course-1/report/', '/certificates/issue/']],
};

async function login(page, u) {
  await page.goto(B + '/login/');
  await page.fill('[name=username]', u); await page.fill('[name=password]', PW);
  await Promise.all([page.waitForNavigation(), page.locator('form:has([name=password]) button.btn-primary').click()]);
}

(async () => {
  const browser = await chromium.launch();
  const ids = { lesson: process.env.LESSON_ID, quiz: process.env.QUIZ_ID };
  for (const [role, [user, pages]] of Object.entries(roles)) {
    for (const dev of ['Desktop Chrome', 'Pixel 7', 'iPhone 13']) {
      const ctx = await browser.newContext({ ...devices[dev], ...(dev === 'iPhone 13' ? { defaultBrowserType: undefined } : {}) });
      const page = await ctx.newPage();
      page.on('console', m => { if (m.type() === 'error') out.console.push({ role, dev, url: page.url(), text: m.text() }); });
      page.on('pageerror', e => out.console.push({ role, dev, url: page.url(), text: 'pageerror: ' + e.message }));
      if (user) await login(page, user);
      if (!ids.lesson && role === 'student') {
        await page.goto(B + '/courses/qa-course-1/');
        ids.lesson = (await page.locator('a[href*="/lessons/"]').first().getAttribute('href')).split('/lessons/')[1].split('/')[0];
        ids.quiz = (await page.locator('a[href*="/quizzes/"]').first().getAttribute('href')).split('/quizzes/')[1].split('/')[0];
      }
      for (const p of pages) {
        const url = B + p.replace('{lesson}', ids.lesson).replace('{quiz}', ids.quiz);
        await page.goto(url, { waitUntil: 'load' });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        if (overflow > 2) out.layout.push({ role, dev, url: p, overflowPx: overflow });
        if (dev === 'Desktop Chrome' || dev === 'Pixel 7') {
          await page.addScriptTag({ content: AXE });
          const res = await page.evaluate(async () => (await axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] })).violations
            .map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0] && v.nodes[0].target.join(' ') })));
          for (const v of res) out.axe.push({ role, dev, url: p, ...v });
        }
      }
      await ctx.close();
    }
  }
  // Slow 3G (≈400 kbps, 400 ms RTT) first visit of the login page and a student lesson page
  const ctx = await browser.newContext(devices['Pixel 7']); const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 400 * 1024 / 8, uploadThroughput: 400 * 1024 / 8 });
  for (const p of ['/login/']) {
    const t = Date.now(); await page.goto(B + p, { waitUntil: 'load', timeout: 120000 });
    const bytes = await page.evaluate(() => performance.getEntriesByType('resource').reduce((s, r) => s + (r.transferSize || 0), 0) + (performance.getEntriesByType('navigation')[0].transferSize || 0));
    out.slow.push({ url: p, loadMs: Date.now() - t, kB: Math.round(bytes / 1024) });
  }
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await login(page, 'lt0001');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 400 * 1024 / 8, uploadThroughput: 400 * 1024 / 8 });
  for (const p of ['/dashboard/', `/courses/qa-course-1/lessons/${ids.lesson}/`]) {
    const t = Date.now(); await page.goto(B + p, { waitUntil: 'load', timeout: 120000 });
    out.slow.push({ url: p + ' (assets cached)', loadMs: Date.now() - t });
  }
  await browser.close();
  // keyboard: is there a visible focus ring and a skip link? (spot check on the login page)
  const b2 = await chromium.launch(); const p2 = await b2.newPage();
  await p2.goto(B + '/login/'); await p2.keyboard.press('Tab');
  out.keyboard = await p2.evaluate(() => ({ firstFocus: document.activeElement.outerHTML.slice(0, 120),
    skipLink: !!document.querySelector('a[href="#main"], a.skip-link, .visually-hidden-focusable') }));
  await b2.close();
  fs.writeFileSync(path.join(__dirname, 'a11y_results.json'), JSON.stringify(out, null, 1));
  const summary = {};
  for (const v of out.axe) summary[`${v.impact} ${v.id}: ${v.help}`] = (summary[`${v.impact} ${v.id}: ${v.help}`] || new Set()).add(v.url);
  console.log('AXE violations (unique rule -> pages):');
  for (const [k, s] of Object.entries(summary)) console.log(' ', k, '->', [...s].join(', '));
  console.log('Console errors:', out.console.length, JSON.stringify(out.console.slice(0, 8)));
  console.log('Horizontal overflow on mobile:', JSON.stringify(out.layout));
  console.log('Slow 3G:', JSON.stringify(out.slow));
  console.log('Keyboard:', JSON.stringify(out.keyboard));
})();
