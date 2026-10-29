# WAC Clearinghouse conference archives: one reader, two archives

Written 2026-10-29. The WAC Clearinghouse has given permission to publish the IWAC programs; corrections go to jlewis2@olympic.edu.

- `wsgi.py` mounts a selector at `/` and one Flask app per archive: `/cccc` and `/iwac`. `APP_PREFIX` puts the whole site under a path.
- `cccc/` is a copy of the CCCC Program Reader with links made prefix-safe (`{{ P }}`), reading `data/cccc.db`.
- `iwac/` is the IWAC reader: census, conferences, year and session pages, person pages (2+ conferences, 2002 excluded), institutions, world atlas, areas (2020 and 2025 only), panel network, formats and roles, terms over time, corpus builder with CSV/JSON export, search.
- `build_iwac.py` builds `data/iwac.db` from `../iwac-corpus/build/iwac.db`. Abstracts are left out.
- Not built for IWAC: groups, call and program, area by institution type.

Run: `python -m waitress --listen=127.0.0.1:8080 wsgi:application`, then open http://127.0.0.1:8080/. Test: `python test_smoke.py`.

Deployment: Fly files are in this folder, and `DEPLOY.md` covers Fly and the Clearinghouse's IIS move.

Known weak years, stated on the site: 2002 is an OCR'd scan, 2008 has authors without institutions, 2016 prints names and institutions without a separator so some splits are inferred. People and affiliation matches are used as built, without a manual review pass.

Licenses: the code is MIT. `data/cccc.db` is the release of the CCCC Convention Program Corpus (CC BY 4.0, https://doi.org/10.5281/zenodo.23751615). `data/iwac.db` is parsed from programs hosted by the WAC Clearinghouse and is included with the Clearinghouse's permission; no separate data license has been set for it yet, so ask before redistributing it.

Live site: https://wacc-conference-reader.fly.dev/
