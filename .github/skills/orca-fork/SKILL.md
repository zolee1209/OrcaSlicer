---
name: orca-fork
description: "Use in the zolee1209/OrcaSlicer fork for any fork maintenance or development workflow: session start status, starting or finishing a fork feature, committing fork work, monthly upstream (mainline) sync / rebase, rebase conflict resolution, profile rules (Ratrig profiles protected, other vendors removed), updating fork/features.yaml, FORK(<id>) code tags. Hungarian-speaking user."
---

# OrcaSlicer fork – eljárások

Alapszabályok: `.github/instructions/orca-fork.instructions.md` (mindig érvényes).
Nyilvántartás és szabályok: `fork/features.yaml`. Scriptek: `fork/tools/` (mind Python 3 + PyYAML).

| Script | Mit csinál | Módosít? |
|---|---|---|
| `session-status.py` | ág, nem commitolt fájlok funkciónként, távoli ág, mainline-távolság, javasolt kérdések | nem |
| `sync-report.py [--fetch] [--out F]` | ütközés-előrejelzés (`git merge-tree`), upstream változások a fork fájljaiban, funkciónként | nem (`--fetch` csak a remote refeket) |
| `prune-profiles.py` | profilszabályok: `--resolve-conflicts`, `--prune`, `--restore-ratrig REF` | csak `--apply`-jal, commitot soha |
| `check-fork.py [--strict]` | features.yaml ↔ kód ↔ commitok összhangja, FORK címkék | nem |

Minden eljárásnál: egy fázis egy kérésben (elemzés / terv / végrehajtás), jóváhagyás az ask_user eszközzel.

## A. Session eleje

1. `python3 fork/tools/session-status.py`
2. 3–5 soros összefoglaló: ág, nem commitolt munka funkciónként, szinkron-állapot.
3. A „Javasolt kérdések” egyenként, ask_user-rel. Tipikus döntések:
   - nem commitolt munka → commit új ágra (`feature/<id>`), a jelenlegi ágra, vagy hagyjuk (→ C);
   - a küszöbnél régebbi szinkron → kéri-e a riportot (→ E/1, csak elemzés);
   - melyik funkción dolgozunk (features.yaml id, vagy új → B).

## B. Új funkció indítása

1. Kérdezd meg a célt; javasolj kebab-case `id`-t; ellenőrizd, hogy nincs-e már ilyen a features.yaml-ban.
2. Terv: érintett upstream fájlok (hook), saját fájlok, CLI/config kulcsok. Jóváhagyás.
3. Ág: `git switch -c feature/<id> <sync.fork_branch>`.
4. features.yaml bejegyzés: `status: fork-only`, `owned_files`, `hooks`, `cli`, `config`, `env`, `used_by`, `notes`.
5. Fejlesztés a kódolási szabályok szerint (saját fájl + FORK címkék).

## C. Commit

1. `git status` + `session-status.py` funkciónkénti bontása.
2. Védett fájl a változások között → külön, kifejezett megerősítés nélkül NEM kerül commitba.
3. Javasolt bontás: funkciónként külön commit, tárgy `[fork:<id>] …`; meglévő funkció javítása: `--fixup`.
4. Mutasd meg a fájllistát és az üzenete(ke)t → jóváhagyás → commit.
5. `python3 fork/tools/check-fork.py` – hiba esetén jelezd.
6. Push-felajánlás a szabályfájl 3a pontja szerint: követett ágnál `git push`, új ágnál
   `git push -u origin <ág>`; a felhasználó futtatja (VS Code Sync vagy terminál). Force push soha.

## D. Funkció lezárása

1. `check-fork.py`, build és (ha van) teszt.
2. Kérdezd meg: beolvasztás a fork fő ágba (`sync.fork_branch`) – fast-forward vagy `--no-ff` merge?
3. features.yaml `commits` és `notes` frissítése.

## E. Havi szinkron a mainline-nal

Minden lépés külön jóváhagyással. Becsült költség: a riport ingyenes; AI csak a „kézi” ütközésekhez kell.

1. **Riport (elemzés):**
   `python3 fork/tools/sync-report.py --fetch --out fork/upstream-sync/<YYYY-MM-DD>/report.md`
   Összefoglaló: kézi ütközések funkciónként, automatikusan kezelt területek, új release tagek.
   Döntés: induljon-e a szinkron, melyik célra (`upstream/main` vagy release tag).
2. **Előkészítés:**
   `git branch backup/pre-sync-<dátum> <fork_branch>` és `git tag pre-sync-<dátum> <fork_branch>`;
   külön worktree, hogy a fő mappa buildje érintetlen maradjon:
   `git worktree add -b custom/rebased-<YYYY-MM> ../OrcaSlicer-sync <fork_branch>`;
   ott: `git config rerere.enabled true`.
3. **Rebase:** `git rebase <cél>`. Minden megállásnál:
   - `python3 fork/tools/prune-profiles.py --resolve-conflicts --apply` (profilütközések AI nélkül);
   - a maradék ütközést a features.yaml `decision`/`notes` szerint oldd fel: ahol a döntés „marad / a miénk”,
     a fork viselkedése marad, és az upstream új kódjához igazítjuk (nem dobjuk el az upstream változást
     sem, ha nem ütközik a fork funkcióval);
   - üres commit (az upstream már tartalmazza) → `git rebase --skip`, a funkció `status: superseded`;
   - minden nem triviális feloldás egy sor a `fork/upstream-sync/<dátum>/rebase-notes.md`-ben;
   - ha a features.yaml nem ad egyértelmű szabályt → állj meg és kérdezz.
4. **Rebase után:**
   - `prune-profiles.py --prune --apply` (új upstream gyártók törlése);
   - `prune-profiles.py --restore-ratrig backup/pre-sync-<dátum> --apply`;
   - commit: `[fork:profiles-vendor-prune] Sync <dátum>: remove other vendors, restore Ratrig`;
   - `check-fork.py`; features.yaml: `commits` (új hash-ek), `sync.fork_branch` → új ág.
5. **Build (jóváhagyással, gépidő):** ha a `deps/` változott (lásd riport): `bash build_linux.sh -x -c -d -s`,
   különben `bash build_linux.sh -x -s -j 40` (részletek: `BUILD_OPTIMIZED.md`).
6. **Ellenőrzés:** a fork CLI-funkcióinak próbája (a www alkalmazás hívásai: features.yaml `used_by`).
7. A felhasználó pusholja az új ágat; a régi ág és a backup marad.

## F. Profilszabályok röviden

- `keep` (Ratrig): mindig a fork verziója; tartalom-módosítás csak kifejezett utasításra.
- `keep_upstream` (OrcaFilamentLibrary, Custom): az upstream verziója, automatikusan frissül.
- Minden más gyártó: törlendő; a szinkron-riport figyelmen kívül hagyja.

## G. Korábbi szinkronok

`fork/upstream-sync/<dátum>/` – riportok, rebase-jegyzőkönyvek, mainline-leírások.
A 2026-10-13-i próba-rebase állapota és nyitott pontjai: `fork/upstream-sync/2026-10-13/rebase-trial-notes.md`.
