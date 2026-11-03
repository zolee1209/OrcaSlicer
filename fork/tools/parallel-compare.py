#!/usr/bin/env python3
"""A --parallel (chunkolt) G-code összevetése a soros úttal. Csak a build/parallel-compare/ alá ír.

Minden futás: ugyanaz a modell + profil soros szeleteléssel és --parallel-lel (alap hullámszám, majd
ORCA_PARALLEL_WAVES=64 stresszpróba: kb. 2 rétegenként új chunk-határ). Összehasonlítás rétegenként:
a rétegek száma/z-je, a rétegkezdő szerszám, a rétegen belüli szerszámváltások sorrendje, és (szerszám, ;TYPE:)
szerinti extrudált hossz + befoglaló doboz. A chunk-határokon várt (utazó mozgások, vissza-/törlőmozgás, sorrend)
eltérések nem számítanak; ami számít: szerszám/szín, réteg, skirt/draft shield, torony, support.

Használat:
  python3 fork/tools/parallel-compare.py [--set kulcs=érték ...] [--clone N] [--waves N] [--keep]
          [--bin B] [--machine F] [--process NÉV_VAGY_FÁJL] MODELL...
  Több MODELL = külön filament-slot modellenként (--assemble, mint a www alkalmazás multicolor útja);
  egy MODELL + --clone N = egyszínű, N példány.

Példák:
  python3 fork/tools/parallel-compare.py benchy.stl bunny.stl cone.stl
  python3 fork/tools/parallel-compare.py --set toolchange_ordering=cyclic a.stl b.stl c.stl
  python3 fork/tools/parallel-compare.py --set draft_shield=enabled --clone 3 benchy.stl

Kilépési kód: 0 = nincs eltérés, 1 = eltérés, 2 = futási hiba.
Megjegyzés: a --set a felhasználói process-profil ideiglenes másolatát (zzct_*.json) a profil mellé írja, mert a CLI az
`inherits` láncot csak a konfigurációs mappából oldja fel; a futás végén törlődik.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SYSTEM = os.path.expanduser("~/.config/OrcaSlicer/system/Ratrig")
USER_PROCESS = os.path.expanduser("~/.config/OrcaSlicer/user/default/process")
DEFAULTS = {
    "bin": os.path.join(REPO, "build/src/Release/orca-slicer"),
    "machine": os.path.join(SYSTEM, "machine/RatRig V-Core 4 IDEX 500 0.4 nozzle.json"),
    "process": "0.20mm @RatRig V-Core 4 IDEX 500 0.4",
    "filament": os.path.join(SYSTEM, "filament/RatRig Generic ABS.json"),
}
OUT = os.path.join(REPO, "build/parallel-compare")

TOOL_RE = re.compile(r"^T(\d+)\b")
E_RE = re.compile(r"\bE(-?[\d.]+)")
X_RE = re.compile(r"\bX(-?[\d.]+)")
Y_RE = re.compile(r"\bY(-?[\d.]+)")


def parse(path):
    layers = []
    cur = None
    tool = None
    typ = None
    pos = [None, None]
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith(";Z:") or line.startswith("; Z_HEIGHT:"):
                cur = {"z": float(line.split(":")[1]), "tools": [], "start_tool": tool, "ext": defaultdict(float),
                       "bbox": defaultdict(lambda: [1e9, 1e9, -1e9, -1e9])}
                layers.append(cur)
                continue
            if line.startswith(";TYPE:"):
                typ = line[6:].strip()
                continue
            m = TOOL_RE.match(line)
            if m:
                tool = int(m.group(1))
                if cur is not None:
                    cur["tools"].append(tool)
                continue
            if cur is None or not (line.startswith("G1") or line.startswith("G0")):
                continue
            mx, my, me = X_RE.search(line), Y_RE.search(line), E_RE.search(line)
            if mx:
                pos[0] = float(mx.group(1))
            if my:
                pos[1] = float(my.group(1))
            if me and (mx or my) and float(me.group(1)) > 0:
                key = (tool, typ)
                cur["ext"][key] += float(me.group(1))
                if pos[0] is not None and pos[1] is not None:
                    b = cur["bbox"][key]
                    b[0], b[1] = min(b[0], pos[0]), min(b[1], pos[1])
                    b[2], b[3] = max(b[2], pos[0]), max(b[3], pos[1])
    return layers


def compare(a, b, bbox_tol=0.4, max_report=40):
    la, lb = parse(a), parse(b)
    problems = []
    if len(la) != len(lb):
        problems.append(f"layer count {len(la)} vs {len(lb)}")
    for i, (x, y) in enumerate(zip(la, lb)):
        msgs = []
        if abs(x["z"] - y["z"]) > 1e-6:
            msgs.append(f"z {x['z']} vs {y['z']}")
        if x["start_tool"] != y["start_tool"]:
            msgs.append(f"start tool {x['start_tool']} vs {y['start_tool']}")
        if x["tools"] != y["tools"]:
            msgs.append(f"tool changes {x['tools']} vs {y['tools']}")
        for k in sorted(set(x["ext"]) | set(y["ext"]), key=str):
            ea, eb = x["ext"].get(k, 0.0), y["ext"].get(k, 0.0)
            if abs(ea - eb) > 0.02 * max(1.0, abs(ea)):
                msgs.append(f"{k}: extruded {ea:.2f} vs {eb:.2f}")
            elif max(abs(p - q) for p, q in zip(x["bbox"][k], y["bbox"][k])) > bbox_tol:
                msgs.append(f"{k}: bbox {[round(v, 2) for v in x['bbox'][k]]} vs {[round(v, 2) for v in y['bbox'][k]]}")
        if msgs:
            problems.append(f"layer {i} z={x['z']}: " + "; ".join(msgs[:5]))
    if len(problems) > max_report:
        problems = problems[:max_report] + [f"... {len(problems) - max_report} more"]
    return len(la), problems


def run_orca(args, label, parallel, waves, process_path, models):
    out = os.path.join(OUT, label)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    n = len(models)
    fil = args.filament
    cmd = [args.bin, "--debug", "4", "--load-settings", f"{args.machine};{process_path}",
           "--load-filaments", ";".join([fil] * n), "--filament-colour", ";".join(["#CCCCCC"] * n)]
    if parallel:
        cmd.append("--parallel")
    if n > 1:
        cmd.append("--assemble")
    cmd += ["--slice", "0", "--outputdir", out] + [os.path.abspath(m) for m in models]
    if n > 1:
        cmd += ["--load-filament-ids", ",".join(str(i + 1) for i in range(n))]
    elif args.clone > 1:
        cmd += ["--clone-objects", str(args.clone)]
    env = dict(os.environ)
    if waves:
        env["ORCA_PARALLEL_WAVES"] = str(waves)
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
    gcode = os.path.join(out, "plate_1.gcode")
    if r.returncode != 0 or not os.path.exists(gcode):
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        print(f"  {label}: a futás sikertelen (kód {r.returncode}): {tail}")
        return None
    return gcode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--bin", default=DEFAULTS["bin"])
    ap.add_argument("--machine", default=DEFAULTS["machine"])
    ap.add_argument("--process", default=DEFAULTS["process"])
    ap.add_argument("--filament", default=DEFAULTS["filament"])
    ap.add_argument("--set", action="append", default=[], metavar="KULCS=ÉRTÉK")
    ap.add_argument("--clone", type=int, default=1)
    ap.add_argument("--waves", type=int, default=64, help="a stresszpróba hullámszáma (0 = kihagyva)")
    ap.add_argument("--keep", action="store_true", help="a G-code fájlok megtartása")
    args = ap.parse_args()

    process = args.process if os.path.isfile(args.process) else os.path.join(USER_PROCESS, args.process + ".json")
    temp_process = None
    if args.set:
        data = json.load(open(process))
        for item in args.set:
            key, _, value = item.partition("=")
            data[key] = value
        temp_process = os.path.join(USER_PROCESS, "zzct_%d.json" % os.getpid())
        data["name"] = os.path.basename(temp_process)[:-5]
        json.dump(data, open(temp_process, "w"), indent=1)
        process = temp_process

    status = 0
    try:
        serial = run_orca(args, "serial", False, None, process, args.models)
        if serial is None:
            return 2
        for label, waves in (("parallel", None), ("parallel-stress", args.waves or None)):
            if label == "parallel-stress" and not args.waves:
                continue
            gcode = run_orca(args, label, True, waves, process, args.models)
            if gcode is None:
                status = 2
                continue
            layers, problems = compare(serial, gcode)
            print(f"{label}: {layers} réteg, " + ("nincs eltérés" if not problems else f"{len(problems)} eltérés"))
            for p in problems:
                print("   " + p)
            if problems:
                status = max(status, 1)
    finally:
        if temp_process and os.path.exists(temp_process):
            os.remove(temp_process)
        if not args.keep:
            for label in ("serial", "parallel", "parallel-stress"):
                shutil.rmtree(os.path.join(OUT, label), ignore_errors=True)
    return status


if __name__ == "__main__":
    sys.exit(main())
