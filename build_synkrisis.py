"""Build data/synkrisis.db, the derived database behind /compare (Synkrisis).  python build_synkrisis.py

Reads every series in series.json (each must pass check_series.py) and stores only aggregates: yearly census rows
side by side, institution footprints, word counts by decade, and counts of people who match across series.
Names are used in memory to find matches and are never written to the output. Adding a conference needs no change here.
"""
import itertools, os, re, sqlite3, sys, unicodedata
from collections import Counter, defaultdict

import check_series

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "synkrisis.db")
STOP = set("""about above after again against also among and any are because been before being between both but can could did does doing down during each
few for from further had has have having her here hers him his how into its itself just more most much must not now off once only other our out over own same
she should some such than that the their theirs them then there these they this those through too under until upon very was were what when where which while
who whom why will with within without would you your yours via per toward towards across new one two use using used""".split())
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "phd", "dr"}


def norm_tokens(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.\-']", " ", s)
    return [t for t in re.sub(r"[^a-z ]", "", s).split() if t not in SUFFIX]


def name_key(name):
    """First and last name only. Initials and one-word names cannot be matched safely, so they return None."""
    t = norm_tokens(name)
    if len(t) < 2 or len(t[0]) < 2 or len(t[-1]) < 2:
        return None
    return t[0] + " " + t[-1]


def main():
    reg = check_series.registry()
    bad = [s["key"] for s in reg if check_series.problems(s)]
    if bad:
        sys.exit(f"series fail the contract: {bad}. Run python check_series.py")
    if os.path.exists(OUT):
        os.remove(OUT)
    out = sqlite3.connect(OUT)
    out.executescript("""
    CREATE TABLE series (key TEXT PRIMARY KEY, ord INTEGER, name TEXT, short TEXT, color INTEGER, y0 INTEGER, y1 INTEGER, conventions INTEGER, sessions INTEGER, listings INTEGER, people INTEGER);
    CREATE TABLE series_year (series TEXT, year INTEGER, city TEXT, status TEXT, sessions INTEGER, appearances INTEGER, people INTEGER, newcomers INTEGER, returners INTEGER,
        with_affiliation INTEGER, matched INTEGER, non_us INTEGER, top10_share REAL, gini REAL, institutions INTEGER, chairs INTEGER, ocr INTEGER, PRIMARY KEY (series, year));
    CREATE TABLE inst (id TEXT PRIMARY KEY, name TEXT, country TEXT, kind TEXT);
    CREATE TABLE inst_series (inst TEXT, series TEXT, listings INTEGER, people INTEGER, first_year INTEGER, last_year INTEGER, years INTEGER, PRIMARY KEY (inst, series));
    CREATE TABLE series_inst_total (series TEXT PRIMARY KEY, listings INTEGER);
    CREATE TABLE word_decade (series TEXT, decade INTEGER, word TEXT, n INTEGER, PRIMARY KEY (series, decade, word));
    CREATE TABLE title_decade (series TEXT, decade INTEGER, n INTEGER, PRIMARY KEY (series, decade));
    CREATE TABLE pair_people (a TEXT, b TEXT, strict INTEGER, possible INTEGER, PRIMARY KEY (a, b));
    CREATE TABLE people_span (n_series INTEGER, strict_span INTEGER, n INTEGER);
    CREATE TABLE arrival (first_series TEXT, then_series TEXT, n INTEGER, PRIMARY KEY (first_series, then_series));
    CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    keys_by_series = {}
    for i, s in enumerate(reg):
        con = sqlite3.connect(f"file:{os.path.join(HERE, 'data', s['db'])}?mode=ro&immutable=1", uri=True)
        con.row_factory = sqlite3.Row
        ocr = set(s.get("ocr_years", []))
        cen = con.execute("select * from census order by year").fetchall()
        years = [r["year"] for r in cen]
        listings = sum(r["appearances"] or 0 for r in cen)
        npeople = con.execute("select count(distinct person_id) from appearances where person_id is not null").fetchone()[0]
        out.execute("insert into series values (?,?,?,?,?,?,?,?,?,?,?)", (s["key"], i, s["name"], s["short"], s["color"], min(years), max(years), len(years),
                    sum(r["sessions"] or 0 for r in cen), listings, npeople))
        for r in cen:
            out.execute("insert into series_year values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (s["key"], r["year"], r["city"], r["status"], r["sessions"], r["appearances"], r["people"],
                        r["newcomers"], r["returners"], r["with_affiliation"], r["matched"], r["non_us"], r["top10_share"], r["gini"], r["institutions"], r["chairs"], int(r["year"] in ocr)))
        for r in con.execute("select id, name, country, kind from institutions"):
            out.execute("insert or ignore into inst values (?,?,?,?)", tuple(r))
        for r in con.execute("""select institution_id, count(*) n, count(distinct person_id) p, min(year) a, max(year) b, count(distinct year) y
                                from appearances where institution_id is not null group by institution_id"""):
            out.execute("insert into inst_series values (?,?,?,?,?,?,?)", (r[0], s["key"], r["n"], r["p"], r["a"], r["b"], r["y"]))
        out.execute("insert into series_inst_total values (?,?)", (s["key"], con.execute("select count(*) from appearances where institution_id is not null").fetchone()[0]))
        wc = defaultdict(Counter)
        td = Counter()
        for r in con.execute("select year, text from titles"):
            d = r["year"] // 10 * 10
            td[d] += 1
            for w in set(re.findall(r"[a-z]{4,}", (r["text"] or "").lower())):
                if w not in STOP:
                    wc[d][w] += 1
        for d, n in td.items():
            out.execute("insert into title_decade values (?,?,?)", (s["key"], d, n))
        for d, c in wc.items():
            out.executemany("insert into word_decade values (?,?,?,?)", [(s["key"], d, w, n) for w, n in c.items() if n >= 2])
        ppl = defaultdict(lambda: [set(), set()])
        for r in con.execute("select a.year, a.institution_id, p.display_name from appearances a join people p on p.id = a.person_id"):
            if r["year"] in ocr:
                continue
            k = name_key(r["display_name"])
            if k:
                ppl[k][0].add(r["year"])
                if r["institution_id"]:
                    ppl[k][1].add(r["institution_id"])
        keys_by_series[s["key"]] = ppl
        con.close()
    skeys = [s["key"] for s in reg]
    allk = defaultdict(list)
    for sk in skeys:
        for k in keys_by_series[sk]:
            allk[k].append(sk)
    pair, span, arr = Counter(), Counter(), Counter()
    for k, ss in allk.items():
        if len(ss) < 2:
            continue
        strict_edges = []
        for a, b in itertools.combinations(ss, 2):
            pair[(a, b, "possible")] += 1
            if keys_by_series[a][k][1] & keys_by_series[b][k][1]:
                pair[(a, b, "strict")] += 1
                strict_edges.append((a, b))
        comp = {x: x for x in ss}

        def find(x):
            while comp[x] != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x
        for a, b in strict_edges:
            comp[find(a)] = find(b)
        size = Counter(find(x) for x in ss)
        span[(len(ss), max(size.values()) if strict_edges else 1)] += 1
        for a, b in strict_edges:
            fa, fb = min(keys_by_series[a][k][0]), min(keys_by_series[b][k][0])
            if fa < fb:
                arr[(a, b)] += 1
            elif fb < fa:
                arr[(b, a)] += 1
    for a, b in itertools.combinations(skeys, 2):
        out.execute("insert into pair_people values (?,?,?,?)", (a, b, pair[(a, b, "strict")], pair[(a, b, "possible")]))
    for (n, st), c in span.items():
        out.execute("insert into people_span values (?,?,?)", (n, st, c))
    for (a, b), c in arr.items():
        out.execute("insert into arrival values (?,?,?)", (a, b, c))
    out.commit()
    out.close()
    print("built", OUT, round(os.path.getsize(OUT) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
