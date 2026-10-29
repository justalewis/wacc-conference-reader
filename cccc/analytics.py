"""Aggregates for the reader's tools: formats, area by institution type, the atlas, and panel networks.

Each function takes a read-only sqlite3 connection (row_factory = sqlite3.Row) and returns plain
data. Results are cached for the life of the process, since reader.db never changes while it runs.
Ethics thresholds (see the ethics page): people appear in network views only with three or more
listings, and an edge needs two shared sessions; group measures need at least 20 listings.
"""
import collections, itertools, math, re

_CACHE = {}

def cached(fn):
    def wrap(con, *a):
        k = (fn.__name__, a)
        if k not in _CACHE:
            _CACHE[k] = fn(con, *a)
        return _CACHE[k]
    wrap.__name__ = fn.__name__
    return wrap

# ---- formats ------------------------------------------------------------------------------

FORMATS = ["concurrent session", "individual presentation", "roundtable", "workshop", "poster", "group meeting", "engaged learning", "other"]
SKIP_TYPES = {"registration/exhibit hall hours", "open rooms", "event"}

def classify(code, session_type):
    st = (session_type or "").lower()
    if st:
        if st in SKIP_TYPES:
            return None
        if "poster" in st:
            return "poster"
        if "roundtable" in st:
            return "roundtable"
        if "workshop" in st:
            return "workshop"
        if "individual" in st:
            return "individual presentation"
        if "special interest" in st or "committee" in st or "caucus" in st:
            return "group meeting"
        if "engaged learning" in st:
            return "engaged learning"
        if "panel" in st or "presentation" in st or st == "session":
            return "concurrent session"
        return "other"
    letters = re.match(r"([A-Z]+)", code or "")
    p = letters.group(1) if letters else ""
    if "SIG" in p:
        return "group meeting"
    if p in ("W", "MW", "AW", "SW"):
        return "workshop"
    if p == "POS":
        return "poster"
    if len(p) == 1:
        return "concurrent session"
    return "other"

@cached
def formats(con):
    """{year: {format: sessions}} and {year: (mean, median, share of four or more people)} for sessions with people."""
    counts = collections.defaultdict(collections.Counter)
    sizes = collections.defaultdict(list)
    n_people = {r["session_id"]: r["n"] for r in con.execute("SELECT session_id, count(*) n FROM appearances GROUP BY session_id")}
    for r in con.execute("SELECT id, year, code, session_type FROM sessions WHERE parent_id IS NULL"):
        f = classify(r["code"], r["session_type"])
        if f is None:
            continue
        counts[r["year"]][f] += 1
        if r["id"] in n_people and f == "concurrent session":
            sizes[r["year"]].append(n_people[r["id"]])
    stats = {}
    for y, v in sizes.items():
        v.sort()
        stats[y] = (round(sum(v) / len(v), 2), v[len(v) // 2], round(sum(1 for x in v if x >= 4) / len(v), 3), len(v))
    return {y: dict(c) for y, c in sorted(counts.items())}, stats

# ---- area by institution type -------------------------------------------------------------

TYPES = ["two-year college", "public four-year", "private nonprofit four-year", "for-profit four-year", "outside the US", "no match"]

def inst_type(r):
    if r["institution_id"] is None:
        return "no match"
    if r["country"] and r["country"] != "US":
        return "outside the US"
    if r["two_year"]:
        return "two-year college"
    if r["control"] == 1:
        return "public four-year"
    if r["control"] == 2:
        return "private nonprofit four-year"
    if r["control"] == 3:
        return "for-profit four-year"
    return "no match"

PERIODS = {"2004–2010": (2004, 2010), "2011–2017": (2011, 2017), "2019–2026": (2019, 2026)}

@cached
def area_by_type(con, period):
    y0, y1 = PERIODS[period]
    rows = con.execute("""SELECT s.area_group g, a.institution_id, i.country, i.two_year, i.control FROM appearances a
                          JOIN sessions s ON s.id = a.session_id LEFT JOIN institutions i ON i.id = a.institution_id
                          WHERE s.year BETWEEN ? AND ? AND s.area_group IS NOT NULL AND s.parent_id IS NULL""", (y0, y1)).fetchall()
    cell = collections.defaultdict(collections.Counter)
    tot_t, tot_g = collections.Counter(), collections.Counter()
    for r in rows:
        t = inst_type(r)
        cell[r["g"]][t] += 1
        tot_t[t] += 1
        tot_g[r["g"]] += 1
    n = sum(tot_t.values())
    out = []
    for g in sorted(tot_g, key=lambda x: -tot_g[x]):
        cols = {}
        for t in TYPES:
            c, base = cell[g][t], tot_t[t]
            share_in_type = c / base if base else None  # of this type's listings, how many sit in this family
            overall = tot_g[g] / n
            cols[t] = {"n": c, "share": share_in_type, "lift": (share_in_type / overall) if (share_in_type is not None and overall and base >= 20 and c >= 5) else None}
        out.append({"group": g, "total": tot_g[g], "cols": cols})
    return {"rows": out, "type_totals": dict(tot_t), "n": n}

# ---- atlas --------------------------------------------------------------------------------

HOSTS = {
    "Chicago": (41.88, -87.63), "Atlanta": (33.75, -84.39), "San Antonio": (29.42, -98.49), "San Francisco": (37.77, -122.42),
    "New York": (40.71, -74.01), "New Orleans": (29.95, -90.07), "Louisville": (38.25, -85.76), "St. Louis": (38.63, -90.2),
    "Las Vegas": (36.17, -115.14), "Indianapolis": (39.77, -86.16), "Tampa": (27.95, -82.46), "Houston": (29.76, -95.37),
    "Portland, OR": (45.52, -122.68), "Kansas City": (39.1, -94.58), "Pittsburgh": (40.44, -79.99), "Milwaukee": (43.04, -87.91),
    "Spokane": (47.66, -117.43), "Baltimore": (39.29, -76.61), "Cleveland": (41.5, -81.69),
}

def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

@cached
def atlas_year(con, year):
    pts = [dict(r) for r in con.execute("""SELECT i.id, i.name, i.lat, i.lon, i.two_year, iy.appearances n, iy.people p FROM inst_year iy
                                           JOIN institutions i ON i.id = iy.institution_id WHERE iy.year = ? AND i.lat IS NOT NULL""", (year,))]
    city = con.execute("SELECT city, status FROM conventions WHERE year = ?", (year,)).fetchone()
    host = HOSTS.get(city["city"]) if city else None
    tot = con.execute("SELECT count(*) n FROM appearances WHERE year = ?", (year,)).fetchone()["n"]
    mapped = sum(p["n"] for p in pts)
    inside = [p for p in pts if 24 <= p["lat"] <= 50 and -125 <= p["lon"] <= -66]
    return {"year": year, "city": city["city"] if city else None, "status": city["status"] if city else None, "host": host,
            "points": inside, "mapped": mapped, "on_map": sum(p["n"] for p in inside), "total": tot}

@cached
def host_draw(con):
    out = []
    for r in con.execute("SELECT year, city, status FROM conventions WHERE year >= 1998 ORDER BY year"):
        host = HOSTS.get(r["city"])
        if not host or r["status"] == "virtual":
            continue
        rows = con.execute("""SELECT i.lat, i.lon, iy.appearances n FROM inst_year iy JOIN institutions i ON i.id = iy.institution_id
                              WHERE iy.year = ? AND i.lat IS NOT NULL""", (r["year"],)).fetchall()
        if not rows:
            continue
        d = sorted((haversine(host, (x["lat"], x["lon"])), x["n"]) for x in rows)
        tot = sum(n for _, n in d)
        half, acc, med = tot / 2, 0, None
        for km, n in d:
            acc += n
            if acc >= half:
                med = km; break
        out.append({"year": r["year"], "city": r["city"], "listings": tot, "within_300": sum(n for km, n in d if km <= 300) / tot,
                    "within_800": sum(n for km, n in d if km <= 800) / tot, "median_km": round(med)})
    return out

# ---- networks -----------------------------------------------------------------------------

ERAS = {"2004–2009": (2004, 2009), "2010–2015": (2010, 2015), "2016–2020": (2016, 2020), "2021–2026": (2021, 2026)}
MIN_LISTINGS, MIN_SHARED = 3, 2

def _eligible(con):
    return {r["person_id"]: r["display_name"] for r in con.execute(
        "SELECT person_id, display_name FROM person_summary WHERE eligible = 1 AND appearances >= ?", (MIN_LISTINGS,))}

@cached
def network(con, era):
    y0, y1 = ERAS[era]
    elig = _eligible(con)
    by_session = collections.defaultdict(set)
    for r in con.execute("""SELECT a.session_id, a.person_id FROM appearances a JOIN sessions s ON s.id = a.session_id
                            WHERE s.year BETWEEN ? AND ? AND a.person_id IS NOT NULL""", (y0, y1)):
        if r["person_id"] in elig:
            by_session[r["session_id"]].add(r["person_id"])
    pair = collections.Counter()
    for people in by_session.values():
        if 2 <= len(people) <= 12:  # a 40-person forum links everyone to everyone and says little
            for a, b in itertools.combinations(sorted(people), 2):
                pair[(a, b)] += 1
    edges = [(a, b, n) for (a, b), n in pair.items() if n >= MIN_SHARED]
    deg = collections.Counter()
    for a, b, n in edges:
        deg[a] += n; deg[b] += n
    keep = {p for p, _ in deg.most_common(220)}
    edges = [(a, b, n) for a, b, n in edges if a in keep and b in keep]
    nodes_in = {p for e in edges for p in e[:2]}
    types = {}
    for r in con.execute("""SELECT a.person_id, i.two_year FROM appearances a JOIN sessions s ON s.id = a.session_id
                            LEFT JOIN institutions i ON i.id = a.institution_id WHERE s.year BETWEEN ? AND ?""", (y0, y1)):
        if r["person_id"] in nodes_in:
            types.setdefault(r["person_id"], []).append(1 if r["two_year"] else 0)
    nodes = [{"id": p, "name": elig[p], "deg": deg[p], "two": (sum(types.get(p, [0])) * 2 > len(types.get(p, [0])))} for p in nodes_in]
    return {"nodes": nodes, "edges": [{"a": a, "b": b, "n": n} for a, b, n in edges], "era": era, "sessions": len(by_session)}

@cached
def teams(con):
    """Pairs of eligible people who shared at least three sessions across at least two conventions."""
    elig = _eligible(con)
    by_session = collections.defaultdict(set)
    year_of = {}
    for r in con.execute("""SELECT a.session_id, a.person_id, s.year FROM appearances a JOIN sessions s ON s.id = a.session_id
                            WHERE a.person_id IS NOT NULL"""):
        if r["person_id"] in elig:
            by_session[r["session_id"]].add(r["person_id"]); year_of[r["session_id"]] = r["year"]
    pair, yrs = collections.Counter(), collections.defaultdict(set)
    for sid, people in by_session.items():
        if 2 <= len(people) <= 8:
            for a, b in itertools.combinations(sorted(people), 2):
                pair[(a, b)] += 1; yrs[(a, b)].add(year_of[sid])
    out = [{"a": a, "an": elig[a], "b": b, "bn": elig[b], "n": n, "years": sorted(yrs[(a, b)])} for (a, b), n in pair.items()
           if n >= 3 and len(yrs[(a, b)]) >= 2]
    out.sort(key=lambda t: (-t["n"], -len(t["years"]), t["an"]))
    return out[:120]

@cached
def bridges(con):
    """Per year: of sessions with two or more institution-matched people, the share mixing two-year colleges with others."""
    sess = collections.defaultdict(set)
    for r in con.execute("""SELECT a.session_id, a.year, a.person_id, i.two_year, i.country FROM appearances a
                            JOIN institutions i ON i.id = a.institution_id WHERE a.person_id IS NOT NULL"""):
        t = "two" if r["two_year"] else ("abroad" if r["country"] and r["country"] != "US" else "four")
        sess[(r["session_id"], r["year"])].add((r["person_id"], t))
    out = collections.defaultdict(lambda: [0, 0, 0])
    for (sid, y), pts in sess.items():
        if len({p for p, _ in pts}) < 2:
            continue
        kinds = {t for _, t in pts}
        out[y][0] += 1
        if "two" in kinds and ("four" in kinds or "abroad" in kinds):
            out[y][1] += 1
        if "abroad" in kinds and len(kinds) > 1:
            out[y][2] += 1
    return {y: {"sessions": v[0], "mixed_two": v[1], "mixed_abroad": v[2], "share_two": v[1] / v[0], "share_abroad": v[2] / v[0]} for y, v in sorted(out.items()) if v[0] >= 20}
