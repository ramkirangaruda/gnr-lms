// k6 load test for GNR LMS (STAGING ONLY). Run from the repo root, e.g.
//   k6 run -e SCENARIO=ramp tests/load/lms.js
//   k6 run -e SCENARIO=login_storm tests/load/lms.js
//   k6 run -e SCENARIO=quiz_burst tests/load/lms.js
//   k6 run -e SCENARIO=soak -e SOAK_VUS=300 -e SOAK_MIN=30 tests/load/lms.js
// Needs the fake accounts from tests/seed_staging.py (lt0001..lt1500, qa_owner; password QaPass#2026).
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import exec from 'k6/execution';

const B = __ENV.BASE_URL || 'http://localhost';
const PW = __ENV.QA_PASSWORD || 'QaPass#2026';
const SCENARIO = __ENV.SCENARIO || 'ramp';
const N_USERS = Number(__ENV.N_USERS || 1500);
const HOLD = __ENV.HOLD || '3m';

const tLogin = new Trend('t_login', true), tPage = new Trend('t_page', true), tQuiz = new Trend('t_quiz_submit', true),
      tReport = new Trend('t_admin_report', true), tStatic = new Trend('t_static', true);
const errors = new Rate('app_errors'); const loginFail = new Counter('login_failures');

const stageList = [50, 200, 300, 500, 1000, 1500];
const rampStages = [];
for (const n of stageList) { rampStages.push({ duration: '1m', target: n }); rampStages.push({ duration: HOLD, target: n }); }
rampStages.push({ duration: '30s', target: 0 });

const scenarios = {
  ramp: {
    students: { executor: 'ramping-vus', exec: 'student', startVUs: 0, stages: rampStages, gracefulRampDown: '30s' },
    admin: { executor: 'constant-vus', exec: 'admin', vus: 3, duration: `${stageList.length * 4 + 1}m`, startTime: '1m' },
  },
  login_storm: {  // ~1000 different students log in inside 5 minutes (start of class), 300 of them in the first minute
    storm: { executor: 'ramping-arrival-rate', exec: 'loginOnly', startRate: 5, timeUnit: '1s', preAllocatedVUs: 300, maxVUs: 1200,
             stages: [{ duration: '1m', target: 5 }, { duration: '10s', target: 3 }, { duration: '4m', target: 3 }] },
  },
  quiz_burst: {  // 500 students submit the same quiz inside one minute
    burst: { executor: 'per-vu-iterations', exec: 'quizBurst', vus: 500, iterations: 1, maxDuration: '10m' },
  },
  soak: {
    soak: { executor: 'constant-vus', exec: 'student', vus: Number(__ENV.SOAK_VUS || 300), duration: `${__ENV.SOAK_MIN || 30}m` },
    admin: { executor: 'constant-vus', exec: 'admin', vus: 2, duration: `${__ENV.SOAK_MIN || 30}m` },
  },
};
export const options = {
  scenarios: scenarios[SCENARIO],
  thresholds: { http_req_failed: ['rate<0.01'], app_errors: ['rate<0.01'], t_page: ['p(95)<1500'] },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  discardResponseBodies: false,
  noConnectionReuse: false,
  noCookiesReset: true,   // keep each simulated student logged in across iterations, like a real browser
};

const csrf = (body) => { const m = /name="csrfmiddlewaretoken" value="([^"]+)"/.exec(body || ''); return m ? m[1] : ''; };
// A redirect to /login/ means the simulated student lost their session: count it as an error, not a success.
const ok = (r, name) => { const good = r.status >= 200 && r.status < 400 && !(r.url || '').includes('/login/');
  errors.add(!good); if (!good) console.warn(`${name} -> ${r.status} ${r.url}`); return good; };
const tag = (name) => ({ tags: { name } });

function userFor(n) { return `lt${String(((n - 1) % N_USERS) + 1).padStart(4, '0')}`; }
function coursesFor(username) { const i = Number(username.slice(2)) - 1; return [0, 1, 2].map(k => `qa-course-${((i + k) % 10) + 1}`); }

function login(username) {
  const jar = http.cookieJar();
  let r = http.get(`${B}/login/`, tag('GET /login/'));
  const token = csrf(r.body);
  r = http.post(`${B}/login/`, { username, password: PW, csrfmiddlewaretoken: token },
    { headers: { Referer: `${B}/login/` }, redirects: 0, ...tag('POST /login/') });
  tLogin.add(r.timings.duration);
  const good = r.status === 302 && !(r.headers.Location || '').includes('/login/');
  if (!good) { loginFail.add(1); errors.add(true); console.warn(`login ${username} -> ${r.status}`); }
  return good;
}

function page(path, name) { const r = http.get(`${B}${path}`, tag(name)); tPage.add(r.timings.duration); ok(r, name); return r; }

function statics(body) {  // a first visit pulls CSS/JS/fonts; browsers cache them afterwards (hashed names, long max-age)
  const urls = [...new Set((body.match(/\/static\/[^"' )]+/g) || []))].slice(0, 6);
  for (const u of urls) { const r = http.get(`${B}${u}`, tag('static')); tStatic.add(r.timings.duration); ok(r, 'static'); }
}

const state = {};
export function student() {
  const id = exec.vu.idInTest;
  if (!state.user) {
    state.user = userFor(id); state.courses = coursesFor(state.user);
    if (!login(state.user)) { state.user = null; sleep(5); return; }
    const d = page('/dashboard/', 'dashboard'); statics(d.body);
  }
  const slug = state.courses[Math.floor(Math.random() * 3)];
  group('browse', () => {
    page('/dashboard/', 'dashboard'); sleep(2 + Math.random() * 6);
    const c = page(`/courses/${slug}/`, 'course'); sleep(2 + Math.random() * 6);
    const lessons = [...new Set((c.body.match(new RegExp(`/courses/${slug}/lessons/\\d+/`, 'g')) || []))];
    if (lessons.length) {
      const lp = lessons[Math.floor(Math.random() * lessons.length)];
      const l = page(lp, 'lesson'); sleep(5 + Math.random() * 10);   // watching (video itself is on YouTube/Bunny)
      if (Math.random() < 0.5) {
        const r = http.post(`${B}${lp}`, { csrfmiddlewaretoken: csrf(l.body) }, { headers: { Referer: `${B}${lp}` }, redirects: 0, ...tag('POST lesson complete') });
        tPage.add(r.timings.duration); ok(r, 'lesson complete');
      }
    }
    if (Math.random() < 0.3) { page('/doubts/', 'doubts'); sleep(2 + Math.random() * 5); }
    if (Math.random() < 0.2) {
      const qm = /\/courses\/[^/]+\/quizzes\/\d+\//.exec(c.body);
      if (qm) {
        const q = page(qm[0], 'quiz'); sleep(10 + Math.random() * 20);
        const answers = { csrfmiddlewaretoken: csrf(q.body) };
        for (const m of q.body.matchAll(/name="(q\d+)" value="(\d+)"/g)) if (!answers[m[1]] || Math.random() < 0.3) answers[m[1]] = m[2];
        const r = http.post(`${B}${qm[0]}`, answers, { headers: { Referer: `${B}${qm[0]}` }, redirects: 0, ...tag('POST quiz') });
        tQuiz.add(r.timings.duration); ok(r, 'quiz submit');
      }
    }
    if (Math.random() < 0.1) page('/certificates/', 'certificates');
  });
  sleep(3 + Math.random() * 7);
}

export function admin() {
  if (!state.user) { state.user = 'qa_owner'; if (!login('qa_owner')) { state.user = null; sleep(5); return; } }
  const c = `qa-course-${1 + Math.floor(Math.random() * 10)}`;
  for (const [p, n] of [['/dashboard/', 'admin dashboard'], ['/students/', 'admin students overview'], [`/courses/${c}/report/`, 'admin course report'],
                        ['/users/?role=student', 'admin user list'], ['/doubts/?tab=all', 'admin doubts']]) {
    const r = http.get(`${B}${p}`, tag(n)); tReport.add(r.timings.duration); ok(r, n); sleep(3 + Math.random() * 5);
  }
}

export function loginOnly() {
  const u = userFor(exec.scenario.iterationInTest + 1);
  if (login(u)) page('/dashboard/', 'dashboard');
  http.cookieJar().clear(B);
}

export function quizBurst() {
  const u = userFor(exec.vu.idInTest);
  if (!login(u)) return;
  const slug = coursesFor(u)[0];
  const c = http.get(`${B}/courses/${slug}/`, tag('course'));
  const qm = /\/courses\/[^/]+\/quizzes\/\d+\//.exec(c.body);
  if (!qm) { errors.add(true); return; }
  const q = page(qm[0], 'quiz');
  // everyone presses Submit within the same minute
  const startAt = Number(__ENV.BURST_AT || 0);
  const wait = startAt ? Math.max(0, startAt - Date.now() / 1000) : 0;
  sleep(wait + Math.random() * 60);
  const answers = { csrfmiddlewaretoken: csrf(q.body) };
  for (const m of q.body.matchAll(/name="(q\d+)" value="(\d+)"/g)) if (!answers[m[1]]) answers[m[1]] = m[2];
  const r = http.post(`${B}${qm[0]}`, answers, { headers: { Referer: `${B}${qm[0]}` }, redirects: 0, ...tag('POST quiz') });
  tQuiz.add(r.timings.duration);
  check(r, { 'quiz stored (302 to result)': (x) => x.status === 302 && (x.headers.Location || '').includes('/result/') });
  ok(r, 'quiz submit');
}
