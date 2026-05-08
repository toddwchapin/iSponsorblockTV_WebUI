# Run as a systemd service

The shipped unit is a **system** service — it works whether or not anyone is
logged in, and it works on DietPi-as-root (where user-scope systemd does not).

## Install

1. Confirm the pipx shim exists for the account that ran `pipx install`:

   ```bash
   ls -l ~/.local/bin/isponsorblocktv-webui
   ```

2. Edit the unit file inside the cloned repo. Its full path is:

   ```
   ~/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service
   ```

   (If you cloned somewhere else, substitute that path throughout this doc.
   For a `root` install where you cloned to `/root/iSponsorblockTV_WebUI`,
   the path is
   `/root/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service`.)

   Two lines reference the account that owns the pipx install — both must
   be updated:

   ```ini
   User=REPLACE_ME
   ExecStart=/home/REPLACE_ME/.local/bin/isponsorblocktv-webui
   ```

   Replace `REPLACE_ME` with that username. The substitution differs
   slightly between regular accounts and `root` because `root`'s home is
   `/root`, not `/home/root`:

   | Account | `User=` | `ExecStart=` |
   |---------|---------|--------------|
   | `pi` | `User=pi` | `ExecStart=/home/pi/.local/bin/isponsorblocktv-webui` |
   | `dietpi` | `User=dietpi` | `ExecStart=/home/dietpi/.local/bin/isponsorblocktv-webui` |
   | `root` | `User=root` | `ExecStart=/root/.local/bin/isponsorblocktv-webui` |

   One-shot edits — pick the line that matches your account:

   ```bash
   # Regular user (replace 'pi' with your account if different)
   sed -i 's|REPLACE_ME|pi|g' \
       ~/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service

   # Root (note the second sed rewrites /home/root → /root)
   sudo sed -i -e 's|REPLACE_ME|root|g' \
               -e 's|/home/root/|/root/|' \
               /root/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service
   ```

   Verify before installing:

   ```bash
   grep -E '^(User|ExecStart)=' \
       ~/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service
   # Expected (pi):
   #   User=pi
   #   ExecStart=/home/pi/.local/bin/isponsorblocktv-webui
   ```

3. Install the unit:

   ```bash
   sudo cp ~/iSponsorblockTV_WebUI/systemd/isponsorblocktv-webui.service \
           /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now isponsorblocktv-webui
   ```

   For a `root` install, replace `~/iSponsorblockTV_WebUI` with
   `/root/iSponsorblockTV_WebUI` in the `cp` source path above.

4. Verify:

   ```bash
   systemctl status isponsorblocktv-webui
   journalctl -u isponsorblocktv-webui -n 50
   curl -s http://localhost:8099/healthz   # {"status":"ok","version":"..."}
   ```

## DietPi note

DietPi often runs as `root`. That works fine with this **system** unit:
install with `sudo pipx install ~/iSponsorblockTV_WebUI` (or run `pipx
install` while logged in as root) and use
`/root/.local/bin/isponsorblocktv-webui` for `ExecStart`.

## Set the password (`WEBUI_PASSWORD`)

The WebUI is single-admin and sits on the network — set a password before
exposing the port. If `WEBUI_PASSWORD` is unset the service starts with
`WARNING: WEBUI_PASSWORD not set — UI is open …` in the journal and
serves unauthenticated (kept for backwards-compat with v1 installs).

Pick **one** of the recipes below.

### EnvironmentFile (recommended)

Keeps the password out of the unit and lets you `chmod 600` it:

```bash
sudo install -d -m 700 -o root -g root /etc/iSponsorBlockTV
sudo install -m 600 -o root -g root /dev/null /etc/iSponsorBlockTV/webui.env
echo 'WEBUI_PASSWORD=hunter2' | sudo tee /etc/iSponsorBlockTV/webui.env >/dev/null
```

Then add a single line to `/etc/systemd/system/isponsorblocktv-webui.service`
under `[Service]`:

```ini
EnvironmentFile=/etc/iSponsorBlockTV/webui.env
```

`sudo systemctl daemon-reload && sudo systemctl restart isponsorblocktv-webui`,
then check `journalctl -u isponsorblocktv-webui -n 5` — the warning should
be gone.

### Inline `Environment=` (simpler, but the password is world-readable in the unit)

```ini
[Service]
Environment=WEBUI_PASSWORD=hunter2
```

Only do this if `/etc/systemd/system/` is already chmod 700 on your host.

### Rotation

Edit the env file (or unit), `daemon-reload`, restart. Existing browser
sessions stay valid until the cookie expiry (default 7 days, or
`WEBUI_SESSION_TTL` seconds).

### Forgot the password

There is no reset flow. Edit the env file, restart, log in.

## Sudoers

If iSponsorBlockTV runs as a *system* unit (not a Docker container, not a
user unit), the WebUI needs passwordless sudo to restart it and to read
its log. Scope tightly — never grant blanket sudo.

```
# /etc/sudoers.d/isponsorblocktv-webui
pi ALL=(root) NOPASSWD: /bin/systemctl restart iSponsorBlockTV
pi ALL=(root) NOPASSWD: /bin/journalctl -u iSponsorBlockTV *
```

Replace `pi` with the account that runs `isponsorblocktv-webui`. Without
the second line, `/logs` falls back to a friendly "no log source available"
notice instead of 500'ing.

Validate the file with `visudo -cf /etc/sudoers.d/isponsorblocktv-webui`
before reloading.

## Override the unit name

If iSponsorBlockTV is installed under a different name, set
`WEBUI_SERVICE_NAME=...` (in the unit's `Environment=` line, in your shell,
or in a drop-in).

## Uninstall

Run as the same user that did `pipx install`. Order matters: stop the
service first, remove the package, then the repo. The iSponsorBlockTV
`config.json` is left untouched.

1. Stop and disable (skip if you never installed the unit):

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

4. (Optional) Remove the sudoers rule:

   ```bash
   sudo rm /etc/sudoers.d/isponsorblocktv-webui
   ```

5. (Optional) Delete the iSponsorBlockTV config itself. **This deletes
   paired devices and the YouTube API key — only do this if you're also
   removing iSponsorBlockTV.**

   ```bash
   rm -rf ~/.config/iSponsorBlockTV
   ```
