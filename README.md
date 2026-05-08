# iSponsorBlockTV WebUI

A small browser-based configuration UI for
[iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV) — edit
`config.json`, pair YouTube TV devices, and manage the channel whitelist
without SSHing into the Pi. Skip data is sourced from the
[SponsorBlock API](https://sponsor.ajay.app); see the
[Category Explanations](https://github.com/toddwchapin/iSponsorblockTV_WebUI/wiki/Category-Explanations)
wiki page for what each skip category covers.

[![healthz](https://img.shields.io/badge/healthz-/healthz-blue)](#run)
LAN-only. Single-admin. No auth.

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
isponsorblocktv-webui              # serves on http://0.0.0.0:8099
```

The UI reads and writes the same `config.json` iSponsorBlockTV uses
(default `~/.config/iSponsorBlockTV/config.json`).

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

Verify:

```bash
isponsorblocktv-webui --version
curl -s http://localhost:8099/healthz
```

## Configuration

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEBUI_HOST` | `0.0.0.0` | Bind address |
| `WEBUI_PORT` | `8099` | Bind port |
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

- Single-admin, LAN-only. No authentication, no CSRF token. Bind to
  `127.0.0.1` and front with a reverse proxy on untrusted networks.
- The YouTube Data API key is masked in the form but stored in plaintext
  in `config.json` (matches upstream).
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
