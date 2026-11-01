# WAC Clearinghouse conference archives: five readers and a comparator

Version 2.0.0, 2026-11-01. The WAC Clearinghouse has given permission to publish the IWAC programs; corrections go to jlewis2@olympic.edu.

- `wsgi.py` mounts a landing page at `/` and one Flask app per series listed in `series.json`: `/cccc`, `/iwac`, `/cw`, `/cptsc` and `/ccw`, plus `/compare`. `APP_PREFIX` puts the whole site under a path.
- `cccc/` is the CCCC Program Reader (1998 to 2027), made prefix-safe (`{{ P }}`), reading `data/cccc.db`. It also has groups, calls, and area by institution type.
- `iwac/` reads the International WAC Conference programs (2002 to 2025). `cw/` reads Computers and Writing (1984 to 2024). `cptsc/` reads the CPTSC proceedings (1974 to 2025). `ccw/` reads the Conference on Community Writing (2015 to 2025). Each has a census, conferences, year and session pages, person pages (two or more conferences, heavily OCR'd years excluded), institutions, an atlas, a panel network, terms over time, formats, a corpus builder with CSV and JSON export, and search. Abstracts are left out of every database.
- `compare/` is Synkrisis: Chronikon (the years side by side), Oikoi (institutions), Topoi (one term across archives) and Prosopographia (people matched across archives, as counts only). It reads `data/synkrisis.db`, which holds aggregates and no names.
- `series.json` registers each archive. `check_series.py` checks a database against the shared contract, `build_synkrisis.py` builds the comparator's data, and a new conference needs a database that passes the check plus one registry entry.
- `build_iwac.py`, `build_cw.py`, `build_cptsc.py` and `build_ccw.py` build each archive's database from its private corpus folder. `shared/` holds the sidebar layout, icons and styles that `sync_shell.py` copies into every reader.

Run: `python -m waitress --listen=127.0.0.1:8080 wsgi:application`, then open http://127.0.0.1:8080/. Test: `python test_smoke.py`.

Deployment: Fly files are in this folder, and `DEPLOY.md` covers Fly and the Clearinghouse's IIS move.

Weak years are stated on each reader: scanned programs read by OCR, programs that print names without institutions, and years with no program in the corpus. People and affiliation matches are used as built, without a manual review pass.

Licenses: the code is MIT. `data/cccc.db` is the release of the CCCC Convention Program Corpus (CC BY 4.0, https://doi.org/10.5281/zenodo.23751615). The other databases are parsed from programs published by their organizers and are included with permission; no separate data license has been set for them, so ask before redistributing them.

Live site: https://wacc-conference-reader.fly.dev/

Cite: Lewis, Justin. WAC Clearinghouse Conference Archives Reader. Zenodo, https://doi.org/10.5281/zenodo.23780138 (all versions; v2.0.0 is 10.5281/zenodo.23871035).
