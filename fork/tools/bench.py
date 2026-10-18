#!/usr/bin/env python3
"""Ismételhető CLI-szeletelési teljesítménymérés (referencia: helmet + tree support). Csak a build/bench/ alá ír.

Minden futás: rögzített process-profil (fork/bench/process/helmet-tree.json), --debug 4, falidő / user / sys / csúcs-RSS
(os.wait4), a verbose log [fork-perf] és [fork-exp] sorai, fázis-jelek, geometriai digest (a G-code "; " kommentek és az
ismert --parallel zaj (_SUPP_INTERFACE_FAN) nélkül), opcionálisan CPU-kihasználtság fázisonként (pidstat) és
gperftools CPU-profil. A nagy kimenetek (G-code, .moves) futás után törlődnek, hacsak nincs --keep.

Használat:
  python3 fork/tools/bench.py run LABEL [--runs N] [--env K=V ...] [--cpu] [--profile] [--keep]
                                  [--bin B] [--stl F] [--process F] [--machine F] [--filament F]
                                  [--serial] [-- további orca-slicer argumentumok]
  python3 fork/tools/bench.py compare LABEL_A LABEL_B
  python3 fork/tools/bench.py list

Példák:
  python3 fork/tools/bench.py run base --runs 3
  python3 fork/tools/bench.py run proto --runs 3 --env ORCA_EXP_X=1
  python3 fork/tools/bench.py compare base proto
  python3 fork/tools/bench.py run prof --profile && \\
      python3 fork/tools/gprof-report.py build/src/Release/orca-slicer build/bench/prof/run-1/cpu.prof --top 40

Megjegyzések:
  - A mérési zaj ezen a gépen ~±4% (háttérben VS Code / GUI): döntéshez --runs 3 és medián.
  - --profile: LD_PRELOAD="libgcc_s.so.1 libprofiler.so.0" (a libgcc_s előre kell, különben a libprofiler által
    behúzott libunwind felülírja az _Unwind_* szimbólumokat, és az első C++ kivételnél SIGSEGV jön). Strippelt
    binárisnál (build_linux.sh -x) a profil szimbólumok nélkül értéktelen.
  - A kimenet NE tmpfs-re (/tmp) menjen: egy futás ~2 GB G-code + .moves.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SYSTEM = os.path.expanduser("~/.config/OrcaSlicer/system/Ratrig")
DEFAULTS = {
    "bin": os.path.join(REPO, "build/src/Release/orca-slicer"),
    "stl": os.environ.get("ORCA_BENCH_STL", os.path.expanduser("~/Letöltések/Battle_Damaged_Helmet.stl")),
    "process": os.path.join(REPO, "fork/bench/process/helmet-tree.json"),
    "machine": os.path.join(SYSTEM, "machine/RatRig V-Core 4 IDEX 500 0.4 nozzle.json"),
    "filament": os.path.join(SYSTEM, "filament/RatRig Generic ABS.json"),
}
OUT_ROOT = os.environ.get("ORCA_BENCH_OUT", os.path.join(REPO, "build/bench"))
LIBDIR = "/usr/lib/x86_64-linux-gnu"

LOG_RE = re.compile(r"^\[(\w+)\]\s+(\S+ \S+)\[Thread [^\]]*\]:(.*)")
PERF_RE = re.compile(r"\[fork-perf\] (.+): ([0-9.]+) ms$")
# Fázis-jelek: (név, a log-üzenet egy részlete). Ami nem fordul elő (pl. nincs tree support), kimarad.
MARKS = [
    ("tree_precalc_done", "Precalculating collision"),
    ("pathing_done", "creating influence areas' subtasks"),
    ("support_done", "Total time used creating Tree support"),
    ("export_start", "will export gcode temporarily"),
]
NOISE_FILTER = r"^; \|_SUPP_INTERFACE_FAN"


def parse_log(path):
    t0 = last = None
    marks, perf, exp = {}, {}, []
    with open(path, errors="replace") as f:
        for line in f:
            m = LOG_RE.match(line)
            if not m:
                continue
            t = datetime.datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S.%f").timestamp()
            if t0 is None:
                t0 = t
            last = t
            msg = m.group(3).rstrip()
            for name, needle in MARKS:
                if name not in marks and needle in msg:
                    marks[name] = round(t - t0, 2)
            if "[fork-perf]" in msg:
                pm = PERF_RE.search(msg)
                if pm:
                    perf[pm.group(1)] = float(pm.group(2))
            elif "[fork-exp]" in msg:
                exp.append(msg[msg.index("[fork-exp]"):])
    if last is not None:
        marks["end"] = round(last - t0, 2)
    return t0, marks, perf, exp


def geometry_digest(gcode):
    grep = subprocess.Popen(["grep", "-v", NOISE_FILTER, gcode], stdout=subprocess.PIPE)
    h = hashlib.sha256()
    for chunk in iter(lambda: grep.stdout.read(1 << 22), b""):
        h.update(chunk)
    grep.wait()
    return h.hexdigest()[:16]


def cpu_by_phase(pidstat_txt, t0, marks):
    samples = []
    for line in pidstat_txt.splitlines():
        p = line.split()
        if len(p) > 8 and ":" in p[0] and p[1].isdigit():
            hh, mm, ss = map(int, p[0].split(":"))
            day = datetime.datetime.fromtimestamp(t0)
            t = day.replace(hour=hh, minute=mm, second=ss, microsecond=0).timestamp() - t0 - 0.5
            samples.append((t, float(p[7]) / 100.0))
    bounds = [("start", 0.0)] + sorted(((k, v) for k, v in marks.items()), key=lambda kv: kv[1])
    out = {}
    for (a, ta), (b, tb) in zip(bounds, bounds[1:]):
        s = [c for t, c in samples if ta <= t < tb]
        if s:
            out[f"{a}->{b}"] = round(sum(s) / len(s), 1)
    return out


def run_once(args, run_dir, extra):
    os.makedirs(os.path.join(run_dir, "out"), exist_ok=True)
    cmd = [args.bin, "--debug", "4",
           "--load-settings", f"{args.machine};{args.process}",
           "--load-filaments", args.filament, "--filament-colour", "#CCCCCC", "--slice", "0",
           "--outputdir", os.path.join(run_dir, "out"), args.stl]
    if not args.serial:
        cmd.append("--parallel")
    cmd += extra
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    for kv in args.env or []:
        k, _, v = kv.partition("=")
        env[k] = v
    if args.profile:
        env["LD_PRELOAD"] = f"{LIBDIR}/libgcc_s.so.1 {LIBDIR}/libprofiler.so.0"
        env["CPUPROFILE"] = os.path.join(run_dir, "cpu.prof")
        env.setdefault("CPUPROFILE_FREQUENCY", "250")
    with open(os.path.join(run_dir, "cmd.txt"), "w") as f:
        f.write(" ".join(cmd) + "\n" + " ".join(args.env or []) + "\n")
    stdout = open(os.path.join(run_dir, "stdout.log"), "w")
    t_start = time.time()
    proc = subprocess.Popen(cmd, stdout=stdout, stderr=subprocess.STDOUT, env=env)
    pidstat = None
    if args.cpu and shutil.which("pidstat"):
        pidstat = subprocess.Popen(["pidstat", "-u", "-h", "-p", str(proc.pid), "1"], stdout=subprocess.PIPE, text=True)
    _, status, ru = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    wall = time.time() - t_start
    stdout.close()
    pid_txt = ""
    if pidstat:
        pidstat.terminate()
        pid_txt = pidstat.communicate()[0]
        with open(os.path.join(run_dir, "pidstat.txt"), "w") as f:
            f.write(pid_txt)

    res = {"exit": proc.returncode, "wall_s": round(wall, 2), "user_s": round(ru.ru_utime, 1),
           "sys_s": round(ru.ru_stime, 1), "rss_mb": ru.ru_maxrss // 1024}
    log_path = None
    m = re.search(r"verbose log at (\S+)", open(os.path.join(run_dir, "stdout.log"), errors="replace").read())
    if m:
        log_path = re.sub(r"\.\*$", ".0", m.group(1))
    if log_path and os.path.exists(log_path):
        shutil.copy(log_path, os.path.join(run_dir, "verbose.log"))
        t0, marks, perf, exp = parse_log(log_path)
        res.update(marks=marks, perf=perf, exp=exp)
        if pid_txt and t0:
            res["cpu_cores_by_phase"] = cpu_by_phase(pid_txt, t0, marks)
    gcode = os.path.join(run_dir, "out", "plate_1.gcode")
    if os.path.exists(gcode):
        res["gcode_bytes"] = os.path.getsize(gcode)
        res["digest"] = geometry_digest(gcode)
        if not args.keep:
            for p in (gcode, gcode + ".moves"):
                if os.path.exists(p):
                    os.remove(p)
    else:
        res["digest"] = None
    with open(os.path.join(run_dir, "result.json"), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


def summarize(runs):
    ok = [r for r in runs if r.get("exit") == 0]
    s = {"runs": len(runs), "ok": len(ok), "digests": sorted({str(r.get("digest")) for r in runs})}
    for key in ("wall_s", "user_s", "sys_s", "rss_mb"):
        vals = [r[key] for r in ok if key in r]
        if vals:
            s[key] = round(statistics.median(vals), 2)
            s[key + "_spread"] = round(max(vals) - min(vals), 2)
    for group in ("marks", "perf"):
        names = sorted({n for r in ok for n in r.get(group, {})})
        s[group] = {n: round(statistics.median([r[group][n] for r in ok if n in r.get(group, {})]), 1) for n in names}
    return s


def print_summary(label, s):
    print(f"[{label}] runs={s['runs']} ok={s['ok']} wall={s.get('wall_s')}s (±{s.get('wall_s_spread')}) "
          f"user={s.get('user_s')}s sys={s.get('sys_s')}s rss={s.get('rss_mb')}MB digest={','.join(s['digests'])}")
    if s["marks"]:
        print("  phases (s): " + "  ".join(f"{k}={v}" for k, v in s["marks"].items()))
    for k, v in s["perf"].items():
        print(f"  {k}: {v} ms")


def cmd_run(args, extra):
    for key, val in DEFAULTS.items():
        if getattr(args, key) is None:
            setattr(args, key, val)
    for key in ("bin", "stl", "process", "machine", "filament"):
        if not os.path.exists(getattr(args, key)):
            sys.exit(f"nem található ({key}): {getattr(args, key)}")
    if args.profile and b", stripped" in subprocess.run(["file", args.bin], capture_output=True).stdout:
        print("FIGYELEM: a bináris strippelt, a profil szimbólumok nélkül készül.", file=sys.stderr)
    label_dir = os.path.join(OUT_ROOT, args.label)
    if os.path.exists(label_dir):
        shutil.rmtree(label_dir)
    runs = []
    for i in range(1, args.runs + 1):
        r = run_once(args, os.path.join(label_dir, f"run-{i}"), extra)
        runs.append(r)
        print(f"  run {i}/{args.runs}: exit={r['exit']} wall={r['wall_s']}s digest={r.get('digest')}"
              + (f" cpu={r['cpu_cores_by_phase']}" if r.get("cpu_cores_by_phase") else ""), flush=True)
        for line in r.get("exp", []):
            print("    " + line)
    s = summarize(runs)
    s["env"] = args.env or []
    s["extra"] = extra
    with open(os.path.join(label_dir, "summary.json"), "w") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    print_summary(args.label, s)
    if len(s["digests"]) > 1:
        print("FIGYELEM: a futások geometriája eltér egymástól (nemdeterminisztikus kimenet).")


def load_summary(label):
    p = os.path.join(OUT_ROOT, label, "summary.json")
    if not os.path.exists(p):
        sys.exit(f"nincs ilyen mérés: {label}")
    return json.load(open(p))


def cmd_compare(a, b):
    sa, sb = load_summary(a), load_summary(b)
    same = sa["digests"] == sb["digests"] and len(sa["digests"]) == 1
    print(f"geometria: {'AZONOS' if same else 'ELTÉR'} ({','.join(sa['digests'])} vs {','.join(sb['digests'])})")

    def row(name, va, vb, unit):
        if va is None or vb is None:
            return
        d = vb - va
        pct = (100.0 * d / va) if va else 0.0
        print(f"  {name:62s} {va:10.1f} {vb:10.1f} {d:+10.1f} {unit} ({pct:+.1f}%)")
    print(f"  {'':62s} {a:>10s} {b:>10s}")
    for key, unit in (("wall_s", "s"), ("user_s", "s"), ("sys_s", "s"), ("rss_mb", "MB")):
        row(key, sa.get(key), sb.get(key), unit)
    for name in sorted(set(sa["marks"]) | set(sb["marks"]), key=lambda n: sa["marks"].get(n, sb["marks"].get(n, 0))):
        row("phase " + name, sa["marks"].get(name), sb["marks"].get(name), "s")
    for name in sorted(set(sa["perf"]) | set(sb["perf"])):
        row(name, sa["perf"].get(name), sb["perf"].get(name), "ms")


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("label")
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--env", action="append", help="K=V környezeti változó (ismételhető)")
    r.add_argument("--cpu", action="store_true", help="CPU-kihasználtság fázisonként (pidstat)")
    r.add_argument("--profile", action="store_true", help="gperftools CPU-profil (run-N/cpu.prof)")
    r.add_argument("--keep", action="store_true", help="G-code és .moves megtartása")
    r.add_argument("--serial", action="store_true", help="--parallel nélkül")
    for key in DEFAULTS:
        r.add_argument("--" + key, default=None, help=f"alap: {DEFAULTS[key]}")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        cmd_run(args, extra)
    elif args.cmd == "compare":
        cmd_compare(args.a, args.b)
    else:
        if os.path.isdir(OUT_ROOT):
            for label in sorted(os.listdir(OUT_ROOT)):
                p = os.path.join(OUT_ROOT, label, "summary.json")
                if os.path.exists(p):
                    s = json.load(open(p))
                    print(f"{label:30s} wall={s.get('wall_s')}s runs={s['runs']} digest={','.join(s['digests'])}")


if __name__ == "__main__":
    main()
