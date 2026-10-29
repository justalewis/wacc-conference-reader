# Deploying the conference archives reader

The site is one WSGI app (`wsgi:application`): a selector at `/`, the CCCC reader at `/cccc`, the IWAC reader at `/iwac`. It is Flask on waitress, reads two read-only SQLite files in `data/`, and needs no write access and no secrets. Every page sends `X-Robots-Tag: noindex, nofollow`; remove that header in `wsgi.py`, `cccc/app.py` and `iwac/app.py` if the Clearinghouse wants the pages indexed.

## Fly.io (interim host)

```bash
fly launch --no-deploy --copy-config --name wacc-conference-reader
fly deploy
```

`fly.toml` and `Dockerfile` are in this folder. The image copies `data/*.db` in, so rebuild and redeploy after any data change. Machines stop when idle (`min_machines_running = 0`), so the first request after a quiet spell takes a few seconds.

## IIS (the Clearinghouse's eventual host)

The Clearinghouse's pages live under `/repository/professional/conferences/`. Two ways to host the reader there:

1. **Reverse proxy (matches how Pinakes is hosted).** Run waitress as a Windows service on a local port and proxy a path or subdomain to it with IIS Application Request Routing and URL Rewrite. The service command, from the project folder:

   ```
   python -m waitress --listen=127.0.0.1:8080 wsgi:application
   ```

   Use NSSM or a scheduled task to keep it running. Set the environment variables below on the service.

2. **Under a path.** To serve the whole site below an existing path, set `APP_PREFIX=/repository/professional/conferences/archives` (any path) and proxy that path to the service **without stripping it**. All links in the selector and both readers are built from the mount path, so nothing else changes. If the proxy strips the path instead, leave `APP_PREFIX` unset and set the `SCRIPT_NAME` header to the path in the rewrite rule.

Sample `web.config` rule for option 2 (needs ARR with proxy enabled):

```xml
<rule name="conference-archives" stopProcessing="true">
  <match url="^repository/professional/conferences/archives(/.*)?$" />
  <action type="Rewrite" url="http://127.0.0.1:8080/repository/professional/conferences/archives{R:1}" />
</rule>
```

Checklist for the IIS move:

- Python 3.12 and `pip install -r requirements.txt` (flask, waitress).
- Copy `wsgi.py`, `selector/`, `cccc/`, `iwac/` and `data/`. Nothing else is needed at run time (`build_iwac.py` and `test_smoke.py` are build tools).
- Environment variables: `READER_CONTACT` (corrections address, default `jlewis2@olympic.edu`), `APP_PREFIX` (optional), `READER_URL` (the public base URL, used in citations).
- Static files are served by Flask from `cccc/static` and `iwac/static`. They can be served by IIS directly if preferred; the paths are `/static/...` under each mount.
- Health check: `GET /` returns 200.
- Add `Content-Security-Policy` and HSTS at the IIS level if the Clearinghouse's other sites send them; the pages use only inline scripts and same-origin assets.

## Rebuilding the data

`python build_iwac.py` rebuilds `data/iwac.db` from `../iwac-corpus/build/iwac.db`, which holds the parsed IWAC programs (not in this repository; the captured PDFs and WARC files are the Clearinghouse's material). `data/cccc.db` comes from the CCCC corpus build.
