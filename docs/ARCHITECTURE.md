# Architecture

A short tour of how the WebUI is wired together. Read alongside the source —
file paths in this doc are clickable in most editors.

## Stack

- **FastAPI** for routing + DI (`app/main.py`).
- **Jinja2** templates with a single `base.html` and per-page extends.
- **HTMX** for partial swaps (status badge, toast, channel rows, log tail).
- **Pico CSS** as the base style layer; a thin design-token bridge on top.

No JS bundler, no client-side framework, no build step.

## App layout

```
app/
├── main.py              # FastAPI app, /static mount, /healthz, favicon
├── settings.py          # env-var reads (HOST, PORT, DATA_DIR, SERVICE_NAME)
├── routes/
│   ├── config.py        # GET / (config form), POST /save
│   ├── pair.py          # GET /pair, POST /pair/code
│   ├── channels.py      # GET /channels, POST /channels/apikey, /search, /add, DELETE
│   └── status.py        # GET /status (JSON), /status/badge (HTML), /logs, /logs/tail
├── services/
│   ├── config_io.py     # load/save config.json (atomic write)
│   ├── pairing.py       # YouTube TV pairing protocol
│   ├── channels.py      # YouTube Data API v3 channel search
│   ├── service_status.py# detection + log tail
│   └── restart.py       # docker / systemd restart
├── templates/
│   ├── base.html        # sticky header, tab bar, footer slot, toast container
│   ├── config.html      # main form (extends base, fills footer block)
│   ├── pair.html, channels.html, logs.html
│   └── partials/        # HTMX swap targets
└── assets/
    ├── favicon.svg
    └── static/          # mounted at /static
        ├── app.css      # design tokens + layout + a11y
        ├── app.js       # status-badge a11y announcer
        ├── config.js    # save/start button state machine
        └── bricolage-grotesque-var.woff2
```

## Service detection

`app/services/service_status.py` and `app/services/restart.py` share the
same chain. They check (in order):

1. **Docker** — `/var/run/docker.sock` exists, `docker` is on PATH, and
   `docker ps --filter name=^$NAME$` matches. A stopped container with
   the right name still anchors detection (`docker_inspect_exists`) so
   Stopped is a real state, not Unknown.
2. **Systemd user** — `systemctl --user is-active $NAME` returns any
   string (`active` / `inactive` / `failed` / etc.).
3. **Systemd system** — only attempted if `sudo -n true` succeeds. Then
   `sudo -n systemctl is-active $NAME`.

If all three return nothing, status is `Status("none", False, ...)` —
shown as **Unknown** (grey) in the UI.

`status()` returns a dataclass:

```python
@dataclass
class Status:
    method: str   # "docker" | "systemd-user" | "systemd-system" | "none"
    running: bool
    detail: str
```

Both `/status` (JSON for programmatic callers) and `/status/badge` (HTML
fragment for the header poll) call `status()`. The badge polls every 5s
via `hx-trigger="every 5s"`.

`tail_logs(n)` is the same chain for log reading — `docker logs --tail`,
then `journalctl --user`, then `sudo -n journalctl`.

## Templates and partials

`base.html` defines:

- A sticky header with app title, status badge (HTMX-polled), and tab nav
  (`aria-current="page"` on the active tab).
- A `{% block content %}` for the page body.
- A `{% block footer %}` rendered as a fixed-bottom action bar (used by
  `config.html` for the Save/Start button).
- A toast container with `role="status" aria-live="polite"` — HTMX
  `hx-swap-oob` replaces it on every action.
- A hidden `#status-announcer` `aria-live` region updated by `app.js` only
  when the badge text changes.

Partials in `templates/partials/`:

| Partial | Used by |
|---------|---------|
| `status_badge.html` | header poll, OOB swap from `/save` |
| `toast.html` | OOB swap from save / API-key / pair / add / remove |
| `device_row.html` | config form devices list |
| `channel_row.html` | `/channels` whitelist list |
| `channel_search_results.html` | `/channels/search` HTMX response |
| `paired_device.html` | `/pair/code` success response |
| `logs_tail.html` | `/logs` page + `/logs/tail` polled refresh |

## Static assets and `/static`

`app/main.py:30` mounts `app/assets/static/` at `/static` via FastAPI's
`StaticFiles`. The `pyproject.toml` package-data globs include
`assets/static/*` so wheel installs ship the CSS/JS/font.

`app.css` is a single layer that:

- Defines a design-token system (terracotta accent ramp `--accent-50..-900`
  anchored at `#dc6d4a`, status palette, type/spacing/motion scales,
  toast surfaces with light/dark variants).
- Bridges Pico's tokens (font, radii, focus ring) so theme switches keep
  working.
- Declares `@font-face` for Bricolage Grotesque variable (woff2, latin
  subset, 77 KB), preloaded from `base.html`. `font-display: swap`.
- Lays out the sticky chrome: `.app-header__inner` and `.action-bar__inner`
  cap the inner content at the layout max-width while the bands span the
  full viewport.
- Provides `:focus-visible` ring, `prefers-reduced-motion` motion guard,
  `.help` / `.caption` / `.badge` utility classes.

`app.js` listens to `htmx:afterSwap` for the status badge target and
copies the new badge text into `#status-announcer` only on transitions —
this avoids spamming a screen reader on every 5s no-op poll.

`config.js` runs the save/start button state machine: dirty tracking on
first `input`/`change`, busy state during POST, `pollStatusUntilSettled()`
after restart, `pollHealthzUntilBack()` for service comebacks.

## Pairing flow

`POST /pair/code` calls `pairing.pair_with_code()` which talks to the
YouTube TV pairing endpoint, then writes the new device into
`config.json` via `config_io.save()`. The frontend auto-hyphenates the
12-digit code as the user types; backend strips hyphens/spaces.

## Channel whitelist

The YouTube Data API key + `use_proxy` toggle are managed on `/channels`
(not on the main `/` config form — that decoupling landed in PR #26).
`POST /channels/apikey` saves the key and proxy flag; the search input is
hidden until a key is present. `/channels/search` proxies the YouTube
Data API v3 channel search; `POST /channels/add` and `DELETE
/channels/{id}` mutate the whitelist and return HTMX-swappable fragments.

## Error handling

The convention is "fail soft into a toast." Restart/log errors do not
500 — they return an explanatory message via the toast or fall back to a
"no log source available" notice. This keeps the UI usable in environments
where no detection method is available (e.g. dev laptop without Docker
or systemd).

## Tests

`tests/test_routes.py` is the bulk of the suite — exercises every route,
asserts on rendered HTML, monkeypatches `service_status.status()` and
`restart.restart()` so tests don't shell out. `WEBUI_NO_RESTART=1` is the
canonical env var for disabling the restart subprocess in dev/test.
