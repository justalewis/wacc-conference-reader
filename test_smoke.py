"""Smoke test: every page of both readers answers, and every internal link carries its prefix.  python test_smoke.py"""
import re, sqlite3
from werkzeug.test import Client
import wsgi

c = Client(wsgi.application)
d = sqlite3.connect("data/iwac.db")
pid = d.execute("select person_id from person_summary where eligible=1 order by conventions desc limit 1").fetchone()[0]
paths = ["/", "/cccc/", "/cccc/tools", "/cccc/year/2005", "/cccc/atlas?year=2005", "/iwac/", "/iwac/tools", "/iwac/conventions", "/iwac/year/2025", "/iwac/institutions",
         "/iwac/areas", "/iwac/network", "/iwac/network?era=2012%E2%80%932016", "/iwac/formats", "/iwac/atlas?year=2025", "/iwac/trends?terms=transfer,assessment", "/iwac/corpus?q=assessment", "/iwac/search?q=writing", "/iwac/how-to-read", f"/iwac/person/{pid}"]
bad = 0
for p in paths:
    r = c.get(p)
    body = r.get_data(as_text=True)
    prefix = "/iwac" if p.startswith("/iwac") else "/cccc" if p.startswith("/cccc") else ""
    off = [l for l in re.findall(r'(?:href|src|action)="(/[^"]*)"', body) if prefix and not (l.startswith(prefix) or l == "/")]
    if r.status_code != 200 or off:
        bad += 1
        print("FAIL", r.status_code, p, off[:3])
print("all passed" if not bad else f"{bad} failed")
