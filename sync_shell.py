"""Copy the shared shell (shared/) into each reader and the landing page.  python sync_shell.py
shared/reader.css, figure.js and figure-head.js go to <reader>/static; _icons.html and _capsa.html go to
<reader>/templates. The landing page serves cccc/static, so it needs only its own icons partial."""
import os, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, "shared")
for r in ("cccc", "iwac", "cw", "cptsc", "ccw"):
    for f in ("reader.css", "figure.js", "figure-head.js"):
        shutil.copyfile(os.path.join(S, f), os.path.join(HERE, r, "static", f))
    for f in ("_icons.html", "_capsa.html"):
        shutil.copyfile(os.path.join(S, f), os.path.join(HERE, r, "templates", f))
shutil.copyfile(os.path.join(S, "_icons.html"), os.path.join(HERE, "selector", "templates", "_icons.html"))
# The comparator has its own capsa and templates; it takes the shared styles, scripts and icons, and the type and chart files from cccc.
C = os.path.join(HERE, "compare")
for f in ("reader.css", "figure.js", "figure-head.js"):
    shutil.copyfile(os.path.join(S, f), os.path.join(C, "static", f))
shutil.copyfile(os.path.join(S, "_icons.html"), os.path.join(C, "templates", "_icons.html"))
for f in ("tokens.css", "fonts.css", "chart.umd.min.js", "chart-defaults.js"):
    shutil.copyfile(os.path.join(HERE, "cccc", "static", f), os.path.join(C, "static", f))
shutil.copytree(os.path.join(HERE, "cccc", "static", "fonts"), os.path.join(C, "static", "fonts"), dirs_exist_ok=True)
print("synced")
