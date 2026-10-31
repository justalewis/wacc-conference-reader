"""WAC Clearinghouse conference archives: a selector at / and one reader per conference archive.

Run: python -m flask --app wsgi run   (or waitress-serve --listen=127.0.0.1:8080 wsgi:application)
One Flask app per series in series.json, plus /compare (Synkrisis), is mounted under its own prefix (each page links with request.script_root).
"""
import importlib.util, json, os, sys
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
    return render_template("selector.html", corpora=CORPORA, compare=os.path.exists(os.path.join(HERE, "data", "synkrisis.db")))


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


REGISTRY = json.load(open(os.path.join(HERE, "series.json"), encoding="utf-8"))["series"]
for s in REGISTRY:
    if os.path.exists(os.path.join(HERE, "data", s["db"])):
        n_s, n_p, yrs, n = stats(s["db"], "select min(year), max(year) from census", None)
        CORPORA[s["key"]] = {"name": s["name"], "short": s["short"], "url": s["url"], "sessions": n_s, "people": n_p, "years": yrs, "conferences": n,
                             "blurb": s["blurb"], "caveat": s["caveat"]}
CORPORA = list(CORPORA.values())

mounts = {}
for key in [s["key"] for s in REGISTRY] + ["compare"]:
    p = os.path.join(HERE, key, "app.py")
    if os.path.exists(p):
        mounts["/" + key] = load(key)
application = DispatcherMiddleware(selector, mounts)
# APP_PREFIX puts the whole site under a path, e.g. /repository/professional/conferences (see DEPLOY.md)
PREFIX = os.environ.get("APP_PREFIX", "").rstrip("/")
if PREFIX:
    application = DispatcherMiddleware(lambda env, start: (start("404 Not Found", [("Content-Type", "text/plain")]), [b"Not found"])[1], {PREFIX: application})
