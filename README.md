# iSponsorBlockTV WebUI

A small browser-based configuration UI for
[iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV) — edit
`config.json`, pair YouTube TV devices, and manage the channel whitelist
without SSHing into the Pi. Skip data is sourced from the
[SponsorBlock API](https://sponsor.ajay.app); see the
[Category Explanations](https://github.com/toddwchapin/iSponsorblockTV_WebUI/wiki/Category-Explanations)
wiki page for what each skip category covers.

[![healthz](https://img.shields.io/badge/healthz-/healthz-blue)](#run)
Single-admin. Password-gated session auth (`WEBUI_PASSWORD`). Defaults to
binding `127.0.0.1`.

## Pages

| Path | Purpose |
|------|---------|
| `/` | Edit `config.json`: skip categories, ad muting, devices, join name |
| `/pair` | Pair a TV via 12-digit code (auto-hyphenates as you type) |
| `/channels` | Manage the channel whitelist; save the YouTube Data API key + proxy toggle |
| `/logs` | Live tail of the iSponsorBlockTV service log (auto-refreshes every 5s) |
| `/healthz` | JSON liveness/version probe |
| `/status` | JSON service status (method, running, detail) |
| `/status/badge` | HTML fragment used by the header status badge |

## Features

- Sticky header + tab bar; fixed-bottom **Save and restart** button that
  enables only when the form is dirty. When the service is detected as
  stopped, the same button switches to **Start service**.
- Live status badge in the header — Running / Stopped / Unknown — with a
  hidden `aria-live` region announcing transitions.
- Toast notifications for save / restart / API-key actions, with
  `role="status"` and `aria-live="polite"`.
- Light and dark themes follow the OS preference (Pico CSS tokens).
- Self-hosted [Bricolage Grotesque](https://fonts.google.com/specimen/Bricolage+Grotesque)
  variable font (latin subset, ~77 KB woff2) — no third-party CDN.
- Service detection: Docker container → `systemctl --user` → `sudo
  systemctl` (passwordless, scoped sudoers rule).

## Quick start

`pipx` keeps the command on PATH and isolated from system Python.

```bash
sudo apt install -y pipx git
pipx ensurepath
git clone https://github.com/toddwchapin/iSponsorblockTV_WebUI.git ~/iSponsorblockTV_WebUI
pipx install ~/iSponsorblockTV_WebUI
```

Open a new shell so `~/.local/bin` is on PATH, then:

```bash
isponsorblocktv-webui --version    # e.g. "isponsorblocktv-webui 0.2.0"
WEBUI_PASSWORD=hunter2 isponsorblocktv-webui   # serves on http://127.0.0.1:8099
```

The UI reads and writes the same `config.json` iSponsorBlockTV uses
(default `~/.config/iSponsorBlockTV/config.json`).

> **`WEBUI_PASSWORD` is required for production.** If unset, the service
> starts with a warning and serves unauthenticated (kept for v1
> backwards-compat). For LAN access set `WEBUI_HOST=0.0.0.0` *and*
> `WEBUI_PASSWORD`. For systemd-managed installs see
> [docs/SYSTEMD.md → Set the password](docs/SYSTEMD.md#set-the-password-webui_password).

To run it as a system service so it survives reboots, see
[**docs/SYSTEMD.md**](docs/SYSTEMD.md).

## Update

`git pull` does not update the pipx venv. Always reinstall after a pull:

```bash
cd ~/iSponsorblockTV_WebUI
git pull
pipx install --force ~/iSponsorblockTV_WebUI
sudo systemctl restart isponsorblocktv-webui   # if installed as a service
```

> **Upgrading from a pre-auth release?** Set `WEBUI_PASSWORD` *before*
> restarting — otherwise the WebUI runs without auth and emits
> `WARNING: WEBUI_PASSWORD not set` in the journal. The default bind also
> changes from `0.0.0.0` to `127.0.0.1`; if you reach the UI from another
> host on the LAN, set `WEBUI_HOST=0.0.0.0` (and a password) explicitly.
> See [Security notes](#security-notes) for the threat model.

Verify:

```bash
isponsorblocktv-webui --version
curl -s http://localhost:8099/healthz
```

## Configuration

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEBUI_HOST` | `127.0.0.1` | Bind address. Set to `0.0.0.0` for LAN access (combine with `WEBUI_PASSWORD`). |
| `WEBUI_PORT` | `8099` | Bind port |
| `WEBUI_PASSWORD` | unset | Single shared password. Unset = open + startup warning. |
| `WEBUI_SESSION_TTL` | `604800` | Session cookie max-age in seconds (default 7 days). |
| `WEBUI_SESSION_SECRET` | random per-process | Signing key for the session cookie. Set to a stable random string to keep sessions valid across restarts. |
| `WEBUI_DATA_DIR` | `~/.config/iSponsorBlockTV` | Where `config.json` lives |
| `WEBUI_SERVICE_NAME` | `iSponsorBlockTV` | Docker container / systemd unit name |
| `WEBUI_NO_RESTART` | unset | Set `1` to disable the restart subprocess (dev/tests) |

## Service detection & restart

The same chain drives the status badge, log tail, and the save+restart action:

1. **Docker** — `docker restart $WEBUI_SERVICE_NAME` if `/var/run/docker.sock`
   exists and a container with that name is present.
2. **Systemd user unit** — `systemctl --user restart $WEBUI_SERVICE_NAME`
   if the user unit is known to systemd.
3. **Systemd system unit (sudo)** — `sudo -n systemctl restart
   $WEBUI_SERVICE_NAME`. Requires a NOPASSWD sudoers entry. Logs require a
   second NOPASSWD line for `journalctl`. See
   [**docs/SYSTEMD.md**](docs/SYSTEMD.md#sudoers) for the exact rules.

If none succeed, the UI shows a toast asking you to restart manually.

## Security notes

### Threat model

The WebUI is a single-admin tool. It assumes one trusted operator and
treats anyone else who can reach the port as hostile. The defaults aim
for a typical home LAN (one admin, several family members on the same
Wi-Fi, no segmentation): bind to `127.0.0.1`, require a password before
serving anything stateful, CSRF-protect every write.

What it does **not** defend against:

- Multi-admin / multi-tenant use — there is one shared password and no
  per-user auth.
- A compromised host — anyone with shell access can read
  `config.json`, the session secret, and the password env var.
- Replay of a stolen session cookie within its TTL. Mitigation: set a
  short `WEBUI_SESSION_TTL` (e.g. `3600`) on shared networks.

### What's enforced

- **Password gate.** `WEBUI_PASSWORD` (single shared secret). When unset
  the service still starts but logs `WARNING: WEBUI_PASSWORD not set …`
  and serves unauthenticated — preserved for v1 deployments that haven't
  rotated yet, but **set the password as soon as you can.**
- **Signed-cookie sessions** via Starlette's `SessionMiddleware`. Cookie
  is `HttpOnly`, `SameSite=Lax`. Default TTL 7 days
  (`WEBUI_SESSION_TTL`).
- **CSRF on every write.** The login form, all `POST /save`,
  `POST /pair/*`, `POST /channels/*`, and `DELETE /channels/{id}` require
  an `X-CSRF-Token` header (htmx; injected automatically by a global
  `htmx:configRequest` listener) or a hidden `_csrf` form field. Token
  is per-session and stored only in the session cookie.
- **Bind defaults to `127.0.0.1`.** LAN access is opt-in via
  `WEBUI_HOST=0.0.0.0`. The reverse-proxy recipe below is the
  recommended path for exposing the UI off-host.
- **Logs don't leak secrets.** Uvicorn's access log is disabled (forms
  POST the YouTube API key in the body anyway, but belt-and-suspenders).
  The `apikey` field is masked in the rendered config form.
- **Open routes.** `/healthz`, `/favicon.*`, `/static/*`, `/login`,
  `/logout` only. Everything else (including `/logs`) requires auth.

### Reverse proxy (Caddy) — exposing on the LAN

If you want the UI reachable from another machine on the LAN, the
recommended path is to keep `WEBUI_HOST=127.0.0.1` and front the service
with a reverse proxy that adds TLS (and, optionally, a second auth
layer):

```caddyfile
# /etc/caddy/Caddyfile
isponsorblocktv.lan {
    reverse_proxy 127.0.0.1:8099
}
```

For nginx the equivalent is a `proxy_pass http://127.0.0.1:8099;` block
inside a `server { listen 443 ssl; … }` virtual host.

If you'd rather skip the proxy and bind directly:

```bash
WEBUI_HOST=0.0.0.0 WEBUI_PASSWORD=hunter2 isponsorblocktv-webui
```

You **must** set `WEBUI_PASSWORD` in this case — anything else is leaving
the front door open.

### Other notes

- The YouTube Data API key is masked in the form but stored in plaintext
  in `config.json` (matches upstream). Don't world-read your data dir.
- Scope sudoers rules tightly to `systemctl restart iSponsorBlockTV` and
  `journalctl -u iSponsorBlockTV *` — never blanket sudo.

## Development

```bash
pip install -e '.[dev]'
WEBUI_NO_RESTART=1 pytest
WEBUI_NO_RESTART=1 WEBUI_DATA_DIR=/tmp/webui-dev uvicorn app.main:app --reload
```

For architecture details (service detection internals, template + partial
layout, design-token system, `/static` mount, accessibility) see
[**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md). For dev workflow
guidance and how to add a page see [**CONTRIBUTING.md**](CONTRIBUTING.md).

## Uninstall

Stop the service, remove the package, then the repo. Your iSponsorBlockTV
`config.json` is left untouched. Full steps in
[docs/SYSTEMD.md → Uninstall](docs/SYSTEMD.md#uninstall).

## Dependencies

### Upstream service this UI configures

- [iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV) — the
  daemon that does the actual SponsorBlock skipping on YouTube TV.

### Runtime (Python)

Pinned in [`pyproject.toml`](pyproject.toml).

- [FastAPI](https://fastapi.tiangolo.com/) ([repo](https://github.com/fastapi/fastapi))
  — web framework + routing.
- [Uvicorn](https://www.uvicorn.org/) ([repo](https://github.com/encode/uvicorn))
  — ASGI server (`[standard]` extra for httptools + uvloop).
- [Jinja2](https://jinja.palletsprojects.com/) ([repo](https://github.com/pallets/jinja))
  — HTML templates.
- [python-multipart](https://github.com/Kludex/python-multipart) — form
  parsing for `POST /save`, `POST /channels/apikey`, `POST /pair/code`.
- [httpx](https://www.python-httpx.org/) ([repo](https://github.com/encode/httpx))
  — async HTTP client used by the YouTube pairing + Data API calls.
- [appdirs](https://github.com/ActiveState/appdirs) — locates the
  default `~/.config/iSponsorBlockTV/` data directory.

### Frontend (vendored or self-hosted)

- [Pico CSS](https://picocss.com/) ([repo](https://github.com/picocss/pico))
  — base style layer (loaded from jsDelivr in
  [`base.html`](app/templates/base.html)).
- [htmx](https://htmx.org/) ([repo](https://github.com/bigskysoftware/htmx))
  — partial swaps for status badge, toast, channel rows, log tail
  (loaded from unpkg).
- [Bricolage Grotesque](https://fonts.google.com/specimen/Bricolage+Grotesque)
  ([repo](https://github.com/ateliertriay/bricolage)) — variable display
  font, self-hosted at `/static/bricolage-grotesque-var.woff2` (latin
  subset, ~77 KB).

### Development

- [pytest](https://docs.pytest.org/) ([repo](https://github.com/pytest-dev/pytest))
  — test runner.
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) — async
  test support.
- [ruff](https://docs.astral.sh/ruff/) ([repo](https://github.com/astral-sh/ruff))
  — linter + formatter.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Tracking design and progress in
[issue #1](../../issues/1).

## License

MIT.
