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

Use `pipx` so the command is on PATH globally and isolated from system Python.

```bash
sudo apt install -y pipx git
pipx ensurepath        # adds ~/.local/bin to PATH; open a new shell after
git clone https://github.com/toddwchapin/iSponsorblockTV_WebUI.git ~/iSponsorblockTV_WebUI
pipx install ~/iSponsorblockTV_WebUI
```

Open a new shell (or `source ~/.bashrc`) so `~/.local/bin` is on PATH, then
confirm the install and run it:

```bash
isponsorblocktv-webui --version    # prints e.g. "isponsorblocktv-webui 0.2.0"
isponsorblocktv-webui              # serves on http://0.0.0.0:8099
```

The UI reads and writes the same `config.json` iSponsorBlockTV uses (default
`~/.config/iSponsorBlockTV/config.json`). Override with `WEBUI_DATA_DIR=/path`.

While running, `GET /healthz` returns `{"status":"ok","version":"..."}` —
useful for monitoring or for confirming which version is actually live.

## Update to the latest version

`git pull` only updates the source tree on disk. It does **not** touch the
pipx venv that holds the running binary, so the new code never reaches
the service. After every pull you must reinstall:

```bash
cd ~/iSponsorblockTV_WebUI
git pull
pipx install --force ~/iSponsorblockTV_WebUI
# If you have the systemd unit installed:
sudo systemctl restart isponsorblocktv-webui
```

Verify the version that's actually running:

```bash
isponsorblocktv-webui --version
# or, with the service running:
curl -s http://localhost:8099/healthz
```

If the version still looks old after `pipx install --force`, double-check
that you ran the command as the same user that did the original
`pipx install` (the venv lives under that user's home directory).

## Run as a systemd service

The shipped unit is a **system** service — it works whether or not anyone is
logged in, and it works on DietPi-as-root (where user-scope systemd doesn't).

1. Confirm the pipx shim exists for the account that ran `pipx install`:

   ```bash
   ls -l ~/.local/bin/isponsorblocktv-webui
   ```

2. Edit `systemd/isponsorblocktv-webui.service` and replace **both**
   occurrences of `REPLACE_ME` with that username (e.g. `dietpi`, `pi`, or
   `root`). For `root`, change the `ExecStart` path to
   `/root/.local/bin/isponsorblocktv-webui`.

3. Install the unit:

   ```bash
   cd ~/iSponsorblockTV_WebUI
   sudo cp systemd/isponsorblocktv-webui.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now isponsorblocktv-webui
   ```

4. Verify:

   ```bash
   systemctl status isponsorblocktv-webui
   journalctl -u isponsorblocktv-webui -n 50
   curl -s http://localhost:8099/healthz   # {"status":"ok","version":"..."}
   ```

### DietPi note

DietPi often runs as `root`. That works fine with this **system** unit:
install with `sudo pipx install ~/iSponsorblockTV_WebUI` (or run `pipx
install` while logged in as root) and use
`/root/.local/bin/isponsorblocktv-webui` for `ExecStart`.

## Uninstall

Run as the same user that did the `pipx install`. The order matters: stop
the service first, then remove the package, then the repo. Your
iSponsorBlockTV `config.json` is left untouched.

1. Stop and disable the service (skip if you never installed the unit):

   ```bash
   sudo systemctl disable --now isponsorblocktv-webui
   sudo rm /etc/systemd/system/isponsorblocktv-webui.service
   sudo systemctl daemon-reload
   ```

2. Remove the package and its venv:

   ```bash
   pipx uninstall isponsorblocktv-webui
   ```

   For a root install, run that with `sudo`.

3. Remove the cloned repo:

   ```bash
   rm -rf ~/iSponsorblockTV_WebUI
   ```

4. (Optional) Remove the sudoers rule, if you added one for the restart
   feature:

   ```bash
   sudo rm /etc/sudoers.d/isponsorblocktv-webui
   ```

5. (Optional) Delete the iSponsorBlockTV config itself. **This deletes the
   paired devices and your YouTube API key — only do this if you're also
   removing iSponsorBlockTV.**

   ```bash
   rm -rf ~/.config/iSponsorBlockTV
   ```

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
| `WEBUI_PORT` | `8099` | Bind port |
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
