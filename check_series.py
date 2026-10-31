"""Check each registered series against the contract the comparator relies on.  python check_series.py [key ...]

A new conference passes when data/<db> has these tables with at least these columns. Extra columns and tables
(CCCC has IPEDS fields and area groups) are ignored. Exit status is 1 if any series fails."""
import json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = {
    "sessions": ["id", "year", "title", "session_type", "area", "code"],
    "appearances": ["id", "year", "session_id", "person_id", "institution_id", "role", "role_group", "name_as_printed", "affiliation_as_printed", "paper_title"],
    "people": ["id", "display_name"],
    "person_summary": ["person_id", "display_name", "first_year", "last_year", "conventions", "appearances", "eligible"],
    "institutions": ["id", "name", "country", "kind", "lat", "lon", "ror_id"],
    "inst_year": ["year", "institution_id", "appearances", "people"],
    "titles": ["year", "kind", "session_id", "text"],
    "census": ["year", "city", "status", "sessions", "appearances", "people", "newcomers", "returners", "with_affiliation", "matched",
               "non_us", "top10_share", "gini", "institutions", "chairs"],
    "conventions": ["year", "city", "status", "theme", "chair"],
}


def registry():
    return json.load(open(os.path.join(HERE, "series.json"), encoding="utf-8"))["series"]


def problems(s):
    path = os.path.join(HERE, "data", s["db"])
    if not os.path.exists(path):
        return [f"{s['db']} is missing"]
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    out = []
    for table, cols in CONTRACT.items():
        have = [r[1] for r in con.execute(f"pragma table_info({table})")]
        if not have:
            out.append(f"table {table} is missing")
        else:
            out += [f"{table}.{c} is missing" for c in cols if c not in have]
    if not out and not con.execute("select count(*) from census").fetchone()[0]:
        out.append("census is empty")
    con.close()
    return out


if __name__ == "__main__":
    want = set(sys.argv[1:])
    bad = 0
    for s in registry():
        if want and s["key"] not in want:
            continue
        p = problems(s)
        print(("FAIL " if p else "ok   ") + s["key"], *p, sep="\n  " if p else " ")
        bad += bool(p)
    sys.exit(1 if bad else 0)
