"""Build the CPTSC reader database (data/cptsc.db) from the corpus database (cptsc-corpus/build/cptsc.db).

Usage: python build_cptsc.py
Adds what the pages need: role groups, person summaries with the ethics threshold, per-year census figures,
institutions, a title table for term trends, and full-text search.
Institutions: the CPTSC proceedings were not run through ROR. A printed affiliation takes the institution of an identical
printed affiliation in the CCCC, IWAC or Computers and Writing readers (data/cccc.db, data/iwac.db, data/cw.db); the rest stay unmatched.
Private fields never leave the corpus database: session descriptions (abstracts) are left out.
"""
import os, re, sqlite3, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "cptsc-corpus", "build", "cptsc.db")
OUT = os.path.join(HERE, "data", "cptsc.db")
MIN_CONVENTIONS = 2
OCR_YEARS = {1999}   # the noisiest OCR scan; the other scanned years were checked name by name against their tables of contents, so they count


def gini(values):
    v = sorted(values); n, s = len(v), sum(v)
    return round((2 * sum((i + 1) * x for i, x in enumerate(v)) - (n + 1) * s) / (n * s), 3) if n and s else None


def role_group(r):
    r = (r or "").lower()
    if r.startswith(("chair", "presid", "moderator")): return "chair"
    if r.startswith("respond"): return "respondent"
    if r.startswith(("coordinator", "organizer")) or "workshop" in r: return "workshop leader"
    if r.startswith(("facilit", "discussion", "leader", "host", "helper", "introduc", "plenary", "summary", "reader", "recorder")): return "facilitator"
    return "presenter"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def crosswalk():
    """Normalized printed affiliation -> (institution row), from the readers already built; the most common match wins."""
    votes, rows = {}, {}
    for db in ("cccc", "iwac", "cw"):
        path = os.path.join(HERE, "data", db + ".db")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(path)
        for a, i, n in c.execute("select affiliation_as_printed, institution_id, count(*) from appearances where institution_id is not null and affiliation_as_printed is not null group by 1, 2"):
            votes.setdefault(norm(a), Counter())[i] += n
        for r in c.execute("select id, name, ror_id, country, kind, lat, lon from institutions"):
            if r[0] not in rows or (rows[r[0]][5] is None and r[5] is not None):
                rows[r[0]] = r
    return {k: v.most_common(1)[0][0] for k, v in votes.items()}, rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    src = sqlite3.connect(SRC); src.row_factory = sqlite3.Row
    out = sqlite3.connect(OUT)
    out.executescript("""
    CREATE TABLE conventions (year INTEGER PRIMARY KEY, city TEXT, venue TEXT, theme TEXT, chair TEXT, status TEXT, dates TEXT, site TEXT);
    CREATE TABLE source_documents (id TEXT PRIMARY KEY, year INTEGER, kind TEXT, url TEXT, rights TEXT, public_url TEXT);
    CREATE TABLE sessions (id TEXT PRIMARY KEY, year INTEGER, source_document_id TEXT, code TEXT, title TEXT, session_type TEXT, area TEXT, room TEXT);
    CREATE TABLE appearances (id INTEGER PRIMARY KEY, year INTEGER, session_id TEXT, ord INTEGER, role TEXT, role_group TEXT, name_as_printed TEXT,
        affiliation_as_printed TEXT, paper_title TEXT, person_id TEXT, institution_id TEXT, source_document_id TEXT);
    CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT, method TEXT);
    CREATE TABLE person_summary (person_id TEXT PRIMARY KEY, display_name TEXT, first_year INTEGER, last_year INTEGER, conventions INTEGER, appearances INTEGER, eligible INTEGER);
    CREATE TABLE institutions (id TEXT PRIMARY KEY, name TEXT, ror_id TEXT, country TEXT, kind TEXT, lat REAL, lon REAL);
    CREATE TABLE inst_year (year INTEGER, institution_id TEXT, appearances INTEGER, people INTEGER);
    CREATE TABLE census (year INTEGER PRIMARY KEY, city TEXT, status TEXT, sessions INTEGER, appearances INTEGER, people INTEGER, newcomers INTEGER, returners INTEGER,
        with_affiliation INTEGER, matched INTEGER, non_us INTEGER, top10_share REAL, gini REAL, institutions INTEGER, chairs INTEGER);
    CREATE TABLE titles (id INTEGER PRIMARY KEY, year INTEGER, kind TEXT, session_id TEXT, text TEXT);
    """)
    for r in src.execute("select * from convention"):
        out.execute("insert into conventions values (?,?,?,?,?,?,?,?)", (r["year"], r["city"], r["venue"], r["theme"], r["chair"], r["status"], None, None))
    for r in src.execute("select * from source_document"):
        pub = r["url"] if (r["url"] or "").startswith("http") else None
        out.execute("insert into source_documents values (?,?,?,?,?,?)", (r["id"], r["year"], r["kind"], r["url"], r["rights"], pub))
    for r in src.execute("select * from session"):
        out.execute("insert into sessions values (?,?,?,?,?,?,?,?)", (r["id"], r["year"], r["source_document_id"], r["code"], r["title"], r["session_type"], r["tracks"], r["room"]))
    year_of = {r["id"]: r["year"] for r in src.execute("select id, year from session")}
    cw, inst_rows = crosswalk()
    used = set()
    for r in src.execute("select * from appearance order by session_id, ord"):
        iid = cw.get(norm(r["affiliation_as_printed"])) if r["affiliation_as_printed"] else None
        used.add(iid)
        out.execute("insert into appearances values (?,?,?,?,?,?,?,?,?,?,?,?)", (r["id"], year_of[r["session_id"]], r["session_id"], r["ord"], r["role"], role_group(r["role"]),
                    r["name_as_printed"], r["affiliation_as_printed"], r["paper_title"], r["person_id"], iid, r["source_document_id"]))
    for r in src.execute("select id, display_name, method from person"):
        out.execute("insert into people values (?,?,?)", tuple(r))
    out.execute("""insert into person_summary select p.id, p.display_name, min(a.year), max(a.year), count(distinct a.year), count(*), 0
                   from people p join appearances a on a.person_id = p.id group by p.id""")
    # eligibility counts conventions other than the OCR years
    for pid, n in out.execute(f"select person_id, count(distinct year) from appearances where year not in ({','.join(map(str, OCR_YEARS))}) group by person_id").fetchall():
        if n >= MIN_CONVENTIONS:
            out.execute("update person_summary set eligible = 1 where person_id = ?", (pid,))
    for iid in used:
        if iid in inst_rows:
            out.execute("insert into institutions values (?,?,?,?,?,?,?)", inst_rows[iid])
    out.execute("""insert into inst_year select year, institution_id, count(*), count(distinct person_id) from appearances where institution_id is not null group by year, institution_id""")
    # census
    seen = set()
    for c in out.execute("select year, city, status from conventions order by year").fetchall():
        y = c[0]
        rows = out.execute("select person_id, institution_id, affiliation_as_printed, role_group from appearances where year = ?", (y,)).fetchall()
        people = {r[0] for r in rows}
        newcomers = len(people - seen); returners = len(people & seen); seen |= people
        withaff = sum(1 for r in rows if r[2]); matched = sum(1 for r in rows if r[1])
        counts = Counter(r[1] for r in rows if r[1])
        top10 = sum(v for _, v in counts.most_common(10)) / matched if matched else None
        nonus = out.execute("select count(*) from appearances a join institutions i on i.id = a.institution_id where a.year = ? and i.country is not null and i.country != 'US'", (y,)).fetchone()[0]
        out.execute("insert into census values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (y, c[1], c[2],
            out.execute("select count(*) from sessions where year = ?", (y,)).fetchone()[0], len(rows), len(people), newcomers, returners, withaff, matched, nonus,
            top10, gini(list(counts.values())), len(counts), sum(1 for r in rows if r[3] == "chair")))
    out.execute("insert into titles(year, kind, session_id, text) select year, 'session', id, title from sessions where title is not null and title != ''")
    out.execute("insert into titles(year, kind, session_id, text) select year, 'paper', session_id, paper_title from appearances where paper_title is not null and paper_title != ''")
    for t in ("appearances(person_id)", "appearances(session_id)", "appearances(institution_id)", "appearances(year)", "sessions(year)", "titles(year)"):
        out.execute(f"create index ix_{t.replace('(', '_').replace(')', '')} on {t}")
    out.execute("create virtual table sessions_fts using fts5(title, content='sessions')")
    out.execute("insert into sessions_fts(rowid, title) select rowid, title from sessions")
    out.execute("create virtual table institutions_fts using fts5(name, content='institutions')")
    out.execute("insert into institutions_fts(rowid, name) select rowid, name from institutions")
    out.execute("create virtual table papers_fts using fts5(text, content='titles', content_rowid='id')")
    out.execute("insert into papers_fts(rowid, text) select id, text from titles where kind = 'paper'")
    out.execute("create virtual table people_fts using fts5(display_name, person_id UNINDEXED)")
    out.execute("insert into people_fts(display_name, person_id) select display_name, person_id from person_summary where eligible = 1")
    out.commit()
    q = lambda s: out.execute(s).fetchall()
    print("sessions", q("select count(*) from sessions")[0][0], "| appearances", q("select count(*) from appearances")[0][0], "| people", q("select count(*) from people")[0][0],
          "| eligible", q("select count(*) from person_summary where eligible=1")[0][0], "| institutions", q("select count(*) from institutions")[0][0],
          "| with coordinates", q("select count(*) from institutions where lat is not null")[0][0])
    print(q("select year, sessions, people, newcomers, matched, non_us from census"))


if __name__ == "__main__":
    main()
