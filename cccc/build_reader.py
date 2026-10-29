"""Build the reader's database from a release package.

Usage: python -I reader/build_reader.py <release_dir> <out.db> [capture_dir] [data/suppressed_people.csv]
Copies the release SQLite and adds what the pages need: full-text search, a title table for
term trends, per-person summaries (with the ethics threshold), per-year census figures, and
institution-by-year counts. capture_dir (optional, private) is read only to find the public
NCTE address of each program file, so pages can link to NCTE's own copy at the printed page.
"""
import csv, glob, json, math, os, re, shutil, sqlite3, sys
from collections import Counter, defaultdict

MIN_CONVENTIONS_FOR_PAGE = 2  # a person page needs a career; one-time listings stay on session pages only

def public_urls(capture_dir):
    """filename used in the corpus -> address on NCTE's site (or the Wayback Machine)."""
    out = {}
    for path in glob.glob(os.path.join(capture_dir, "*manifest.csv")):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            url = r.get("url") or ""
            if not url.lower().endswith(".pdf") or str(r.get("http_status")) != "200":
                continue
            if "/convention/" in url:
                name = url.split("/convention/")[-1]
            elif "/uploads/" in url:
                name = url.split("/uploads/")[-1]
            else:
                name = url.split("/cccc/")[-1]
            out[name.replace("/", "__")] = re.sub(r"/web/(\d+)id_/", r"/web/\1/", url)
    return out

def gini(values):
    v = sorted(values)
    n, s = len(v), sum(v)
    if not n or not s:
        return None
    return round((2 * sum((i + 1) * x for i, x in enumerate(v)) - (n + 1) * s) / (n * s), 3)

def main(release_dir, out, capture_dir=None, suppressed_csv=None):
    if os.path.exists(out):
        os.remove(out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    shutil.copy(os.path.join(release_dir, "cccc-program-corpus.sqlite"), out)
    con = sqlite3.connect(out)
    con.row_factory = sqlite3.Row

    # links to NCTE's own files
    con.execute("ALTER TABLE source_documents ADD COLUMN public_url TEXT")
    urls = public_urls(capture_dir) if capture_dir and os.path.isdir(capture_dir) else {}
    for r in con.execute("SELECT id, url FROM source_documents").fetchall():
        u = urls.get(r["url"]) or (re.sub(r"/web/(\d+)id_/", r"/web/\1/", r["url"]) if (r["url"] or "").startswith("http") else None)
        con.execute("UPDATE source_documents SET public_url=? WHERE id=?", (u, r["id"]))

    # titles for term trends
    con.execute("CREATE TABLE titles (id INTEGER PRIMARY KEY, year INTEGER, kind TEXT, session_id TEXT, text TEXT)")
    con.execute("INSERT INTO titles(year, kind, session_id, text) SELECT year, 'session', id, title FROM sessions WHERE title IS NOT NULL AND title != ''")
    con.execute("INSERT INTO titles(year, kind, session_id, text) SELECT year, 'paper', session_id, paper_title FROM appearances WHERE paper_title IS NOT NULL AND paper_title != ''")
    con.execute("CREATE INDEX ix_titles_year ON titles(year)")

    # people: summaries and the ethics threshold
    suppressed = set()
    if suppressed_csv and os.path.exists(suppressed_csv):
        suppressed = {r["person_id"] for r in csv.DictReader(open(suppressed_csv, encoding="utf-8-sig"))}
    con.execute("""CREATE TABLE person_summary (person_id TEXT PRIMARY KEY, display_name TEXT, method TEXT, first_year INTEGER,
                   last_year INTEGER, conventions INTEGER, appearances INTEGER, eligible INTEGER)""")
    con.execute("""INSERT INTO person_summary
        SELECT p.id, p.display_name, p.method, min(a.year), max(a.year), count(DISTINCT a.year), count(*), 0
        FROM people p JOIN appearances a ON a.person_id = p.id GROUP BY p.id""")
    con.execute("UPDATE person_summary SET eligible = 1 WHERE conventions >= ?", (MIN_CONVENTIONS_FOR_PAGE,))
    for pid in suppressed:
        con.execute("UPDATE person_summary SET eligible = 0 WHERE person_id = ?", (pid,))
    con.execute("CREATE INDEX ix_app_person ON appearances(person_id)")
    con.execute("CREATE INDEX ix_app_session ON appearances(session_id)")
    con.execute("CREATE INDEX ix_app_inst ON appearances(institution_id)")
    con.execute("CREATE INDEX ix_app_year ON appearances(year)")
    con.execute("CREATE INDEX ix_sess_year ON sessions(year)")

    # full-text search
    con.execute("CREATE VIRTUAL TABLE sessions_fts USING fts5(title, content='sessions')")
    con.execute("INSERT INTO sessions_fts(rowid, title) SELECT rowid, title FROM sessions")
    con.execute("CREATE VIRTUAL TABLE institutions_fts USING fts5(name, content='institutions')")
    con.execute("INSERT INTO institutions_fts(rowid, name) SELECT rowid, name FROM institutions")
    con.execute("CREATE VIRTUAL TABLE people_fts USING fts5(display_name, person_id UNINDEXED)")
    con.execute("INSERT INTO people_fts(display_name, person_id) SELECT display_name, person_id FROM person_summary WHERE eligible = 1")
    con.execute("CREATE VIRTUAL TABLE papers_fts USING fts5(paper_title, content='titles', content_rowid='id')")
    con.execute("INSERT INTO papers_fts(rowid, paper_title) SELECT id, text FROM titles WHERE kind = 'paper'")

    # institution-by-year
    con.execute("""CREATE TABLE inst_year AS
        SELECT a.year, a.institution_id, count(*) AS appearances, count(DISTINCT a.person_id) AS people
        FROM appearances a WHERE a.institution_id IS NOT NULL GROUP BY a.year, a.institution_id""")
    con.execute("CREATE INDEX ix_iy ON inst_year(institution_id, year)")

    # census, one row per year
    con.execute("""CREATE TABLE census (year INTEGER PRIMARY KEY, city TEXT, status TEXT, sessions INTEGER, appearances INTEGER,
        people INTEGER, newcomers INTEGER, returners INTEGER, with_affiliation INTEGER, matched INTEGER, us_ipeds INTEGER,
        two_year INTEGER, public_n INTEGER, private_n INTEGER, forprofit_n INTEGER, hbcu_n INTEGER, tribal_n INTEGER,
        non_us INTEGER, top10_share REAL, top50_share REAL, gini REAL, institutions INTEGER,
        chairs INTEGER, respondents INTEGER, facilitators INTEGER, formats TEXT)""")
    first = dict(con.execute("SELECT person_id, min(year) FROM appearances WHERE person_id IS NOT NULL GROUP BY person_id").fetchall())
    conv = {r["year"]: r for r in con.execute("SELECT year, city, status FROM conventions")}
    for (y,) in con.execute("SELECT DISTINCT year FROM sessions ORDER BY year").fetchall():
        rows = con.execute(
            """SELECT a.person_id, a.affiliation_as_printed, a.institution_id, i.country, i.ipeds_unitid, i.two_year, i.control, i.hbcu, i.tribal
               FROM appearances a LEFT JOIN institutions i ON i.id = a.institution_id WHERE a.year = ?""", (y,)).fetchall()
        people = {r["person_id"] for r in rows}
        new = sum(1 for p in people if first.get(p) == y)
        has_aff = {r["person_id"] for r in rows if r["affiliation_as_printed"]}
        matched = {r["person_id"] for r in rows if r["institution_id"]}
        # a person counts in a category if any of that year's listings fall in it (the same rule as stats.py)
        ipeds_rows = [r for r in rows if r["ipeds_unitid"] or r["two_year"] is not None]
        ipeds = {r["person_id"] for r in ipeds_rows}
        two = {r["person_id"] for r in ipeds_rows if r["two_year"]}
        def cat(pred):
            return len({r["person_id"] for r in ipeds_rows if pred(r)})
        non_us = {r["person_id"] for r in rows if r["institution_id"] and r["country"] and r["country"] != "US"}
        by_inst = Counter(r["institution_id"] for r in rows if r["institution_id"])
        counts = sorted(by_inst.values(), reverse=True)
        tot = sum(counts)
        ro = Counter(r[0] for r in con.execute("SELECT role_group FROM appearances WHERE year = ?", (y,)))
        fm = Counter(r[0] for r in con.execute("SELECT session_type FROM sessions WHERE year = ? AND session_type IS NOT NULL AND parent_id IS NULL", (y,)))
        c = conv.get(y)
        con.execute("INSERT INTO census VALUES (" + ",".join("?" * 26) + ")", (
            y, c["city"] if c else None, c["status"] if c else None,
            con.execute("""SELECT count(*) FROM sessions WHERE year = ? AND parent_id IS NULL
                           AND coalesce(session_type, '') NOT IN ('Registration/Exhibit Hall Hours', 'Open Rooms', 'Committee Meeting', 'Event')""", (y,)).fetchone()[0], sum(ro.values()),
            len(people), new, len(people) - new, len(has_aff), len(matched), len(ipeds), len(two),
            cat(lambda r: r["control"] == 1), cat(lambda r: r["control"] == 2), cat(lambda r: r["control"] == 3),
            cat(lambda r: r["hbcu"]), cat(lambda r: r["tribal"]), len(non_us),
            round(sum(counts[:10]) / tot, 4) if tot else None, round(sum(counts[:50]) / tot, 4) if tot else None,
            gini(counts), len(counts), ro["chair"], ro["respondent"], ro["facilitator"], json.dumps(fm)))
    con.commit()
    if capture_dir and os.path.isdir(capture_dir):  # derived call-versus-program measures; no call text is stored
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
        import calls_analysis
        calls_analysis.build(out, capture_dir)
    con.execute("VACUUM")
    n = con.execute("SELECT count(*) FROM person_summary WHERE eligible = 1").fetchone()[0]
    print(f"reader db -> {out} ({os.path.getsize(out) / 1e6:.1f} MB); {n} people with pages; {len(urls)} NCTE file addresses")

if __name__ == "__main__":
    main(*sys.argv[1:5])
