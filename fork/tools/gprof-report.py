#!/usr/bin/env python3
"""gperftools CPU-profil (legacy bináris formátum) kiértékelése nm-alapú szimbolizálással. Csak olvas.

A profilt a bench.py --profile készíti (LD_PRELOAD libprofiler, perf/sudo/ptrace nélkül).
Feltétel: a bináris NEM strippelt (a `build_linux.sh -x` strippel; a sima ninja build nem).
Külső könyvtárak mintái `<libnév>` néven jelennek meg.

Használat:
  python3 fork/tools/gprof-report.py BINARY PROFILE [--top N] [--cum]
          [--match REGEX] [--callers REGEX] [--within REGEX] [--width N]
  --cum      inkluzív (cum) szerinti rendezés
  --callers  a REGEX-re illő függvény hívóinak bontása (külső lib: csak levél-minták)
  --within   a REGEX-et tartalmazó stackeken belül a hívott függvények inkluzív aránya
"""
import argparse, bisect, collections, re, struct, subprocess, sys


def load_profile(path):
    data = open(path, 'rb').read()
    w = 8
    words = struct.unpack_from('<5Q', data, 0)
    assert words[0] == 0 and words[1] == 3, 'not a gperftools 64-bit profile'
    period_us = words[3]
    pos = 5 * w
    samples = []
    while True:
        n, depth = struct.unpack_from('<2Q', data, pos)
        pos += 2 * w
        pcs = struct.unpack_from('<%dQ' % depth, data, pos)
        pos += depth * w
        if n == 0 and depth == 1 and pcs[0] == 0:
            break
        samples.append((n, pcs))
    maps = data[pos:].decode('utf-8', 'replace')
    return period_us, samples, maps


def load_symbols(binary):
    out = subprocess.run(['nm', '-C', '--defined-only', '-n', binary], capture_output=True, text=True).stdout
    addrs, names = [], []
    for line in out.splitlines():
        p = line.split(' ', 2)
        if len(p) == 3 and p[1] in 'tTwW':
            addrs.append(int(p[0], 16))
            names.append(p[2])
    # vaddr - file offset of the executable LOAD segment
    ph = subprocess.run(['readelf', '-lW', binary], capture_output=True, text=True).stdout
    segs = []
    for line in ph.splitlines():
        p = line.split()
        if p and p[0] == 'LOAD':
            segs.append((int(p[1], 16), int(p[2], 16), int(p[4], 16)))  # offset, vaddr, filesz
    return addrs, names, segs


def short(name, width=150):
    # Strip template / argument noise for readability.
    s = re.sub(r'\(.*', '', name) if 'lambda' not in name and '$_' not in name else name
    s = s.replace('Slic3r::', '').replace('std::', '').replace('tbb::detail::', 'tbb::')
    return s[:width]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('binary')
    ap.add_argument('profile')
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--cum', action='store_true', help='sort by cumulative (inclusive) samples')
    ap.add_argument('--match', help='only report functions matching REGEX')
    ap.add_argument('--callers', help='print callers breakdown of functions matching REGEX')
    ap.add_argument('--within', help='inclusive breakdown (cum) of all functions inside stacks containing REGEX')
    ap.add_argument('--width', type=int, default=150)
    a = ap.parse_args()

    period_us, samples, maps = load_profile(a.profile)
    addrs, names, segs = load_symbols(a.binary)
    binname = a.binary.split('/')[-1]
    regions, libs = [], []
    for line in maps.splitlines():
        p = line.split()
        if len(p) >= 6 and 'x' in p[1]:
            lo, hi = (int(x, 16) for x in p[0].split('-'))
            if p[5].endswith('/' + binname):
                regions.append((lo, hi, int(p[2], 16)))
            else:
                libs.append((lo, hi, p[5].split('/')[-1]))
    if not regions:
        sys.exit('binary mapping not found in profile')

    cache = {}

    def sym(pc):
        if pc in cache:
            return cache[pc]
        r = None
        for lo, hi, off in regions:
            if lo <= pc < hi:
                foff = pc - lo + off
                for so, sv, sz in segs:
                    if so <= foff < so + sz:
                        va = foff - so + sv
                        i = bisect.bisect_right(addrs, va) - 1
                        r = names[i] if i >= 0 else None
                        break
                break
        if r is None:
            r = next(('<' + n + '>' for lo, hi, n in libs if lo <= pc < hi), '<?>')
        cache[pc] = r
        return r

    total = sum(n for n, _ in samples)
    flat = collections.Counter()
    cum = collections.Counter()
    callers = collections.defaultdict(collections.Counter)
    creg = re.compile(a.callers) if a.callers else None
    wreg = re.compile(a.within) if a.within else None
    within = collections.Counter()
    within_total = 0
    for n, pcs in samples:
        frames = [sym(pcs[0])] + [sym(pc - 1) for pc in pcs[1:]]
        flat[frames[0]] += n
        for f in set(frames):
            cum[f] += n
        if wreg:
            idx = next((i for i, f in enumerate(frames) if wreg.search(f)), None)
            if idx is not None:
                within_total += n
                for f in set(frames[:idx]):
                    within[f] += n
        if creg:
            for i, f in enumerate(frames):
                if f.startswith('<') and i > 0:
                    continue  # external libs: attribute leaf samples only
                if creg.search(f):
                    nxt = next((g for g in frames[i + 1:] if not g.startswith('<')), '<root>') if f.startswith('<') else (frames[i + 1] if i + 1 < len(frames) else '<root>')
                    callers[short(f, 80)][short(nxt, a.width)] += n
                    break
    sec = period_us / 1e6
    print(f'samples={total}  period={period_us}us  ~{total * sec:.1f} CPU-s sampled')
    src = cum if a.cum else flat
    mreg = re.compile(a.match) if a.match else None
    k = 0
    for f, n in src.most_common():
        if mreg and not mreg.search(f):
            continue
        print(f'{100 * flat[f] / total:6.2f}% flat {100 * cum[f] / total:6.2f}% cum  {short(f, a.width)}')
        k += 1
        if k >= a.top:
            break
    if wreg:
        print(f'\n== inside {a.within}: {100 * within_total / total:.2f}% of all samples; inclusive share of callees:')
        for f, n in within.most_common(a.top):
            print(f'  {100 * n / within_total:6.2f}%  {short(f, a.width)}')
    for f, cnt in callers.items():
        print(f'\n== callers of {f}')
        for c, n in cnt.most_common(15):
            print(f'  {100 * n / total:6.2f}%  {c}')


if __name__ == '__main__':
    main()
