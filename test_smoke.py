"""Smoke test: every page of all five readers answers, and every internal link carries its prefix.  python test_smoke.py"""
import re, sqlite3
from werkzeug.test import Client
import wsgi

c = Client(wsgi.application)
w = sqlite3.connect("data/cw.db")
cpid = w.execute("select person_id from person_summary where eligible=1 order by conventions desc limit 1").fetchone()[0]
t = sqlite3.connect("data/cptsc.db")
tpid = t.execute("select person_id from person_summary where eligible=1 order by conventions desc limit 1").fetchone()[0]
x = sqlite3.connect("data/ccw.db")
xpid = x.execute("select person_id from person_summary where eligible=1 order by conventions desc limit 1").fetchone()[0]
d = sqlite3.connect("data/iwac.db")
pid = d.execute("select person_id from person_summary where eligible=1 order by conventions desc limit 1").fetchone()[0]
paths = ["/", "/cccc/", "/cccc/tools", "/cccc/year/2005", "/cccc/atlas?year=2005", "/iwac/", "/iwac/tools", "/iwac/conventions", "/iwac/year/2025", "/iwac/institutions",
         "/iwac/areas", "/iwac/network", "/iwac/network?era=2012%E2%80%932016", "/iwac/formats", "/iwac/atlas?year=2025", "/iwac/trends?terms=transfer,assessment", "/iwac/corpus?q=assessment", "/iwac/search?q=writing", "/iwac/how-to-read", f"/iwac/person/{pid}",
         "/cw/", "/cw/tools", "/cw/conventions", "/cw/year/1998", "/cw/year/2015", "/cw/institutions", "/cw/network", "/cw/network?era=2000%E2%80%932009", "/cw/formats", "/cw/atlas",
         "/cw/trends?terms=hypertext,assessment", "/cw/corpus?q=hypertext", "/cw/search?q=writing", "/cw/how-to-read", "/cw/ethics", f"/cw/person/{cpid}",
         "/cptsc/", "/cptsc/tools", "/cptsc/conventions", "/cptsc/year/1997", "/cptsc/year/2015", "/cptsc/institutions", "/cptsc/network", "/cptsc/formats", "/cptsc/atlas",
         "/cptsc/trends?terms=assessment,usability", "/cptsc/corpus?q=assessment", "/cptsc/search?q=writing", "/cptsc/how-to-read", "/cptsc/ethics", f"/cptsc/person/{tpid}",
         "/ccw/", "/ccw/tools", "/ccw/conventions", "/ccw/year/2015", "/ccw/year/2023", "/ccw/year/2025", "/ccw/institutions", "/ccw/network", "/ccw/network?era=2015%E2%80%932019",
         "/ccw/formats", "/ccw/atlas", "/ccw/trends?terms=prison,literacy", "/ccw/corpus?q=prison", "/ccw/search?q=writing", "/ccw/how-to-read", "/ccw/ethics", f"/ccw/person/{xpid}"]
bad = 0
for p in paths:
    r = c.get(p)
    body = r.get_data(as_text=True)
    prefix = "/iwac" if p.startswith("/iwac") else "/cccc" if p.startswith("/cccc") else "/cptsc" if p.startswith("/cptsc") else "/ccw" if p.startswith("/ccw") else "/cw" if p.startswith("/cw") else ""
    off = [l for l in re.findall(r'(?:href|src|action)="(/[^"]*)"', body) if prefix and not (l.startswith(prefix) or l == "/")]
    if r.status_code != 200 or off:
        bad += 1
        print("FAIL", r.status_code, p, off[:3])
print("all passed" if not bad else f"{bad} failed")
