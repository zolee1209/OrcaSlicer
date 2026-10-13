---
applyTo: "**"
description: "zolee1209/OrcaSlicer fork – kötelező munkaszabályok minden sessionben (fork-azonosítás, fázis-fegyelem, védett profilok, commit- és szinkron-szabályok)."
---

# OrcaSlicer fork – munkaszabályok

Ez a repó a **zolee1209/OrcaSlicer fork**, nem a mainline. A fork-specifikus kérdésekben ezek a szabályok
felülírják az upstream `AGENTS.md`, `CLAUDE.md`, `.claude/` és `.agents/` tartalmát.
Részletes eljárások: **orca-fork** skill (`.github/skills/orca-fork/SKILL.md`).
Nyilvántartás: `fork/features.yaml` (funkciók, szabályok, döntések), áttekintés: `fork/README.md`.

## 1. Session eleje

Az első érdemi lépés előtt futtasd: `python3 fork/tools/session-status.py`
(csak olvas, kb. 0,3 mp). Foglald össze 3–5 sorban, majd a „Javasolt kérdések” pontjait egyenként tedd fel
az ask_user eszközzel. Ha a felhasználó kérése egyértelműen a forkon kívüli témáról szól, ez kihagyható.

## 2. Fázis-fegyelem (a legfontosabb szabály)

Minden kérést sorolj be: **elemzés** | **terv** | **végrehajtás**. Csak a kért fázist végezd el.
- Kétértelmű kérésnél kérdezz, mielőtt nekikezdesz.
- Az „utána”, „azok után”, „majd” szavak NEM jelentenek engedélyt a következő fázisra.
- Jóváhagyott terv nélkül tilos: rebase, merge, szinkron, tömeges módosítás, fájltörlés, deps build,
  nagy munkát végző subagent indítása.
- Ha a felhasználó elutasít egy szerkesztést, állj meg és kérdezz – ne próbálkozz kerülőúton.
- Minden nem-triviális lépés előtt mondd el röviden, mit és miért csinálsz.

## 3. Kemény tiltások

- **Védett fájlok** (`sync.protected` a features.yaml-ban – jelenleg `resources/profiles/Ratrig/**` és
  `resources/profiles/Ratrig.json`): nem törölhetők, és csak a felhasználó **adott üzenetben adott, kifejezett**
  utasítására módosíthatók. Az upstream `orca-profiles` skill ezekre nem vonatkozik.
- Nem adunk be semmit upstreamre (nincs PR az OrcaSlicer/OrcaSlicer repóba).
- Nincs push: az agentnek nincs GitHub-hozzáférése; a felhasználó pusholja (lásd 3a).

## 3a. Push-felajánlás (automatikus üzenet commit után)

Minden commit után, és ha a `session-status.py` pusholatlan commitot jelez, ezt az üzenetet add, a
`<ág>` helyére a `git branch --show-current` kimenetét írva:

> A commit csak helyben van. Feltöltés a saját forkra (`origin` = github.com/zolee1209/OrcaSlicer):
> - VS Code: Source Control → **Sync Changes** / **Push** – vagy a VS Code terminálban:
> - ha az ág már létezik az originen (van követett távoli ág): `git push`
> - ha új az ág (pl. `feature/<id>`, `custom/rebased-<YYYY-MM>`): `git push -u origin <ág>`
> - backup tag feltöltése (opcionális): `git push origin <tag>`
>
> A push a jelenlegi ág összes pusholatlan commitját feltölti, az új commitot is. Ellenőrzés utána:
> `git status -sb` → nincs `[ahead N]`.

Soha ne javasolj `--force` pusht; ha a távoli ág eltért (`behind`), előbb kérdezz.
- Nem módosítható: upstream `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`.
- Pusholt ág története nem írható át; rebase mindig új ágon, előtte backup ág + tag.
- Más gyártók profiljai nem kerülhetnek vissza a forkba (keep: Ratrig; keep_upstream: OrcaFilamentLibrary, Custom).

## 4. Kódolási szabályok fork-funkcióknál

- Új fork-kód lehetőleg saját fájlba; az upstream fájlokban csak vékony hívási pont maradjon.
- Upstream fájlban minden fork-módosítás címkézett:
  `// FORK(<id>): <miért>` egy sorra, vagy `// FORK(<id>) BEGIN` … `// FORK(<id>) END` blokkra
  (shell/CMake/Python: `# FORK(<id>)`). Az `<id>` a features.yaml-ból való.
- Új vagy módosított funkciónál frissítsd a features.yaml bejegyzést (fájlok, cli, config, env, used_by, notes).
- Commit-tárgy: `[fork:<id>] <leírás>` (meta-munka: `[fork:fork-meta]`); javítás egy meglévő funkcióhoz:
  `git commit --fixup=<commit>`.
- Commit csak a felhasználó jóváhagyásával; előtte mutasd meg a fájllistát és az üzenetet.
- Változtatás után: `python3 fork/tools/check-fork.py`.

## 5. Költséghatékonyság

- Először a determinisztikus scriptek (`fork/tools/`), csak utána AI-elemzés.
- Nagy fájlokból csak a szükséges sorokat olvasd; ne olvass végig PR-listákat kérés nélkül.
- Upstream változásokat csak a `sync-report.py` által jelzett, a fork funkcióit érintő helyeken vizsgálj.

## 6. Kommunikáció

Magyarul, tömören. Kérdést mindig az ask_user eszközzel, egyszerre egyet.
