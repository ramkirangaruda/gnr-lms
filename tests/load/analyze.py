"""Per-stage latency/error/throughput table from a k6 CSV (+ the monitor.sh CSV).

    python3 tests/load/analyze.py ramp.csv.gz ramp_mon.csv --stages 50,200,300,500,1000,1500 --ramp 60 --hold 180
    python3 tests/load/analyze.py soak.csv.gz soak_mon.csv --window 300       # 5-minute buckets
"""
import argparse
import csv
import gzip
import statistics
from collections import defaultdict


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


ap = argparse.ArgumentParser()
ap.add_argument("k6csv"); ap.add_argument("moncsv", nargs="?")
ap.add_argument("--stages"); ap.add_argument("--ramp", type=int, default=60); ap.add_argument("--hold", type=int, default=180)
ap.add_argument("--window", type=int)
a = ap.parse_args()

rows = defaultdict(lambda: {"dur": [], "page": [], "login": [], "quiz": [], "fail": 0, "n": 0, "codes": defaultdict(int)})
t0 = None
op = gzip.open if a.k6csv.endswith(".gz") else open
with op(a.k6csv, "rt") as f:
    for r in csv.DictReader(f):
        ts = int(r["timestamp"])
        t0 = ts if t0 is None else min(t0, ts)
        rows[ts]  # keep ts
        m = r["metric_name"]
        if m not in ("http_req_duration", "http_req_failed", "t_login", "t_quiz_submit"):
            continue
        b = rows[ts]
        v = float(r["metric_value"])
        if m == "http_req_duration":
            b["n"] += 1; b["dur"].append(v); b["codes"][r["status"]] += 1
            if r["name"] not in ("static",) and not r["name"].startswith(("GET /login/", "POST /login/")):
                b["page"].append(v)
        elif m == "http_req_failed":
            b["fail"] += int(v)
        elif m == "t_login":
            b["login"].append(v)
        elif m == "t_quiz_submit":
            b["quiz"].append(v)

mon = []
if a.moncsv:
    with open(a.moncsv) as f:
        for r in csv.DictReader(f):
            mon.append(r)

if a.stages:
    windows, t = [], t0
    for n in a.stages.split(","):
        t += a.ramp
        windows.append((f"{n} VUs", t, t + a.hold)); t += a.hold
else:
    end = max(rows)
    windows = [(f"{(s - t0) // 60}-{(s - t0 + a.window) // 60} min", s, s + a.window) for s in range(t0, end, a.window)]

print("| Stage | Requests/s | Page p50 | Page p95 | Page p99 | Login p50 | Login p95 | Quiz submit p95 | Errors | Non-2xx/3xx codes |")
print("|---|---|---|---|---|---|---|---|---|---|")
for name, s, e in windows:
    d, pg, lg, qz, fail, n, codes = [], [], [], [], 0, 0, defaultdict(int)
    for ts in range(s, e):
        b = rows.get(ts)
        if not b:
            continue
        pg += b["page"]; lg += b["login"]; qz += b["quiz"]; fail += b["fail"]; n += b["n"]
        for k, v in b["codes"].items():
            codes[k] += v
    bad = {k: v for k, v in codes.items() if not k.startswith(("2", "3"))}
    f = lambda x: "–" if x != x else (f"{x / 1000:.2f} s" if x >= 1000 else f"{x:.0f} ms")
    print(f"| {name} | {n / max(1, e - s):.1f} | {f(pct(pg, 50))} | {f(pct(pg, 95))} | {f(pct(pg, 99))} | {f(pct(lg, 50))} | {f(pct(lg, 95))} | "
          f"{f(pct(qz, 95))} | {100 * fail / max(1, n):.2f}% | {dict(bad) or '–'} |")

if mon:
    import datetime as dt
    print("\n| Stage | web CPU avg (of 200%) | web RAM max | db CPU avg | db RAM max | DB connections max |")
    print("|---|---|---|---|---|---|")
    day = dt.datetime.fromtimestamp(t0, dt.timezone.utc).date()
    for name, s, e in windows:
        sel = [r for r in mon if s <= dt.datetime.combine(day, dt.time.fromisoformat(r["time"])).replace(tzinfo=dt.timezone.utc).timestamp() < e]
        def cpu(c): return [float(r["cpu"].rstrip("%")) for r in sel if c in r["container"]]
        def mem(c): return [r["mem"].split("/")[0].strip() for r in sel if c in r["container"]]
        conns = [int(r["db_conns"]) for r in sel if r.get("db_conns", "").isdigit()]
        avg = lambda xs: f"{statistics.mean(xs):.0f}%" if xs else "–"
        def mx(ms):
            def mib(x):
                return float(x[:-3]) * (1024 if x.endswith("GiB") else 1) if x.endswith(("MiB", "GiB")) else 0
            return f"{max(map(mib, ms)):.0f} MiB" if ms else "–"
        print(f"| {name} | {avg(cpu('web'))} | {mx(mem('web'))} | {avg(cpu('db'))} | {mx(mem('db'))} | {max(conns) if conns else '–'} |")
