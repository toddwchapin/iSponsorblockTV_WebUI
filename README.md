# iSponsorBlockTV WebUI

A small browser-based configuration UI for
[iSponsorBlockTV](https://github.com/dmunozv04/iSponsorBlockTV) so you can
edit `config.json`, pair a YouTube TV device, and manage the channel
whitelist without SSHing into the Raspberry Pi.

Tracking design and progress in [issue #1](../../issues/1).

## Features (v1)

- Edit every field of `config.json` (devices, skip categories, ads, API key,
  proxy, etc.) and save.
- Pair YouTube TV devices with a 12-digit code from the TV's
  *Settings → Link with TV code*.
- Search and add channels to the whitelist using the YouTube Data API.
- Detects how iSponsorBlockTV is running (Docker container, systemd user
  unit, or system unit via passwordless `sudo`) and restarts it after a
  config save.

Out of scope for v1: LAN auto-discovery during pairing, log viewer,
authentication. Use `iSponsorBlockTV --setup` on the Pi if you need LAN scan.

## Install on a Raspberry Pi

```bash
git clone https://github.com/toddwchapin/iSponsorblockTV_WebUI.git
cd iSponsorblockTV_WebUI
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run it directly:

```bash
isponsorblocktv-webui
# Opens on http://0.0.0.0:8080
```

The UI reads and writes the same `config.json` iSponsorBlockTV uses (default
`~/.config/iSponsorBlockTV/config.json`). Override with `WEBUI_DATA_DIR=/path`.

## Run as a systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp systemd/isponsorblocktv-webui.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now isponsorblocktv-webui
```

(Run `loginctl enable-linger $USER` once if you want it to start at boot
without you logged in.)

## Restarting the service after a config save

The WebUI tries the following, in order:

1. **Docker:** `docker restart iSponsorBlockTV` if `/var/run/docker.sock`
   exists and a container with that name is running.
2. **Systemd user unit:** `systemctl --user restart iSponsorBlockTV` if such
   a unit is active.
3. **System unit via sudo:** `sudo -n systemctl restart iSponsorBlockTV`.
   Requires a NOPASSWD sudoers entry. Example, scoped to one command only:

   ```
   # /etc/sudoers.d/isponsorblocktv-webui
   pi ALL=(root) NOPASSWD: /bin/systemctl restart iSponsorBlockTV
   ```

If none of the above succeed, the UI shows a toast asking you to restart
manually.

Override the unit/container name with `WEBUI_SERVICE_NAME=...`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `WEBUI_HOST` | `0.0.0.0` | Bind address |
| `WEBUI_PORT` | `8080` | Bind port |
| `WEBUI_DATA_DIR` | `~/.config/iSponsorBlockTV` | Where `config.json` lives |
| `WEBUI_SERVICE_NAME` | `iSponsorBlockTV` | Docker container / systemd unit name |
| `WEBUI_NO_RESTART` | unset | Set `1` to disable the restart subprocess (dev/tests) |

## Security notes

- This is a single-admin, LAN-only tool. No authentication, no CSRF token.
  Bind to `127.0.0.1` and put it behind a reverse proxy if your network
  is not trusted.
- The YouTube API key is masked in the form but stored in plaintext in
  `config.json` (this is what upstream does too).
- If you use the sudoers route, scope the rule to *only* the
  `systemctl restart iSponsorBlockTV` command — never give blanket sudo.

## Development

```bash
pip install -e '.[dev]'
WEBUI_NO_RESTART=1 pytest
WEBUI_NO_RESTART=1 WEBUI_DATA_DIR=/tmp/webui-dev uvicorn app.main:app --reload
```
