"""WAC Clearinghouse conference archives: a selector at / and one reader per conference archive.

Run: python -m flask --app wsgi run   (or waitress-serve --listen=127.0.0.1:8080 wsgi:application)
/cccc, /iwac, /cw, /cptsc and /ccw are separate Flask apps mounted under their own prefixes (each page links with request.script_root).
"""
import importlib.util, os, sys
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask, render_template

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_app", os.path.join(HERE, name, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.app


selector = Flask(__name__, template_folder=os.path.join(HERE, "selector", "templates"), static_folder=os.path.join(HERE, "cccc", "static"), static_url_path="/static")
CORPORA = {}


@selector.route("/")
def index():
    return render_template("selector.html", corpora=CORPORA)


@selector.after_request
def noindex(r):
    r.headers["X-Robots-Tag"] = "noindex, nofollow"
    return r


import sqlite3


def stats(db, years_sql, first_last):
    con = sqlite3.connect(f"file:{os.path.join(HERE, 'data', db)}?mode=ro&immutable=1", uri=True)
    sessions = con.execute("select count(*) from sessions").fetchone()[0]
    people = con.execute("select count(distinct person_id) from appearances").fetchone()[0]
    y = con.execute(years_sql).fetchone()
    n = con.execute("select count(*) from census").fetchone()[0]
    con.close()
    return sessions, people, f"{y[0]} to {y[1]}", n


if os.path.exists(os.path.join(HERE, "data", "cccc.db")):
    s, p, yrs, n = stats("cccc.db", "select min(year), max(year) from census", None)
    CORPORA["cccc"] = {"name": "CCCC convention programs", "short": "CCCC", "url": "/cccc/", "sessions": s, "people": p, "years": yrs, "conferences": n,
                       "blurb": "The Conference on College Composition and Communication, from NCTE's printed and online programs.",
                       "caveat": "2000 to 2003 are missing and 2018 prints hashtags where other years print areas."}
if os.path.exists(os.path.join(HERE, "data", "iwac.db")):
    s, p, yrs, n = stats("iwac.db", "select min(year), max(year) from census", None)
    CORPORA["iwac"] = {"name": "International WAC Conference programs", "short": "IWAC", "url": "/iwac/", "sessions": s, "people": p, "years": yrs, "conferences": n,
                       "blurb": "The International Writing Across the Curriculum Conference, from the programs the Clearinghouse hosts.",
                       "caveat": "A draft: 2002 is an OCR'd scan, and 2008 and 2016 have known weak spots."}
if os.path.exists(os.path.join(HERE, "data", "cw.db")):
    s, p, yrs, n = stats("cw.db", "select min(year), max(year) from census", None)
    CORPORA["cw"] = {"name": "Computers and Writing conference programs", "short": "Computers and Writing", "url": "/cw/", "sessions": s, "people": p, "years": yrs, "conferences": n,
                     "blurb": "The Computers and Writing Conference, from the program PDFs in Are We There Yet? (Computers and Composition Digital Press), and for 2022 to 2024 from programs the organizers supplied.",
                     "caveat": "A draft: 1987 to 1988, 1991 to 1994, 2016 to 2017 and 2020 to 2021 are missing, 1997, 2007, 2008 and 2012 are weak scans, seven years print few or no institutions, and the 2024 schedule names almost no one."}
if os.path.exists(os.path.join(HERE, "data", "cptsc.db")):
    s, p, yrs, n = stats("cptsc.db", "select min(year), max(year) from census", None)
    CORPORA["cptsc"] = {"name": "CPTSC conference proceedings", "short": "CPTSC", "url": "/cptsc/", "sessions": s, "people": p, "years": yrs, "conferences": n,
                        "blurb": "The annual meeting of the Council for Programs in Technical and Scientific Communication, from the proceedings volumes on cptsc.org.",
                        "caveat": "A draft: 1976 and 2020 are missing, 2016 was cancelled but its proceedings were published, the volumes through 2004 are scans read by OCR and checked by hand, and 1989 is an agenda."}
if os.path.exists(os.path.join(HERE, "data", "ccw.db")):
    s, p, yrs, n = stats("ccw.db", "select min(year), max(year) from census", None)
    CORPORA["ccw"] = {"name": "Conference on Community Writing programs", "short": "Community Writing", "url": "/ccw/", "sessions": s, "people": p, "years": yrs, "conferences": n,
                      "blurb": "The Conference on Community Writing, from the programs the Coalition for Community Writing published: two PDFs, a schedule page and two public program documents.",
                      "caveat": "A draft: the conference meets in odd years, 2025 is only its public DeepThink Tank listing and one keynote, and the 2019 and 2021 programs print some chairs and speakers without institutions."}
CORPORA = list(CORPORA.values())

mounts = {}
for key in ("cccc", "iwac", "cw", "cptsc", "ccw"):
    p = os.path.join(HERE, key, "app.py")
    if os.path.exists(p):
        mounts["/" + key] = load(key)
application = DispatcherMiddleware(selector, mounts)
# APP_PREFIX puts the whole site under a path, e.g. /repository/professional/conferences (see DEPLOY.md)
PREFIX = os.environ.get("APP_PREFIX", "").rstrip("/")
if PREFIX:
    application = DispatcherMiddleware(lambda env, start: (start("404 Not Found", [("Content-Type", "text/plain")]), [b"Not found"])[1], {PREFIX: application})
