# Contributing

Thanks for the interest. This is a small project — no contributor agreement,
no required ceremony. Open an issue to talk through anything non-trivial
before you start coding.

## Dev setup

```bash
git clone https://github.com/toddwchapin/iSponsorblockTV_WebUI.git
cd iSponsorblockTV_WebUI
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Run the test suite:

```bash
WEBUI_NO_RESTART=1 pytest
```

Run the app with auto-reload against a throwaway data dir:

```bash
WEBUI_NO_RESTART=1 \
WEBUI_DATA_DIR=/tmp/webui-dev \
uvicorn app.main:app --reload
```

`WEBUI_NO_RESTART=1` short-circuits the `docker restart` / `systemctl
restart` calls so saves don't try to touch a real service.

## Lint

```bash
ruff check .
ruff format .
```

## Code style

- Python: follow ruff. 100-col line length, py39+ syntax.
- Templates: 2-space indent. Keep partials small — one HTMX swap target
  per file under `app/templates/partials/`.
- CSS: design tokens live in `app/assets/static/app.css`. Don't add
  hard-coded hex/spacing values; reach for an existing token or define
  a new one.

## Adding a page

Wiring a new page involves four files:

1. **Route** — add an APIRouter under `app/routes/` and include it in
   `app/main.py` (`app.include_router(...)`). Pass `"active": "<key>"`
   in the template context for the tab highlight.
2. **Template** — extend `templates/base.html`, fill `{% block content %}`.
   If the page has a primary action that should sit at the bottom of the
   viewport, fill `{% block footer %}` with a `.action-bar` div.
3. **Tab entry** — add an `<a>` to the tab nav in `base.html` with the
   `aria-current` rule wired to the `active` key.
4. **Tests** — add a route test in `tests/test_routes.py`. Monkeypatch
   `service_status.status()` and `restart.restart()` if the page touches
   them so tests stay hermetic.

## Adding a partial

Partials live at `app/templates/partials/`. Convention: one HTMX swap
target per file. Render them via
`request.app.state.templates.TemplateResponse(request, "partials/foo.html", ctx)`
and target with `hx-target` / `hx-swap`. Use `hx-swap-oob="outerHTML"`
on the toast container so any route can pop a toast as a side effect.

## Architecture notes

For service detection, template + partial layout, design-token system,
`/static` mount, and accessibility internals, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tests are the spec

`tests/test_routes.py` is the canonical "does this still work" check.
Before opening a PR:

```bash
WEBUI_NO_RESTART=1 pytest
```

If you change a rendered string the tests assert on, update the test.
Don't relax assertions to make a change "fit" — that's a sign the test
was the actual contract.

## PRs

- Branch off `main`. One PR per logical change.
- Reference the issue number in the PR title (e.g. `(#15)`).
- The PR description should answer *why*; the diff already shows *what*.
