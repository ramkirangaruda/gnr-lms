// End-to-end walkthrough of GNR LMS through Caddy on http://localhost, every role.
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const crypto = require('crypto');
const path = require('path');
const B = process.env.BASE_URL || 'http://localhost';
const DIR = __dirname;
const REPO = process.env.REPO_DIR || require('path').resolve(__dirname, '../..');
const results = [];
let failures = 0;
const ok = (area, name, cond, detail = '') => {
  results.push({ area, name, pass: !!cond, detail });
  if (!cond) failures++;
  console.log(`${cond ? 'PASS' : 'FAIL'} [${area}] ${name}${detail ? ' :: ' + detail : ''}`);
};
const shell = (code) => execSync(`docker compose exec -T web python manage.py shell -v0 -c ${JSON.stringify(code)}`,
  { cwd: REPO }).toString().trim().split('\n').pop();

const serverErrors = [];
async function newRole(browser, label) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on('dialog', d => d.accept());
  page.on('response', r => { if (r.status() >= 500 && r.url().startsWith(B)) serverErrors.push(`${label}: ${r.status()} ${r.url()}`); });
  page.on('pageerror', e => serverErrors.push(`${label}: JS error ${e.message} on ${page.url()}`));
  return { ctx, page };
}
async function login(page, u, p) {
  await page.goto(B + '/login/');
  await page.fill('[name=username]', u);
  await page.fill('[name=password]', p);
  await Promise.all([page.waitForNavigation(), page.locator('form:has([name=password]) button.btn-primary').click()]);
  await page.waitForLoadState('load');
  return page.url();
}
async function submit(page, fieldSel) {
  const btn = page.locator(`form:has(${fieldSel})`).locator('button:not([name=delete_quiz]):not([name=delete_question])').last();
  const [resp] = await Promise.all([page.waitForNavigation({ waitUntil: 'load' }).catch(() => null), btn.click()]);
  return page.url();
}
async function crawl(page, role, start, skip = []) {
  const seen = new Set(); const queue = [start]; const bad = [];
  const deny = [/\/logout/, /\/delete\//, /reset-password/, /\/media\//, /\/static\//, /\.csv/, /^data:/, /\/admin\/logout/, ...skip];
  while (queue.length && seen.size < 120) {
    const u = queue.shift(); if (seen.has(u)) continue; seen.add(u);
    const r = await page.goto(u).catch(e => ({ status: () => 0, err: e }));
    const st = r ? r.status() : 0;
    if (st >= 400 && st !== 403 && st !== 404) bad.push(`${st} ${u}`);
    if (st === 404) bad.push(`404 ${u}`);
    const links = await page.$$eval('a[href]', as => as.map(a => a.href)).catch(() => []);
    for (let l of links) {
      l = l.split('#')[0];
      if (!l.startsWith(B) || deny.some(d => d.test(l)) || seen.has(l)) continue;
      if (/\/admin\//.test(l) && !/\/admin\/$/.test(l) && !/\/admin\/\w+\/\w+\/$/.test(l)) continue; // admin: index + changelists only
      queue.push(l);
    }
  }
  ok(role, `crawl: every linked page loads (${seen.size} pages)`, bad.length === 0, bad.slice(0, 8).join(' | '));
  return seen;
}

(async () => {
  const browser = await chromium.launch();
  const stamp = Date.now().toString().slice(-5);

  // ---------- public ----------
  {
    const { ctx, page } = await newRole(browser, 'public');
    for (const u of ['/', '/login/', '/newsletters/', '/gallery/', '/competitions/']) {
      const r = await page.goto(B + u); ok('public', `GET ${u}`, r.status() === 200 || (r.status() === 200 || page.url().includes('/login/')), `${r.status()} -> ${page.url()}`);
    }
    const r = await page.goto(B + '/courses/'); ok('public', 'course list requires login', page.url().includes('/login/'));
    const bad = await login(page, 'admin', 'wrong-password');
    ok('public', 'wrong password is rejected', bad.includes('/login/'));
    await ctx.close();
  }

  // ---------- owner ----------
  const O = await newRole(browser, 'owner'); const op = O.page;
  ok('owner', 'login', (await login(op, 'admin', 'OwnerPass123!')).includes('/dashboard/'));
  // school
  await op.goto(B + '/schools/new/');
  await op.fill('[name=name]', 'E2E Test School ' + stamp); await op.fill('[name=code]', 'e2e' + stamp.slice(-3)); await op.fill('[name=city]', 'Hyderabad');
  await submit(op, '[name=code]');
  ok('owner', 'create school', op.url().endsWith('/schools/') && (await op.content()).includes('E2E Test School ' + stamp), op.url());
  // bulk generate students
  await op.goto(B + '/users/generate/');
  await op.selectOption('[name=student_type]', 'school');
  await op.selectOption('[name=school]', { label: (await op.locator('[name=school] option', { hasText: 'E2E Test School ' + stamp }).first().textContent()).trim() });
  await op.fill('[name=grade]', '6'); await op.fill('[name=count]', '3');
  await submit(op, '[name=count]');
  const credText = await op.locator('table').first().innerText().catch(() => '');
  const creds = credText.split('\n').map(l => l.split('\t').map(s => s.trim())).filter(r => r.some(c => /^e2e\d+$/.test(c)));
  const stu = creds.map(r => ({ u: r.find(c => /^e2e\d+$/.test(c)), p: r[r.findIndex(c => /^e2e\d+$/.test(c)) + 1] }));
  ok('owner', 'bulk-generate 3 student logins + credentials sheet', stu.length === 3, JSON.stringify(stu.map(s => s.u)));
  // instructor
  await op.goto(B + '/users/new/');
  await op.fill('[name=first_name]', 'Asha' + stamp); await op.fill('[name=last_name]', 'Rao'); await op.fill('[name=username]', 'inst' + stamp);
  await op.selectOption('[name=role]', 'instructor'); await op.fill('[name=password]', 'InstPass123!');
  await submit(op, '[name=role]');
  ok('owner', 'create instructor login', !(await op.locator('.invalid-feedback, .errorlist').count()), op.url());
  // course
  await op.goto(B + '/courses/new/');
  await op.fill('[name=title]', 'E2E Course ' + stamp); await op.fill('[name=description]', 'Made by the end-to-end test.');
  await op.selectOption('[name=instructors]', { label: (await op.locator('[name=instructors] option', { hasText: 'Asha' + stamp }).first().textContent()).trim() });
  await op.setInputFiles('[name=thumbnail]', path.join(DIR, 'img.png'));
  await op.check('[name=is_published]');
  await submit(op, '[name=description]');
  const courseUrl = op.url(); const slug = courseUrl.split('/courses/')[1].split('/')[0];
  ok('owner', 'create course with thumbnail', (await op.content()).includes('E2E Course ' + stamp), courseUrl);
  // enrol the new school
  await op.goto(`${B}/courses/${slug}/students/`);
  await op.selectOption('[name=school]', { label: (await op.locator('[name=school] option', { hasText: 'E2E Test School ' + stamp }).first().textContent()).trim() });
  await submit(op, '[name=school]');
  const enrolled = shell(`from courses.models import Enrollment;print(Enrollment.objects.filter(course__slug='${slug}').count())`);
  ok('owner', 'enrol a whole school in the course', enrolled === '3', `enrolled=${enrolled}`);
  await O.ctx.close();

  // ---------- instructor ----------
  const I = await newRole(browser, 'instructor'); const ip = I.page;
  ok('instructor', 'login', (await login(ip, 'inst' + stamp, 'InstPass123!')).includes('/dashboard/'));
  // lesson with YouTube link + attachment
  await ip.goto(`${B}/courses/${slug}/lessons/new/`);
  await ip.fill('[name=title]', 'Intro (YouTube)'); await ip.fill('[name=video_url]', 'https://www.youtube.com/watch?v=nL34zDTPkcs');
  await ip.fill('[name=content]', 'Read this first.'); await ip.setInputFiles('[name=attachment]', path.join(DIR, 'notes.pdf'));
  await submit(ip, '[name=video_url]');
  const ytSrc = await ip.locator('iframe').first().getAttribute('src').catch(() => '');
  ok('instructor', 'lesson with YouTube link shows the embed', /youtube(-nocookie)?\.com\/embed\/nL34zDTPkcs/.test(ytSrc || ''), ytSrc);
  const attHref = await ip.locator('a[download]').first().getAttribute('href').catch(() => '');
  const attResp = attHref ? await ip.request.get(B + attHref) : null;
  ok('instructor', 'lesson attachment downloads', attResp && attResp.status() === 200, attHref);
  // lesson with uploaded MP4
  await ip.goto(`${B}/courses/${slug}/lessons/new/`);
  await ip.fill('[name=title]', 'Chapter 1 clip (MP4 upload)'); await ip.setInputFiles('[name=video_file]', path.join(DIR, 'clip.mp4'));
  await submit(ip, '[name=video_file]');
  const vSrc = await ip.locator('video').first().getAttribute('src').catch(() => '');
  const vr = vSrc ? await ip.request.get(B + vSrc, { headers: { Range: 'bytes=0-1023' } }) : null;
  ok('instructor', 'MP4 upload saved and served with range requests (seeking)', vr && vr.status() === 206 && vr.headers()['content-type'] === 'video/mp4', `${vSrc} -> ${vr && vr.status()}`);
  // lesson with Bunny upload: browser talks to a fake Bunny (intercepted), server token is real
  const courseId = shell(`from courses.models import Course;print(Course.objects.get(slug='${slug}').pk)`);
  const vid = crypto.randomUUID();
  const token = shell(`from courses import bunny;print(bunny.make_upload_token(${courseId},'${vid}'))`);
  let tusBytes = 0, tusHeaders = null;
  await ip.route('**/lessons/bunny-upload/', async (route) => {
    // the real view would call Bunny's API (needs a real account); hand back the same shape it returns
    const creds = JSON.parse(shell(`from courses import bunny;import json;print(json.dumps(bunny.tus_credentials('${vid}')))`));
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...creds, token }) });
  });
  await ip.route('https://video.bunnycdn.com/**', async (route) => {
    const req = route.request(); const h = { 'Tus-Resumable': '1.0.0', 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'Location, Upload-Offset, Tus-Resumable', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'POST, PATCH, HEAD, OPTIONS' };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: h });
    if (req.method() === 'POST') { tusHeaders = req.headers(); return route.fulfill({ status: 201, headers: { ...h, Location: 'https://video.bunnycdn.com/tusupload/fake-1' } }); }
    if (req.method() === 'PATCH') { const off = Number(req.headers()['upload-offset']); tusBytes += (req.postDataBuffer() || Buffer.alloc(0)).length; return route.fulfill({ status: 204, headers: { ...h, 'Upload-Offset': String(off + (req.postDataBuffer() || Buffer.alloc(0)).length) } }); }
    if (req.method() === 'HEAD') return route.fulfill({ status: 200, headers: { ...h, 'Upload-Offset': String(tusBytes), 'Upload-Length': String(tusBytes) } });
    route.fulfill({ status: 405, headers: h });
  });
  await ip.goto(`${B}/courses/${slug}/lessons/new/`);
  ok('instructor', 'Bunny upload box shows when keys are set', await ip.locator('#bunny-file').count() === 1);
  await ip.fill('[name=title]', 'Chapter 1 (Bunny Stream)');
  await ip.setInputFiles('#bunny-file', path.join(DIR, 'clip.mp4'));
  await ip.waitForFunction(() => document.querySelector('[name=bunny_upload_token]').value !== '', null, { timeout: 60000 }).catch(() => {});
  const status = await ip.locator('#bunny-status').innerText();
  ok('instructor', 'browser uploads the file to Bunny (TUS) with signed headers', tusBytes === 9407603 && tusHeaders && tusHeaders['authorizationsignature'] && tusHeaders['videoid'] === vid, `bytes=${tusBytes} status="${status}"`);
  await submit(ip, '[name=title]');
  const bSrc = await ip.locator('iframe[src*="mediadelivery"]').first().getAttribute('src').catch(() => '');
  const m = /embed\/123456\/([0-9a-f-]+)\?token=([0-9a-f]+)&expires=(\d+)/.exec(bSrc || '');
  const expect = m && crypto.createHash('sha256').update('fake-token-key' + m[1] + m[3]).digest('hex');
  ok('instructor', 'lesson plays the Bunny video through a correctly signed, expiring player link', m && m[1] === vid && m[2] === expect, bSrc);
  const bunnyLessonUrl = ip.url();
  // quiz
  await ip.goto(`${B}/courses/${slug}/quizzes/new/`);
  await ip.fill('[name=title]', 'E2E Quiz'); await ip.fill('[name=pass_percentage]', '50'); await ip.fill('[name=time_limit_minutes]', '5');
  if (await ip.locator('[name=max_attempts]').count()) await ip.fill('[name=max_attempts]', '3');
  if (await ip.locator('[name=is_published]').count()) await ip.check('[name=is_published]');
  await submit(ip, '[name=pass_percentage]');
  const quizManage = ip.url();
  for (const [text, a, b, correct] of [['Which board is the brain?', 'Arduino', 'Battery', '1'], ['Which part moves the robot?', 'Sensor', 'Motor', '2']]) {
    await ip.fill('[name=text]', text); await ip.fill('[name=choice_1]', a); await ip.fill('[name=choice_2]', b);
    await ip.check(`[name=correct][value="${correct}"]`);
    if (await ip.locator('[name=marks]').count()) await ip.fill('[name=marks]', '1');
    await submit(ip, '[name=choice_1]');
  }
  const qCount = shell(`from courses.models import Quiz;print(Quiz.objects.get(course__slug='${slug}').questions.count())`);
  ok('instructor', 'create quiz with 2 questions', qCount === '2', `questions=${qCount} url=${quizManage}`);
  await I.ctx.close();

  // ---------- student (fresh generated login) ----------
  const S = await newRole(browser, 'student'); const sp = S.page; const s1 = stu[0];
  const afterLogin = await login(sp, s1.u, s1.p);
  ok('student', 'first login is forced to set a new password', afterLogin.includes('/welcome/password/'), afterLogin);
  await sp.fill('[name=new_password1]', 'StudentNew123'); await sp.fill('[name=new_password2]', 'StudentNew123');
  await submit(sp, '[name=new_password1]');
  ok('student', 'new password accepted, lands on dashboard', sp.url().includes('/dashboard/'), sp.url());
  await sp.goto(courseUrl);
  ok('student', 'sees the enrolled course', (await sp.content()).includes('E2E Course ' + stamp));
  await sp.goto(bunnyLessonUrl);
  ok('student', 'sees the Bunny player on the lesson', await sp.locator('iframe[src*="mediadelivery"]').count() === 1);
  await sp.locator('form:not(:has(input[type=file])) button.btn-lg').first().click(); await sp.waitForLoadState('load');
  const prog = shell(`from courses.models import LessonProgress;print(LessonProgress.objects.filter(student__username='${s1.u}').count())`);
  ok('student', 'mark lesson complete records progress', prog === '1', `progress rows=${prog}`);
  const quizId = shell(`from courses.models import Quiz;print(Quiz.objects.get(course__slug='${slug}').pk)`);
  await sp.goto(`${B}/courses/${slug}/quizzes/${quizId}/`);
  const radios = sp.locator('#quizform input[type=radio]');
  const qNames = [...new Set(await radios.evaluateAll(els => els.map(e => e.name)))];
  for (const n of qNames) { // pick the correct answer by text
    const labels = await sp.locator(`#quizform input[name=${n}]`).evaluateAll(els => els.map(e => [e.value, document.querySelector(`label[for=${e.id}]`)?.innerText || e.parentElement.innerText]));
    const right = labels.find(([, t]) => /Arduino|Motor/.test(t)); await sp.check(`#quizform input[name=${n}][value="${right[0]}"]`);
  }
  await Promise.all([sp.waitForNavigation(), sp.locator('#quizform button').click()]);
  const resultText = await sp.locator('body').innerText();
  ok('student', 'take the quiz, auto-graded 100% and passed', sp.url().includes('/result/') && /100|2\s*\/\s*2/.test(resultText) && /pass/i.test(resultText), sp.url());
  // doubt with photo
  await sp.goto(`${B}/doubts/ask/`);
  await sp.fill('[name=title]', 'Motor not spinning ' + stamp);
  await sp.fill('[name=body]', 'My motor does not spin.\n```\ndigitalWrite(9, HIGH);\n```');
  if (await sp.locator('select[name=course]').count()) await sp.selectOption('select[name=course]', { label: (await sp.locator('select[name=course] option', { hasText: 'E2E Course' }).first().textContent()).trim() }).catch(() => {});
  if (await sp.locator('select[name=topic]').count()) { const opts = await sp.locator('select[name=topic] option').evaluateAll(o => o.map(x => x.value).filter(Boolean)); if (opts.length) await sp.selectOption('select[name=topic]', opts[0]); }
  await sp.setInputFiles('input[type=file][name=image]', path.join(DIR, 'img.png'));
  await submit(sp, '[name=body]');
  const doubtUrl = sp.url();
  ok('student', 'ask a doubt with code and a photo', /\/doubts\/\d+\/$/.test(doubtUrl) && (await sp.locator('pre, code').count()) > 0, doubtUrl);
  await crawl(sp, 'student', B + '/dashboard/');
  // student must not reach staff pages
  for (const u of ['/users/', '/students/', `/courses/${slug}/report/`, '/certificates/issue/', '/admin/']) {
    const r = await sp.goto(B + u); ok('student', `blocked from ${u}`, r.status() === 403 || r.status() === 404 || sp.url().includes('/login'), `${r.status()} ${sp.url()}`);
  }

  // ---------- instructor answers ----------
  const I2 = await newRole(browser, 'instructor'); const ip2 = I2.page;
  await login(ip2, 'inst' + stamp, 'InstPass123!');
  await ip2.goto(B + '/doubts/?q=' + encodeURIComponent('Motor not spinning ' + stamp));
  ok('instructor', 'doubt appears in the instructor queue', (await ip2.content()).includes('Motor not spinning ' + stamp));
  await ip2.goto(doubtUrl);
  await ip2.fill('textarea[name=body]', 'Check the motor driver enable pin.');
  await Promise.all([ip2.waitForNavigation(), ip2.locator('form:has(textarea[name=body]) button.btn-primary').click()]);
  ok('instructor', 'answer the doubt', (await ip2.content()).includes('Check the motor driver enable pin.'));
  await crawl(ip2, 'instructor', B + '/dashboard/');
  await I2.ctx.close();
  await sp.goto(doubtUrl);
  const accept = sp.locator('button[value=accept]');
  if (await accept.count()) { await Promise.all([sp.waitForNavigation(), accept.first().click()]); }
  const dStatus = shell(`from courses.models import Doubt;d=Doubt.objects.get(title='Motor not spinning ${stamp}');print(d.status)`);
  ok('student', 'student sees answer and marks it best (doubt resolved)', /resolv|answer|closed/i.test(dStatus), `status=${dStatus}`);

  // ---------- owner: certificates, portal, reports, admin ----------
  const O2 = await newRole(browser, 'owner'); const op2 = O2.page;
  await login(op2, 'admin', 'OwnerPass123!');
  await op2.goto(`${B}/certificates/issue/`);
  await op2.selectOption('[name=course]', { label: (await op2.locator('[name=course] option', { hasText: 'E2E Course' }).first().textContent()).trim() });
  await op2.fill('[name=usernames]', s1.u);
  if (await op2.locator('[name=title]').count() && !(await op2.inputValue('[name=title]'))) await op2.fill('[name=title]', 'Certificate of Completion');
  await submit(op2, '[name=usernames]');
  const code = shell(`from courses.models import Certificate;print(Certificate.objects.filter(student__username='${s1.u}').first().code)`);
  ok('owner', 'issue a certificate', code.length === 36, code);
  for (const [u, what] of [[`/certificates/${code}/`, 'printable certificate'], [`/students/`, 'students overview'], [`/courses/${slug}/report/`, 'course progress report']]) {
    const r = await op2.goto(B + u); ok('owner', `${what} loads`, r.status() === 200, u);
  }
  const sid = shell(`from accounts.models import User;print(User.objects.get(username='${s1.u}').pk)`);
  await op2.goto(`${B}/students/${sid}/`);
  const rep = await op2.locator('body').innerText();
  ok('owner', 'student report shows lesson progress, quiz score, certificate and doubt', /E2E Quiz/.test(rep) && /100/.test(rep) && /Motor not spinning/.test(rep) && /ertificate/.test(rep));
  // newsletter / competition / gallery
  await op2.goto(B + '/newsletters/new/');
  await op2.fill('[name=title]', 'E2E Newsletter ' + stamp);
  const bodyField = (await op2.locator('textarea').first().getAttribute('name')); await op2.fill(`textarea[name=${bodyField}]`, 'News body.');
  if (await op2.locator('[name=is_published]').count()) await op2.check('[name=is_published]');
  await submit(op2, '[name=title]');
  ok('owner', 'publish a newsletter', (await op2.content()).includes('E2E Newsletter ' + stamp), op2.url());
  await op2.goto(B + '/competitions/new/');
  const compFields = await op2.locator('form [name]').evaluateAll(els => els.map(e => [e.name, e.type, e.required]));
  for (const [n, t] of compFields) {
    if (n === 'csrfmiddlewaretoken') continue;
    if (t === 'text' && n === 'title') await op2.fill(`[name=${n}]`, 'E2E Robo Race ' + stamp);
    else if (t === 'date') await op2.fill(`[name=${n}]`, '2026-12-20');
    else if (t === 'datetime-local') await op2.fill(`[name=${n}]`, '2026-12-20T10:00');
    else if (t === 'textarea') await op2.fill(`[name=${n}]`, 'Details.');
    else if (t === 'url') await op2.fill(`[name=${n}]`, 'https://example.com/register');
    else if (t === 'checkbox' && /publish/.test(n)) await op2.check(`[name=${n}]`);
  }
  await submit(op2, '[name=title]');
  ok('owner', 'create a competition', (await op2.content()).includes('E2E Robo Race ' + stamp), op2.url());
  await op2.goto(B + '/gallery/new/');
  const galFields = await op2.locator('form [name]').evaluateAll(els => els.map(e => [e.name, e.type]));
  for (const [n, t] of galFields) {
    if (t === 'file') await op2.setInputFiles(`[name=${n}]`, path.join(DIR, 'img.png'));
    else if (t === 'text' && n !== 'csrfmiddlewaretoken') await op2.fill(`[name=${n}]`, 'E2E Photo ' + stamp);
    else if (t === 'date') await op2.fill(`[name=${n}]`, '2026-11-06');
  }
  await submit(op2, 'input[type=file]');
  await op2.goto(B + '/gallery/');
  ok('owner', 'upload a gallery photo', (await op2.content()).includes('E2E Photo ' + stamp));
  await crawl(op2, 'owner', B + '/dashboard/');
  await crawl(op2, 'owner-admin', B + '/admin/');
  await O2.ctx.close();

  // ---------- school admin ----------
  const SA = await newRole(browser, 'school'); const sap = SA.page;
  ok('school admin', 'login', (await login(sap, 'school_demo', 'school123')).includes('/dashboard/'));
  await sap.goto(B + '/users/');
  const ulist = await sap.locator('body').innerText();
  ok('school admin', 'user list shows only their own school (no E2E school students, no staff)', !/e2e\d{4}/.test(ulist) && !/inst\d+/.test(ulist) && /demo26/.test(ulist), JSON.stringify([ulist.match(/e2e\d{4}|inst\d+/), /demo26/.test(ulist)]));
  const r = await sap.goto(`${B}/students/${sid}/`);
  ok('school admin', "blocked from another school's student report", r.status() === 403 || r.status() === 404, `${r.status()}`);
  await sap.goto(B + '/users/new/');
  const roleOpts = await sap.locator('[name=role] option').evaluateAll(o => o.map(x => x.value));
  ok('school admin', 'can only create student logins', roleOpts.join() === 'student', roleOpts.join());
  await sap.fill('[name=first_name]', 'Kiran'); await sap.fill('[name=last_name]', 'S');
  await submit(sap, '[name=role]');
  const kiran = shell(`from accounts.models import User;u=User.objects.filter(first_name='Kiran').first();print(u.school.code if u else None, u.role if u else None)`);
  ok('school admin', 'create a student login (auto username, locked to own school)', kiran === 'demo student', kiran);
  await crawl(sap, 'school admin', B + '/dashboard/');
  await SA.ctx.close();

  // ---------- public verification + quiz timer ----------
  {
    const { ctx, page } = await newRole(browser, 'public');
    const r = await page.goto(`${B}/verify/${code}/`);
    ok('public', 'certificate verification link works without login', r.status() === 200 && (await page.content()).includes('E2E Course'));
    await ctx.close();
  }
  await sp.goto(`${B}/courses/${slug}/quizzes/${quizId}/`);
  ok('student', 'quiz shows a countdown timer', /\d+:\d\d/.test(await sp.locator('body').innerText()));
  await S.ctx.close();

  ok('all', 'no server errors (5xx) or JavaScript errors during the whole run', serverErrors.length === 0, serverErrors.slice(0, 10).join(' | '));
  await browser.close();
  require('fs').writeFileSync(path.join(DIR, 'results.json'), JSON.stringify(results, null, 1));
  console.log(`\n${results.length - failures}/${results.length} passed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('CRASH', e); process.exit(2); });
