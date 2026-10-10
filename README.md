# iSponsorBlockTV WebUI

A browser-based configuration UI for
[iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV). Edit
`config.json`, pair a TV using the code shown in YouTube, and manage the
channel whitelist from your browser. The upstream daemon does the skipping;
this project only manages its settings. Skip data comes from the
[SponsorBlock API](https://sponsor.ajay.app); see the
[Category Explanations](https://github.com/toddwchapin/iSponsorblockTV_WebUI/wiki/Category-Explanations)
wiki page for what each skip category covers.

Single-admin. Set `WEBUI_PASSWORD` to enable session authentication; the UI
binds to `127.0.0.1` by default.

## Pages

| Path | Purpose |
|------|---------|
| `/` | Edit `config.json`: skip categories, ad muting, devices, join name |
| `/pair` | Pair a TV via 12-digit code (auto-hyphenates as you type), or scan the LAN via SSDP/DIAL for nearby YouTube-capable TVs |
| `/channels` | Manage the channel whitelist; save the YouTube Data API key + proxy toggle |
| `/logs` | Live tail of the iSponsorBlockTV service log (auto-refreshes every 5s) |
| `/healthz` | JSON liveness/version probe |
| `/status` | JSON service status (method, running, detail) |
| `/status/badge` | HTML fragment used by the header status badge |

> **Docker and LAN scanning:** SSDP/DIAL discovery needs host networking on
> Linux (`--network host` or `network_mode: host` in Compose). The default
> bridge network won't reliably pass the multicast request and response.
> TV-code pairing works without host networking. On macOS, Docker host
> networking doesn't provide the same LAN multicast behavior as native Linux.

## Features

- Sticky header + tab bar; fixed-bottom **Save and restart** button that
  enables only when the form is dirty. When the service is detected as
  stopped, the same button switches to **Start service**.
- Live status badge in the header — Running / Stopped / Unknown — with a
  hidden `aria-live` region announcing transitions.
- Toast notifications for save, restart, and API-key actions, with
  `role="status"` and `aria-live="polite"`.
- Light and dark themes follow the OS preference (Pico CSS tokens).
- Self-hosted [Bricolage Grotesque](https://fonts.google.com/specimen/Bricolage+Grotesque)
  variable font (latin subset, ~77 KB woff2). CSS and htmx still load from CDNs.
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
isponsorblocktv-webui --version    # e.g. "isponsorblocktv-webui 0.3.0"
read -r -s -p 'WebUI password: ' WEBUI_PASSWORD; printf '\n'
export WEBUI_PASSWORD
isponsorblocktv-webui            # serves on http://127.0.0.1:8099
```

The UI reads and writes the same `config.json` iSponsorBlockTV uses
(default `~/.config/iSponsorBlockTV/config.json`).

> **Set `WEBUI_PASSWORD` before starting the UI.** Without it, the service
> warns and serves pages without authentication (for backwards compatibility).
> For LAN access set `WEBUI_HOST=0.0.0.0` *and*
> `WEBUI_PASSWORD`. For systemd-managed installs see
> [docs/SYSTEMD.md → Set the password](docs/SYSTEMD.md#set-the-password-webui_password).

To run it as a system service so it survives reboots, see
[**docs/SYSTEMD.md**](docs/SYSTEMD.md).

## Container deployment

Published releases use `ghcr.io/toddwchapin/isponsorblocktv-webui:0.3.0`
(use the new tag when upgrading). This image runs the WebUI, not the
iSponsorBlockTV daemon. Run the daemon separately and mount its data directory
into both containers. They must use the same `config.json`; otherwise your
changes won't reach the daemon. Example on Linux:

```yaml
services:
  webui:
    image: ghcr.io/toddwchapin/isponsorblocktv-webui:0.3.0
    network_mode: host # needed for SSDP LAN scanning on Linux
    environment:
      WEBUI_HOST: 0.0.0.0
      WEBUI_PASSWORD: ${WEBUI_PASSWORD:?Set WEBUI_PASSWORD in your environment}
      WEBUI_DATA_DIR: /data
    volumes:
      - ./data:/data # use the daemon's actual host data directory here
    restart: unless-stopped
```

Set `WEBUI_PASSWORD` in your shell or Compose environment before starting the
stack; don't put the password in this file. The UI listens on port 8099. On a
shared network, use a TLS reverse proxy; the built-in password does not
encrypt traffic.

To restart the daemon or show its Docker logs from the UI, the container also
needs the Docker socket. Mounting `/var/run/docker.sock` grants host-level
Docker control (even with a read-only bind); only do this if you accept that
risk. Without the socket, save the config in the UI and restart the daemon
yourself.

On macOS, use TV-code pairing if LAN scanning doesn't find your TV.

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

The WebUI is a single-admin tool. It assumes one trusted operator. By
default it binds to `127.0.0.1` and CSRF-protects writes, but it does **not**
enforce a password unless you set `WEBUI_PASSWORD`. Set one before exposing
the UI to your LAN.

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
- **Access logs are disabled.** Uvicorn does not log request URLs; forms
  POST the YouTube API key in the body.
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
WEBUI_HOST=0.0.0.0 isponsorblocktv-webui  # after exporting WEBUI_PASSWORD above
```

Set `WEBUI_PASSWORD` first. Binding to the LAN without it leaves the UI open.

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
- [ssdp](https://github.com/codingjoe/ssdp) — sends the SSDP M-SEARCH
  request used by `/pair`'s LAN auto-discovery.
- [xmltodict](https://github.com/martinblech/xmltodict) — parses the DIAL
  device-description and YouTube-app-state XML returned during LAN
  auto-discovery.

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
