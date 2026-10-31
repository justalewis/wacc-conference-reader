"""Synkrisis: a read-only Flask app that compares the conference readers (see ../build_synkrisis.py).

Mounted under /compare by ../wsgi.py (links use request.script_root). Every page is noindex.
It reads data/synkrisis.db, which holds aggregates only, and each series' own database for title searches.
Series come from ../series.json, so a new conference appears here once it is registered and the database is rebuilt.
No page names a person: people appear only as counts of matches across series.
"""
import json, os, re, sqlite3
from datetime import date
from flask import Flask, Response, abort, g, render_template, request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
DB = os.environ.get("SYNKRISIS_DB", os.path.join(DATA, "synkrisis.db"))
REGISTRY = json.load(open(os.path.join(HERE, "..", "series.json"), encoding="utf-8"))["series"]
REG = {s["key"]: s for s in REGISTRY}
MAX_SERIES = 8          # the chart palette has eight fixed hues; more would repeat one
MIN_TITLES = 30         # a year with fewer titles than this gives a rate too unstable to draw
SUPPRESS = 5            # a count below this is shown as "fewer than 5"

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
    if d is not None:
        d.close()


def q(sql, *args):
    return db().execute(sql, args).fetchall()


def all_series():
    return [dict(r) for r in q("SELECT * FROM series ORDER BY ord")]


def selected():
    """The series chosen with ?s=a,b (default all, at most eight, in registry order)."""
    known = [s["key"] for s in all_series()]
    raw = ",".join(request.args.getlist("s"))
    want = [k for k in raw.split(",") if k in known]
    keys = [k for k in known if k in want] or known
    return keys[:MAX_SERIES]


def build_date():
    return date.fromtimestamp(os.path.getmtime(DB)).isoformat() if os.path.exists(DB) else ""


@app.context_processor
def inject():
    allk = all_series()
    sel = selected()
    return {"build_date": build_date(), "P": request.script_root, "ROOT": (request.script_root.rsplit("/", 1)[0] or "") + "/",
            "series_all": allk, "sel": sel, "selq": ",".join(sel) if len(sel) != len(allk) else "", "reg": REG,
            "reader_url": lambda k: request.script_root.rsplit("/", 1)[0] + REG[k]["url"].rstrip("/")}


@app.template_filter("num")
def num(n):
    return f"{n:,}" if isinstance(n, int) else n


@app.template_filter("pct")
def pct(x):
    return "" if x is None else f"{100 * x:.1f}%"


def small(n):
    """Counts under the suppression threshold are not shown."""
    return f"fewer than {SUPPRESS}" if n < SUPPRESS else f"{n:,}"


app.jinja_env.globals["small"] = small


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.after_request
def noindex(r):
    r.headers["X-Robots-Tag"] = "noindex, nofollow"
    return r


@app.errorhandler(404)
def nf(_):
    return render_template("error.html", msg="That page does not exist."), 404


@app.errorhandler(400)
def bad(_):
    return render_template("error.html", msg="That request could not be read."), 400


# ---- home ---------------------------------------------------------------------------------------------------------

@app.route("/")
def home():
    rows = all_series()
    for r in rows:
        r["breaks"] = REG[r["key"]]["breaks"]
        r["caveat"] = REG[r["key"]]["caveat"]
    return render_template("home.html", rows=rows)


# ---- Chronikon: the series on one set of years ---------------------------------------------------------------------

METRICS = [
    ("people", "People listed", "count"),
    ("sessions", "Sessions", "count"),
    ("appearances", "Listings of a person in a session", "count"),
    ("listings_per_session", "Listings per session", "ratio"),
    ("newcomer_share", "Share of people first listed that year", "share"),
    ("returner_share", "Share of people listed in an earlier year", "share"),
    ("affiliation_share", "Share of listings that print an institution", "share"),
    ("institutions", "Institutions matched", "count"),
    ("top10_share", "Share of listings from ten institutions", "share"),
    ("gini", "Concentration of listings among institutions (Gini)", "ratio"),
]


def metric_value(r, m):
    a, p, s = r["appearances"] or 0, r["people"] or 0, r["sessions"] or 0
    if m == "listings_per_session":
        return round(a / s, 2) if s else None
    if m == "newcomer_share":
        return round(r["newcomers"] / p, 4) if p and r["newcomers"] is not None else None
    if m == "returner_share":
        return round(r["returners"] / p, 4) if p and r["returners"] is not None else None
    if m == "affiliation_share":
        return round(r["with_affiliation"] / a, 4) if a and r["with_affiliation"] is not None else None
    v = r[m]
    return None if v is None else (round(v, 4) if isinstance(v, float) else v)


@app.route("/chronikon")
def chronikon():
    m = request.args.get("m", "people")
    if m not in {x[0] for x in METRICS}:
        m = "people"
    sel = selected()
    y0, y1 = request.args.get("y0", type=int), request.args.get("y1", type=int)
    rows = q(f"SELECT * FROM series_year WHERE series IN ({','.join('?' * len(sel))}) ORDER BY year", *sel)
    years = sorted({r["year"] for r in rows if (not y0 or r["year"] >= y0) and (not y1 or r["year"] <= y1)})
    by = {k: {r["year"]: r for r in rows if r["series"] == k} for k in sel}
    data = {"years": years, "label": next(x[1] for x in METRICS if x[0] == m), "kind": next(x[2] for x in METRICS if x[0] == m),
            "series": [{"key": k, "short": REG[k]["short"], "color": REG[k]["color"],
                        "values": [metric_value(by[k][y], m) if y in by[k] else None for y in years],
                        "ocr": [bool(by[k][y]["ocr"]) if y in by[k] else False for y in years]} for k in sel]}
    gaps = []
    for k in sel:
        have = sorted(by[k])
        gaps.append({"key": k, "short": REG[k]["short"], "breaks": [b for b in REG[k]["breaks"]]})
    return render_template("chronikon.html", metrics=METRICS, m=m, y0=y0, y1=y1, data=json.dumps(data), tbl=data, gaps=gaps)


# ---- Oikoi: institutions across series -------------------------------------------------------------------------------

def inst_matrix(sel):
    """Shared institutions between each pair, and how many of each series' 25 most-listed schools are in the other's 25."""
    have = {k: {r["inst"]: r["listings"] for r in q("SELECT inst, listings FROM inst_series WHERE series = ?", k)} for k in sel}
    top = {k: set(sorted(v, key=lambda i: -v[i])[:25]) for k, v in have.items()}
    out = {}
    for a in sel:
        for b in sel:
            if a == b:
                continue
            sa, sb = set(have[a]), set(have[b])
            out[(a, b)] = {"shared": len(sa & sb), "jaccard": len(sa & sb) / len(sa | sb) if sa | sb else 0, "top": len(top[a] & top[b])}
    return have, out


@app.route("/oikoi")
def oikoi():
    sel = selected()
    name = request.args.get("name", "").strip()
    outside = request.args.get("outside") == "1"
    minser = max(2, min(request.args.get("min", 2, type=int), len(sel))) if len(sel) > 1 else 1
    have, mat = inst_matrix(sel)
    totals = {r["series"]: r["listings"] for r in q("SELECT * FROM series_inst_total")}
    count = {}
    for k in sel:
        for i in have[k]:
            count.setdefault(i, []).append(k)
    by_k = {}
    for i, ks in count.items():
        by_k[len(ks)] = by_k.get(len(ks), 0) + 1
    info = {r["id"]: r for r in q("SELECT * FROM inst")}
    rows = []
    for i, ks in count.items():
        if len(ks) < minser:
            continue
        r = info.get(i)
        if not r or (name and name.lower() not in (r["name"] or "").lower()) or (outside and (r["country"] in (None, "US"))):
            continue
        rows.append({"id": i, "name": r["name"], "country": r["country"], "n": len(ks), "total": sum(have[k][i] for k in ks),
                     "per": {k: (1000 * have[k][i] / totals[k] if k in ks and totals.get(k) else None) for k in sel},
                     "raw": {k: have[k].get(i) for k in sel}})
    rows.sort(key=lambda r: (-r["n"], -r["total"]))
    return render_template("oikoi.html", mat=mat, rows=rows[:150], n_rows=len(rows), by_k=by_k, name=name, outside=outside, minser=minser,
                           sizes={k: len(have[k]) for k in sel})


# ---- Topoi: terms across series --------------------------------------------------------------------------------------

_TITLES = {}


def titles_of(key):
    if key not in _TITLES:
        con = sqlite3.connect(f"file:{os.path.join(DATA, REG[key]['db'])}?mode=ro&immutable=1", uri=True)
        _TITLES[key] = [(y, k, (t or "").lower()) for y, k, t in con.execute("SELECT year, kind, text FROM titles")]
        con.close()
    return _TITLES[key]


def term_regex(term):
    t = term.strip().lower()
    if not t:
        return None
    star = t.endswith("*")
    t = t.rstrip("*").strip()
    if not t:
        return None
    return re.compile(r"\b" + re.escape(t) + ("" if star else r"\b"))


@app.route("/topoi")
def topoi():
    term = request.args.get("term", "").strip()[:80]
    scope = request.args.get("scope", "all")
    scope = scope if scope in ("all", "sessions", "papers") else "all"
    sel = selected()
    rx = term_regex(term)
    data, table = None, []
    if rx:
        years = set()
        res = {}
        for k in sel:
            hit, den = {}, {}
            for y, kind, t in titles_of(k):
                if scope == "sessions" and kind != "session" or scope == "papers" and kind != "paper":
                    continue
                den[y] = den.get(y, 0) + 1
                if rx.search(t):
                    hit[y] = hit.get(y, 0) + 1
            res[k] = (hit, den)
            years |= set(den)
        years = sorted(years)
        series = []
        for k in sel:
            hit, den = res[k]
            vals = [round(1000 * hit.get(y, 0) / den[y], 2) if den.get(y, 0) >= MIN_TITLES else None for y in years]
            ys = [y for y in years if hit.get(y, 0) >= 2]
            ok = [y for y in years if den.get(y, 0) >= MIN_TITLES and hit.get(y, 0) >= 2]
            peak = max(ok, key=lambda y: (hit[y] / den[y], y), default=None)
            table.append({"key": k, "short": REG[k]["short"], "total": sum(hit.values()), "titles": sum(den.values()), "first": ys[0] if ys else None,
                          "peak": peak if peak and hit.get(peak) else None, "peak_rate": round(1000 * hit[peak] / den[peak], 1) if peak and hit.get(peak) else None,
                          "link": f"{REG[k]['url']}titles?term={term}&scope={scope}"})
            series.append({"key": k, "short": REG[k]["short"], "color": REG[k]["color"], "values": vals,
                           "ocr": [y in set(REG[k].get("ocr_years", [])) for y in years]})
        data = {"years": years, "series": series, "term": term}
    # words that set a series apart
    d0 = request.args.get("d0", type=int)
    d1 = request.args.get("d1", type=int)
    distinct = vocab(sel, d0, d1)
    return render_template("topoi.html", term=term, scope=scope, data=json.dumps(data) if data else "", has=bool(data), table=table, distinct=distinct, d0=d0, d1=d1)


def vocab(sel, d0, d1, top=15):
    import math
    cond, args = "", []
    if d0:
        cond += " AND decade >= ?"; args.append(d0 // 10 * 10)
    if d1:
        cond += " AND decade <= ?"; args.append(d1 // 10 * 10)
    ph = ",".join("?" * len(sel))
    n = {r["series"]: r["n"] for r in q(f"SELECT series, SUM(n) n FROM title_decade WHERE series IN ({ph}){cond} GROUP BY series", *sel, *args)}
    words = {}
    for r in q(f"SELECT series, word, SUM(n) n FROM word_decade WHERE series IN ({ph}){cond} GROUP BY series, word", *sel, *args):
        words.setdefault(r["word"], {})[r["series"]] = r["n"]
    out = {}
    for k in sel:
        nk = n.get(k, 0)
        nr = sum(v for kk, v in n.items() if kk != k)
        if not nk or not nr:
            continue
        sc = []
        for w, d in words.items():
            a = d.get(k, 0)
            if a < 5:
                continue
            r = sum(v for kk, v in d.items() if kk != k)
            sc.append((math.log((a + .5) / (nk - a + .5)) - math.log((r + .5) / (nr - r + .5)), w, a))
        sc.sort(reverse=True)
        out[k] = [(w, a) for _, w, a in sc[:top]]
    return out


# ---- Prosopographia: people across series, counts only ------------------------------------------------------------------

@app.route("/prosopographia")
def prosopographia():
    sel = selected()
    pairs = {(r["a"], r["b"]): r for r in q("SELECT * FROM pair_people")}
    span = q("SELECT n_series, strict_span, n FROM people_span ORDER BY n_series, strict_span")
    arrival = {(r["first_series"], r["then_series"]): r["n"] for r in q("SELECT * FROM arrival")}
    size = {s["key"]: s["people"] for s in all_series()}
    return render_template("prosopographia.html", pairs=pairs, span=span, arrival=arrival, size=size, nser=len(all_series()))


# ---- reading notes ------------------------------------------------------------------------------------------------------

@app.route("/how-to-read")
def how():
    return render_template("how.html")
