"""Community Writing Program Reader: a read-only Flask app over data/ccw.db (see ../build_ccw.py).

Mounted under /ccw by ../wsgi.py (links use request.script_root). Every page is noindex.
Person pages exist only for people listed at two or more conferences .
"""
import csv, io, json, os, re, sqlite3
from datetime import date
from flask import Flask, Response, abort, g, render_template, request

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("CCW_DB", os.path.join(HERE, "..", "data", "ccw.db"))
SITE_URL = os.environ.get("READER_URL", "http://localhost:8080/ccw")
REPO_URL = os.environ.get("REPO_URL", "")
DATA_URL = os.environ.get("DATA_URL", "")
MAX_EXPORT = 100_000
YEARS = list(range(2015, 2026))   # the conference meets in odd years; the even years are drawn as gaps

BREAKS = [
    {"from": y, "to": y, "label": "2016, 2018, 2020, 2022 and 2024: the conference meets in odd years, so there is no edition", "kind": "gap"}
    for y in (2016, 2018, 2020, 2022, 2024)
] + [
    {"from": 2025, "to": 2025, "label": "2025: only the DeepThink Tanks and one keynote speaker are public; the rest of the schedule is behind a registration portal", "kind": "source"},
]

YEAR_NOTES = {
    2015: "The inaugural conference. Read from the program PDF, which prints an institution beside every presenter on the detail pages. The digital posters are one session each, and the chair's address and the two keynotes were added by hand from the overview pages. A few names are spelled differently in the presenter index than on the panel pages.",
    2017: "Read from the program PDF. All 80 panels (A to H) are here. Workshops that the PDF describes only on its abstract pages are listed from there with their facilitators. The Makerthon (15 sessions) prints names with no institutions, and the descriptive paragraphs under a few sessions are not kept. The keynotes and Elaine Richardson's performance were added by hand.",
    2019: "Read from the schedule page on the Coalition's site. Chairs are printed without an institution; where the chair also presents, the institution comes from that listing. Session H6 is printed as \u201cNo session assigned\u201d and is left out. The three keynotes were added by hand and print no institutions.",
    2021: "Read from the program Google Doc for the online conference; times are Eastern. Panel A4 prints a code and nothing else, and panel B1 is missing from the Doc, so neither is here. The pre-recorded panels and talks have no time.",
    2023: "Read from the program Google Doc. Sessions A9, A10, H10, W2 and W7 do not appear in the Doc, and Session E is printed as a single graduate research session. The creative displays and virtual presentations have no time. The Doc prints the leaders of the pre-conference visit to History Colorado (PC1) in its description, so they were added by hand, and the chair of D9 was read from a free-text sentence.",
    2025: "Only the four DeepThink Tanks and the keynote speaker Donnie Johnson Sackey are public. The rest of the schedule is in a registration portal and is not in the corpus, so the counts for this year are far lower than the conference itself. The tanks print no times.",
}

app = Flask(__name__, root_path=HERE)
app.config["JSON_AS_ASCII"] = False


def db():
    if "db" not in g:
        g.db = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def q(sql, *args):
    return db().execute(sql, args).fetchall()


def q1(sql, *args):
    return db().execute(sql, args).fetchone()


_TITLES = None


def titles():
    global _TITLES
    if _TITLES is None:
        con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
        _TITLES = [(y, k, s, t, t.lower()) for y, k, s, t in con.execute("SELECT year, kind, session_id, text FROM titles")]
        con.close()
    return _TITLES


def build_date():
    return date.fromtimestamp(os.path.getmtime(DB)).isoformat() if os.path.exists(DB) else ""


def natural(code):
    m = re.match(r"([A-Za-z]*)[.\-]?(\d*)\.?(\d*)", code or "")
    return (m.group(1), int(m.group(2) or 0), int(m.group(3) or 0)) if m else ("", 0, 0)


def term_regex(term):
    t = term.strip().lower()
    if not t:
        return None
    star = t.endswith("*")
    t = t.rstrip("*").strip()
    if not t:
        return None
    body = r"\s+".join(re.escape(w) for w in t.split())
    return re.compile(r"(?<!\w)" + body + (r"\w*" if star else r"(?!\w)"))


@app.template_filter("pct")
def pct(v, digits=1):
    return "" if v is None else f"{100 * v:.{digits}f}%"


@app.template_filter("num")
def num(v):
    return "" if v is None else f"{v:,}"


@app.after_request
def headers(r):
    r.headers["X-Robots-Tag"] = "noindex, nofollow"
    return r


@app.context_processor
def inject():
    return {"build_date": build_date(), "repo_url": REPO_URL, "data_url": DATA_URL, "P": request.script_root, "ROOT": (request.script_root.rsplit("/", 1)[0] or "") + "/", "corpus": "ccw", "capsa_years": [{"year": c["year"], "n": c["sessions"] or 0} for c in q("SELECT year, sessions FROM census ORDER BY year")]}


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


METRICS = [
    ("people", "People listed", "count"),
    ("sessions", "Sessions", "count"),
    ("newcomer_share", "Share listed for the first time in this corpus", "share"),
    ("non_us_share", "Share at institutions outside the US", "share"),
    ("top10_share", "Share of listings from the ten most-listed institutions", "share"),
    ("gini", "Concentration (Gini) of listings across institutions", "index"),
    ("unmatched_share", "Share with an affiliation we could not match", "share"),
]


def census_rows():
    out = []
    for r in q("SELECT * FROM census ORDER BY year"):
        d = dict(r)
        ppl = d["people"] or 0
        d["non_us_share"] = d["non_us"] / d["matched"] if d["matched"] else None
        d["unmatched_share"] = 1 - d["matched"] / d["with_affiliation"] if d["with_affiliation"] else None
        d["newcomer_share"] = d["newcomers"] / ppl if ppl and d["year"] > 2015 else None
        c = q1("SELECT theme, chair FROM conventions WHERE year = ?", d["year"])
        d["theme"], d["chair"] = (c["theme"], c["chair"]) if c else (None, None)
        out.append(d)
    return out


@app.route("/")
def home():
    rows = census_rows()
    return render_template("home.html", rows=rows, metrics=METRICS, breaks=BREAKS, years=YEARS,
                           data=json.dumps({"rows": rows, "metrics": METRICS, "breaks": BREAKS, "years": YEARS}))


@app.route("/conventions")
def conventions():
    rows = [dict(r) for r in q("SELECT c.*, n.sessions, n.people FROM conventions c JOIN census n ON n.year = c.year ORDER BY c.year DESC")]
    return render_template("conventions.html", rows=rows, notes=YEAR_NOTES)


@app.route("/year/<int:y>")
def year(y):
    c = q1("SELECT * FROM census WHERE year = ?", y)
    if not c:
        abort(404)
    conv = q1("SELECT * FROM conventions WHERE year = ?", y)
    cen = [r for r in census_rows() if r["year"] == y][0]
    sessions = q("""SELECT s.id, s.code, s.title, s.session_type, s.area,
                    (SELECT count(*) FROM appearances a WHERE a.session_id = s.id) AS n FROM sessions s WHERE s.year = ?""", y)
    sessions = sorted(sessions, key=lambda r: (natural(r["code"]), r["id"]))
    top = q("""SELECT i.id, i.name, i.country, iy.appearances, iy.people FROM inst_year iy JOIN institutions i ON i.id = iy.institution_id
               WHERE iy.year = ? ORDER BY iy.appearances DESC, i.name LIMIT 25""", y)
    docs = q("SELECT DISTINCT d.id, d.url, d.public_url, d.kind FROM source_documents d JOIN sessions s ON s.source_document_id = d.id WHERE s.year = ?", y)
    roles = q("SELECT role_group, count(*) n FROM appearances WHERE year = ? GROUP BY 1 ORDER BY n DESC", y)
    area_rows = q("SELECT area, count(*) n FROM sessions WHERE year = ? AND area IS NOT NULL GROUP BY 1 ORDER BY n DESC", y)
    countries = q("""SELECT i.country, count(*) n FROM appearances a JOIN institutions i ON i.id = a.institution_id WHERE a.year = ? AND i.country IS NOT NULL
                     GROUP BY 1 ORDER BY n DESC LIMIT 8""", y)
    prev = q1("SELECT max(year) y FROM census WHERE year < ?", y)["y"]
    nxt = q1("SELECT min(year) y FROM census WHERE year > ?", y)["y"]
    return render_template("year.html", y=y, c=cen, conv=conv, sessions=sessions, top=top, docs=docs, roles=roles, area_rows=area_rows,
                           countries=countries, note=YEAR_NOTES.get(y), prev=prev, next=nxt)


@app.route("/session/<path:sid>")
def session(sid):
    s = q1("SELECT * FROM sessions WHERE id = ?", sid)
    if not s:
        abort(404)
    people = q("""SELECT a.*, i.name AS inst_name, i.country, ps.eligible FROM appearances a
                  LEFT JOIN institutions i ON i.id = a.institution_id LEFT JOIN person_summary ps ON ps.person_id = a.person_id
                  WHERE a.session_id = ? ORDER BY a.ord""", sid)
    doc = q1("SELECT * FROM source_documents WHERE id = ?", s["source_document_id"])
    conv = q1("SELECT * FROM conventions WHERE year = ?", s["year"])
    return render_template("session.html", s=s, people=people, doc=doc, conv=conv, note=YEAR_NOTES.get(s["year"]),
                           today=date.today().strftime("%B %d, %Y"))


ROLE_COLORS = {"presenter": "#8a4b2a", "chair": "#1c1a17", "respondent": "#4f6f8f", "facilitator": "#6b8f4f", "workshop leader": "#6b8f4f", "other": "#999"}


@app.route("/person/<path:pid>")
def person(pid):
    p = q1("SELECT * FROM person_summary WHERE person_id = ?", pid)
    if not p or not p["eligible"]:
        return render_template("hidden_person.html"), 404
    rows = q("""SELECT a.*, s.code, s.title AS stitle, s.session_type, i.name AS inst_name, i.country FROM appearances a
                JOIN sessions s ON s.id = a.session_id LEFT JOIN institutions i ON i.id = a.institution_id
                WHERE a.person_id = ? ORDER BY a.year, s.code""", pid)
    variants = q("SELECT name_as_printed, count(*) n FROM appearances WHERE person_id = ? GROUP BY 1 ORDER BY n DESC", pid)
    insts = []
    for r in rows:
        if r["inst_name"] and (not insts or insts[-1][0] != r["inst_name"]):
            insts.append((r["inst_name"], r["year"]))
    return render_template("person.html", p=p, rows=rows, variants=variants, insts=insts, years=sorted({r["year"] for r in rows}),
                           strip=career_strip(rows), colors=ROLE_COLORS)


def career_strip(rows):
    y0, y1, w = YEARS[0], YEARS[-1], 640
    step = (w - 40) / (y1 - y0)
    by = {}
    for r in rows:
        by.setdefault(r["year"], []).append(r["role_group"] or "other")
    marks = []
    order = ["chair", "respondent", "facilitator", "workshop leader", "presenter", "other"]
    for y, roles in sorted(by.items()):
        x = 20 + (y - y0) * step
        for k, role in enumerate(sorted(set(roles), key=lambda z: order.index(z) if z in order else 9)):
            marks.append({"x": round(x, 1), "y": 28 + 14 * k, "role": role, "n": roles.count(role), "year": y})
    ticks = [{"x": round(20 + (y - y0) * step, 1), "y": y} for y in range(y0, y1 + 1, 2)]
    return {"w": w, "marks": marks, "ticks": ticks}


@app.route("/institutions")
def institutions():
    qs = request.args.get("q", "").strip()
    non_us = request.args.get("non_us") == "1"
    where, args = ["1=1"], []
    if qs:
        where.append("i.name LIKE ?"); args.append(f"%{qs}%")
    if non_us:
        where.append("i.country IS NOT NULL AND i.country != 'US'")
    rows = q(f"""SELECT i.id, i.name, i.country, sum(iy.appearances) AS n, count(DISTINCT iy.year) AS years, min(iy.year) y0, max(iy.year) y1
                 FROM institutions i JOIN inst_year iy ON iy.institution_id = i.id WHERE {' AND '.join(where)} GROUP BY i.id ORDER BY n DESC LIMIT 200""", *args)
    return render_template("institutions.html", rows=rows, qs=qs, non_us=non_us)


@app.route("/institution/<path:iid>")
def institution(iid):
    i = q1("SELECT * FROM institutions WHERE id = ?", iid)
    if not i:
        abort(404)
    by_year = q("SELECT year, appearances, people FROM inst_year WHERE institution_id = ? ORDER BY year", iid)
    people = q("""SELECT ps.person_id, ps.display_name, ps.first_year, ps.last_year, count(*) AS n FROM appearances a
                  JOIN person_summary ps ON ps.person_id = a.person_id WHERE a.institution_id = ? AND ps.eligible = 1
                  GROUP BY ps.person_id ORDER BY n DESC, ps.display_name LIMIT 150""", iid)
    total = q1("SELECT count(DISTINCT person_id) n FROM appearances WHERE institution_id = ?", iid)["n"]
    sess = q("""SELECT DISTINCT s.id, s.year, s.code, s.title FROM appearances a JOIN sessions s ON s.id = a.session_id
                WHERE a.institution_id = ? ORDER BY s.year DESC, s.code LIMIT 60""", iid)
    printed = q("SELECT affiliation_as_printed, count(*) n FROM appearances WHERE institution_id = ? GROUP BY 1 ORDER BY n DESC LIMIT 12", iid)
    return render_template("institution.html", i=i, by_year=by_year, people=people, total=total, sess=sess, printed=printed)


def fts_query(text):
    toks = re.findall(r"\w+", text)
    return " ".join(f'"{t}"*' for t in toks[:8])


@app.route("/search")
def search():
    text = request.args.get("q", "").strip()
    res = {}
    if text and fts_query(text):
        m = fts_query(text)
        res["sessions"] = q("SELECT s.id, s.year, s.code, s.title FROM sessions_fts f JOIN sessions s ON s.rowid = f.rowid WHERE sessions_fts MATCH ? ORDER BY rank LIMIT 40", m)
        res["papers"] = q("SELECT t.year, t.session_id, t.text FROM papers_fts f JOIN titles t ON t.id = f.rowid WHERE papers_fts MATCH ? ORDER BY rank LIMIT 40", m)
        res["institutions"] = q("SELECT i.id, i.name, i.country FROM institutions_fts f JOIN institutions i ON i.rowid = f.rowid WHERE institutions_fts MATCH ? ORDER BY rank LIMIT 25", m)
        res["people"] = q("""SELECT ps.person_id, ps.display_name, ps.first_year, ps.last_year, ps.conventions FROM people_fts f
                             JOIN person_summary ps ON ps.person_id = f.person_id WHERE people_fts MATCH ? AND ps.eligible = 1 ORDER BY rank LIMIT 25""", fts_query(text))
    return render_template("search.html", text=text, res=res)


@app.route("/atlas")
def atlas():
    years = [r["year"] for r in q("SELECT DISTINCT year FROM inst_year ORDER BY year")]
    y = request.args.get("year", type=int)
    y = y if y in years else max(r["year"] for r in q("SELECT year FROM census WHERE matched > 0"))
    pts = [dict(r) for r in q("""SELECT i.id, i.name, i.country, i.lat, i.lon, iy.appearances n, iy.people p FROM inst_year iy
                                 JOIN institutions i ON i.id = iy.institution_id WHERE iy.year = ? AND i.lat IS NOT NULL""", y)]
    tot = q1("SELECT count(*) n FROM appearances WHERE year = ?", y)["n"]
    countries = q("""SELECT i.country, count(*) n, count(DISTINCT i.id) k FROM appearances a JOIN institutions i ON i.id = a.institution_id
                     WHERE a.year = ? AND i.country IS NOT NULL GROUP BY 1 ORDER BY n DESC""", y)
    shares = q("""SELECT c.year, c.city, c.status, n.matched, n.non_us FROM conventions c JOIN census n ON n.year = c.year ORDER BY c.year""")
    return render_template("atlas.html", years=years, y=y, pts=pts, total=tot, on_map=sum(p["n"] for p in pts), countries=countries, shares=shares,
                           data=json.dumps({"points": pts}))


def trend_series(terms, scope):
    sel = [t for t in titles() if scope == "all" or (scope == "sessions" and t[1] == "session") or (scope == "papers" and t[1] == "paper")]
    denom = {y: 0 for y in YEARS}
    for t in sel:
        denom[t[0]] = denom.get(t[0], 0) + 1
    series = []
    for term in terms:
        rx = term_regex(term)
        if not rx:
            continue
        counts = {y: 0 for y in YEARS}
        for t in sel:
            if rx.search(t[4]):
                counts[t[0]] = counts.get(t[0], 0) + 1
        series.append({"term": term, "counts": counts, "total": sum(counts.values())})
    return YEARS, denom, series


@app.route("/trends")
def trends():
    raw = request.args.get("terms", "")
    terms = [t.strip() for t in raw.split(",") if t.strip()][:6]
    scope = request.args.get("scope", "all")
    scope = scope if scope in ("all", "sessions", "papers") else "all"
    years, denom, series = trend_series(terms, scope) if terms else (YEARS, {}, [])
    return render_template("trends.html", raw=raw, terms=terms, scope=scope, years=years, denom=denom, series=series, breaks=BREAKS,
                           data=json.dumps({"years": years, "denom": denom, "breaks": BREAKS,
                                            "series": [{"term": s["term"], "counts": s["counts"]} for s in series]}))


@app.route("/titles")
def title_list():
    term = request.args.get("term", "")
    y = request.args.get("year", type=int)
    scope = request.args.get("scope", "all")
    rx = term_regex(term)
    if not rx:
        abort(400)
    out = [t for t in titles() if (y is None or t[0] == y) and rx.search(t[4])
           and (scope == "all" or (scope == "sessions" and t[1] == "session") or (scope == "papers" and t[1] == "paper"))]
    out.sort(key=lambda t: (t[0], t[3]))
    sess = {r["id"]: r for r in q(f"SELECT id, code, title FROM sessions WHERE id IN ({','.join('?' * min(len(out), 400))})", *[t[2] for t in out[:400]])} if out else {}
    return render_template("titles.html", term=term, y=y, scope=scope, rows=out[:400], total=len(out), sess=sess)


def corpus_rows(args, limit):
    y0, y1 = args.get("y0", type=int), args.get("y1", type=int)
    where, a = ["1=1"], []
    if y0:
        where.append("a.year >= ?"); a.append(y0)
    if y1:
        where.append("a.year <= ?"); a.append(y1)
    if args.get("role") in ("chair", "presenter", "respondent", "facilitator", "workshop leader"):
        where.append("a.role_group = ?"); a.append(args["role"])
    if args.get("inst", "").strip():
        where.append("i.name LIKE ?"); a.append(f"%{args['inst'].strip()}%")
    if args.get("non_us") == "1":
        where.append("i.country IS NOT NULL AND i.country != 'US'")
    sql = f"""SELECT a.year, a.session_id, s.code, s.title AS session_title, s.session_type, s.area, a.role, a.role_group,
              a.name_as_printed, a.affiliation_as_printed, a.paper_title, a.person_id, a.institution_id, i.name AS institution,
              i.country, d.public_url AS source_url
              FROM appearances a JOIN sessions s ON s.id = a.session_id LEFT JOIN institutions i ON i.id = a.institution_id
              LEFT JOIN source_documents d ON d.id = a.source_document_id WHERE {' AND '.join(where)} ORDER BY a.year, s.code, a.ord"""
    rx = term_regex(args.get("q", ""))
    out = []
    for r in db().execute(sql, a):
        if rx and not (rx.search((r["session_title"] or "").lower()) or rx.search((r["paper_title"] or "").lower())):
            continue
        out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def corpus_label(args):
    bits = []
    if args.get("q"): bits.append(f'titles containing "{args["q"]}"')
    if args.get("y0") or args.get("y1"): bits.append(f'{args.get("y0") or "2015"}–{args.get("y1") or "2025"}')
    if args.get("role"): bits.append(f'role: {args["role"]}')
    if args.get("inst"): bits.append(f'institution contains "{args["inst"]}"')
    if args.get("non_us") == "1": bits.append("outside the US")
    return "; ".join(bits) or "all listings"


@app.route("/corpus")
def corpus():
    has = any(request.args.get(k) for k in ("q", "y0", "y1", "role", "inst", "non_us"))
    rows = corpus_rows(request.args, MAX_EXPORT) if has else []
    qs = request.query_string.decode()
    label = corpus_label(request.args)
    cite = f'Community Writing Program Reader. Corpus: {label}. {len(rows):,} listings. Built {build_date()}. {SITE_URL}/corpus?{qs}'
    return render_template("corpus.html", has=has, n=len(rows), sample=rows[:15], qs=qs, a=request.args, label=label, cite=cite, capped=len(rows) >= MAX_EXPORT)


@app.route("/export.<fmt>")
def export(fmt):
    if fmt not in ("csv", "json"):
        abort(404)
    rows = corpus_rows(request.args, MAX_EXPORT)
    label = corpus_label(request.args)
    if fmt == "json":
        body = json.dumps({"corpus": {"filters": label, "listings": len(rows), "built": build_date(), "source": SITE_URL,
                                      "note": "People listed in the program, not attendees. Draft: the programs belong to the Coalition for Community Writing and are used with its permission."}, "rows": rows}, ensure_ascii=False)
        return Response(body, mimetype="application/json")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["year"])
    w.writeheader(); w.writerows(rows)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=ccw-corpus.csv"})


ERAS = {"2015–2019": (2015, 2019), "2021–2025": (2021, 2025), "All six editions": (2015, 2025)}
MIN_SHARED = 2
_NET = {}


def network_for(era):
    """People listed at two or more conferences who shared at least two sessions in a window (sessions of more than twelve of them left out)."""
    if era in _NET:
        return _NET[era]
    y0, y1 = ERAS[era]
    elig = {r["person_id"]: r["display_name"] for r in q("SELECT person_id, display_name FROM person_summary WHERE eligible = 1")}
    by_session = {}
    for r in q("SELECT session_id, person_id FROM appearances WHERE year BETWEEN ? AND ? AND person_id IS NOT NULL", y0, y1):
        if r["person_id"] in elig:
            by_session.setdefault(r["session_id"], set()).add(r["person_id"])
    pair = {}
    for people in by_session.values():
        if 2 <= len(people) <= 12:
            ps = sorted(people)
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    pair[(ps[i], ps[j])] = pair.get((ps[i], ps[j]), 0) + 1
    edges = [(a, b, n) for (a, b), n in pair.items() if n >= MIN_SHARED]
    deg = {}
    for a, b, n in edges:
        deg[a] = deg.get(a, 0) + n; deg[b] = deg.get(b, 0) + n
    keep = set(sorted(deg, key=lambda p: -deg[p])[:220])
    edges = [(a, b, n) for a, b, n in edges if a in keep and b in keep]
    nodes_in = {p for e in edges for p in e[:2]}
    abroad = {}
    for r in q("""SELECT a.person_id, i.country FROM appearances a JOIN institutions i ON i.id = a.institution_id
                  WHERE a.year BETWEEN ? AND ? AND i.country IS NOT NULL""", y0, y1):
        if r["person_id"] in nodes_in:
            abroad.setdefault(r["person_id"], []).append(1 if r["country"] != "US" else 0)
    nodes = [{"id": p, "name": elig[p], "deg": deg[p], "two": sum(abroad.get(p, [0])) * 2 > len(abroad.get(p, [0]))} for p in nodes_in]
    net = {"nodes": nodes, "edges": [{"a": a, "b": b, "n": n} for a, b, n in edges], "era": era, "sessions": len(by_session)}
    _NET[era] = net
    return net


def teams_for():
    elig = {r["person_id"]: r["display_name"] for r in q("SELECT person_id, display_name FROM person_summary WHERE eligible = 1")}
    by_session, year_of = {}, {}
    for r in q("SELECT session_id, person_id, year FROM appearances WHERE person_id IS NOT NULL"):
        if r["person_id"] in elig:
            by_session.setdefault(r["session_id"], set()).add(r["person_id"]); year_of[r["session_id"]] = r["year"]
    pair, yrs = {}, {}
    for sid, people in by_session.items():
        if 2 <= len(people) <= 8:
            ps = sorted(people)
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    pair[(ps[i], ps[j])] = pair.get((ps[i], ps[j]), 0) + 1
                    yrs.setdefault((ps[i], ps[j]), set()).add(year_of[sid])
    out = [{"a": a, "an": elig[a], "b": b, "bn": elig[b], "n": n, "years": sorted(yrs[(a, b)])} for (a, b), n in pair.items() if n >= 2 and len(yrs[(a, b)]) >= 2]
    out.sort(key=lambda t: (-t["n"], -len(t["years"]), t["an"]))
    return out[:100]


@app.route("/network")
def network():
    era = request.args.get("era", "All six editions")
    era = era if era in ERAS else "All six editions"
    net = network_for(era)
    return render_template("network.html", era=era, eras=list(ERAS), net=net, data=json.dumps(net, ensure_ascii=False), teams=teams_for())


@app.route("/formats")
def formats():
    types = q("SELECT year, COALESCE(session_type, 'Not printed') t, count(*) n FROM sessions GROUP BY 1, 2 ORDER BY 1, n DESC")
    roles = q("SELECT year, role_group, count(*) n FROM appearances GROUP BY 1, 2 ORDER BY 1")
    by_year = {}
    for r in types:
        by_year.setdefault(r["year"], {"types": [], "roles": {}})["types"].append((r["t"].replace("�", "–"), r["n"]))
    for r in roles:
        by_year.setdefault(r["year"], {"types": [], "roles": {}})["roles"][r["role_group"]] = r["n"]
    return render_template("formats.html", by_year=dict(sorted(by_year.items())), kinds=["presenter", "chair", "respondent", "facilitator", "workshop leader"])


@app.route("/tools")
def tools():
    return render_template("tools.html")


@app.route("/how-to-read")
def how():
    return render_template("how.html", breaks=BREAKS, notes=sorted(YEAR_NOTES.items()))


@app.route("/ethics")
def ethics():
    return render_template("ethics.html", contact=os.environ.get("READER_CONTACT", "jlewis2@olympic.edu"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.errorhandler(404)
def nf(_):
    return render_template("error.html", msg="That page isn't in the reader."), 404


@app.errorhandler(400)
def bad(_):
    return render_template("error.html", msg="That request was missing something."), 400
