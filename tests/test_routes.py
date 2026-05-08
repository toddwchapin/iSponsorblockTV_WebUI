"""Smoke tests for HTTP routes via FastAPI TestClient."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBUI_NO_RESTART", "1")
    # Clear cached settings if any module-level cached the dir
    import importlib

    from app import settings as settings_mod
    importlib.reload(settings_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    return main_mod.app, tmp_path


def test_healthz_reports_version(app_with_tmp_config) -> None:
    """Users debug stale-install issues with `curl /healthz`. Don't break it."""
    from app import __version__

    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "version": __version__}


def test_favicon_svg_served(app_with_tmp_config) -> None:
    """Issue #18: /favicon.svg returns the bundled icon."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in r.content


def test_favicon_ico_served_as_svg(app_with_tmp_config) -> None:
    """Issue #18: legacy /favicon.ico probe gets the same SVG, not 404."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert b"<svg" in r.content


def test_apple_touch_icon_returns_204(app_with_tmp_config) -> None:
    """Issue #18: iOS apple-touch-icon probes get 204, not 404."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        r = client.get(path)
        assert r.status_code == 204, path
        assert r.content == b""


def test_index_links_favicon(app_with_tmp_config) -> None:
    """Issue #18: base.html declares the SVG favicon so browsers stop
    probing /favicon.ico in the first place."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'rel="icon"' in r.text
    assert '/favicon.svg' in r.text


def test_static_mount_serves_app_css(app_with_tmp_config) -> None:
    """Issue #25: app.css and the bundled woff2 must be reachable.

    Replaces the old "no static mount" test (issue #9 regression). The mount
    is safe now because real files ship in app/assets/static/ — the original
    bug was an empty dir packaged via a glob that matched nothing.
    """
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/static/app.css")
    assert r.status_code == 200
    assert "iSponsorBlockTV WebUI" in r.text  # token-block header comment


def test_index_renders_with_no_existing_config(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Configuration" in r.text
    assert "Skip Categories" in r.text  # round 4 item 7: container label
    assert "Settings" in r.text  # round 4 item 2: renamed from "Ads"


def test_save_persists_config(app_with_tmp_config) -> None:
    """The /save form covers devices + sponsorblock/ads/playback. apikey and
    use_proxy are managed via /channels (issue #25 IA cleanup) and must be
    preserved across saves that don't touch them."""
    app, tmp = app_with_tmp_config
    # Pre-seed apikey on disk so we can verify /save preserves it.
    (tmp / "config.json").write_text(
        json.dumps({"apikey": "preserved-key", "use_proxy": True})
    )
    client = TestClient(app)
    r = client.post(
        "/save",
        data={
            "device_name": "Living",
            "device_screen_id": "screen-xyz",
            "device_offset": "100",
            "skip_categories": ["sponsor", "selfpromo"],
            "minimum_skip_length": "2",
            "skip_count_tracking": "on",
            "mute_ads": "on",
            "auto_play": "on",
            "join_name": "iSponsorBlockTV",
        },
    )
    assert r.status_code == 200
    assert "Saved" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["apikey"] == "preserved-key"
    assert on_disk["use_proxy"] is True
    assert on_disk["devices"] == [
        {"screen_id": "screen-xyz", "name": "Living", "offset": 100}
    ]
    assert on_disk["mute_ads"] is True
    assert on_disk["skip_ads"] is False
    assert "selfpromo" in on_disk["skip_categories"]


def test_channels_apikey_save(app_with_tmp_config) -> None:
    """Issue #25 IA: API key now lives on /channels with its own endpoint."""
    app, tmp = app_with_tmp_config
    client = TestClient(app)
    r = client.post("/channels/apikey", data={"apikey": "AIzaSetByMe", "use_proxy": "on"})
    assert r.status_code == 200
    assert "API key saved" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["apikey"] == "AIzaSetByMe"
    assert on_disk["use_proxy"] is True

    r = client.post("/channels/apikey", data={"apikey": ""})
    assert r.status_code == 200
    assert "API key cleared" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["apikey"] == ""
    assert on_disk["use_proxy"] is False


def test_save_writes_to_settings_config_path(app_with_tmp_config) -> None:
    """Issue #15 comment B: /save writes the file iSponsorBlockTV reads."""
    from app import settings

    app, tmp = app_with_tmp_config
    assert settings.config_path() == tmp / "config.json"
    client = TestClient(app)
    r = client.post("/save", data={"device_screen_id": "x"})
    assert r.status_code == 200
    assert settings.config_path().exists()


def test_index_reads_existing_config(app_with_tmp_config) -> None:
    """Issue #15 comment D: GET / reflects what's on disk at config_path().
    apikey moved to /channels in issue #25, so verify it there."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps(
            {
                "apikey": "PRELOADED_KEY_123",
                "devices": [{"screen_id": "scr-pre", "name": "Pre", "offset": 42}],
                "mute_ads": True,
            }
        )
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "scr-pre" in r.text
    # apikey lives on /channels now.
    r2 = client.get("/channels")
    assert r2.status_code == 200
    assert "key is currently saved" in r2.text


def test_blank_device_row_route_removed(app_with_tmp_config) -> None:
    """The /devices/blank-row endpoint is gone — manual screen-id paste was
    replaced by a link to /pair on the config page."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/devices/blank-row")
    assert r.status_code == 404


def test_screen_id_hidden_in_form(app_with_tmp_config) -> None:
    """Screen ID is opaque and meaningless to humans. It is never rendered
    visibly on the config page — only in a hidden input so POST /save can
    round-trip it."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps({"devices": [{"screen_id": "scr-x", "name": "TV", "offset": 0}]})
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    # Hidden input present so save round-trips.
    assert '<input type="hidden" name="device_screen_id" value="scr-x"' in body
    # No visible Screen ID column header or cell.
    assert "<th>Screen ID</th>" not in body
    assert 'class="device-screen-id"' not in body
    # No readonly attr anywhere on the form (hidden inputs don't take it).
    assert "readonly" not in body
    # "+ Pair a new device" link replaces the old "+ Add device" button.
    assert 'href="/pair"' in body
    assert "+ Pair a new device" in body


def test_config_page_uses_two_column_grid(app_with_tmp_config) -> None:
    """Round 2 had three articles (SponsorBlock left, Ads top + Playback bottom).
    Round 4 collapsed Ads + Playback into a single 'Other settings' article, so
    the grid is now a simple two-column layout."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert 'class="config-grid"' in r.text
    assert 'class="grid-left"' in r.text
    assert 'class="grid-right"' in r.text


def test_round4_form_structure(app_with_tmp_config) -> None:
    """Round 4 items 2/3/6/7/8/9: Skip Categories left (2-col grid), Other
    settings right with checkboxes + min-skip dropdown + join name in order;
    devices caption removed; old SponsorBlock/Ads/Playback labels gone."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    body = r.text

    # 7: container labels (round 5 renamed "Other settings" -> "Settings").
    assert ">Skip Categories<" in body
    assert ">Settings<" in body
    # Old labels are gone.
    assert ">SponsorBlock<" not in body
    assert ">Ads<" not in body
    assert ">Playback<" not in body
    assert ">Other settings<" not in body

    # 6: explanatory caption under "Devices" removed.
    assert "Add or remove paired YouTube TV devices" not in body

    # 8: skip categories 2-col grid wrapper.
    assert 'class="skip-grid"' in body

    # 3+9: Other settings ordering — Autoplay before Report, Report before
    # Min skip, Min skip before Join name.
    i_autoplay = body.index('name="auto_play"')
    i_report = body.index('name="skip_count_tracking"')
    i_min = body.index('name="minimum_skip_length"')
    i_join = body.index('name="join_name"')
    assert i_autoplay < i_report < i_min < i_join


def test_round4_offset_dropdown(app_with_tmp_config) -> None:
    """Round 4 item 5: device_offset is now a <select>; Remove button sits
    inside the same cell, after the select."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps({"devices": [{"screen_id": "scr-x", "name": "TV", "offset": 250}]})
    )
    client = TestClient(app)
    r = client.get("/")
    body = r.text
    assert '<select name="device_offset">' in body
    # Selected option for offset=250 from disk.
    assert 'value="250" selected' in body
    # Boundary options present.
    assert 'value="-2000"' in body and 'value="2000"' in body
    # Offset cell wraps select + Remove together.
    assert 'class="offset-controls"' in body
    # Remove button still works (no name attr; type=button).
    assert "this.closest('tr').remove()" in body


def test_round4_min_skip_dropdown(app_with_tmp_config) -> None:
    """Round 4 item 9: minimum_skip_length is now a <select>."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(json.dumps({"minimum_skip_length": 10}))
    client = TestClient(app)
    r = client.get("/")
    body = r.text
    assert '<select name="minimum_skip_length">' in body
    assert 'value="10" selected' in body


def test_round4_offset_select_round_trips_through_save(app_with_tmp_config) -> None:
    """Round 4 item 5: posting the select value persists correctly."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps({"devices": [{"screen_id": "scr-y", "name": "Old TV", "offset": 0}]})
    )
    client = TestClient(app)
    r = client.post(
        "/save",
        data={
            "device_name": "TV1",
            "device_screen_id": "scr-y",
            "device_offset": "750",
            "minimum_skip_length": "5",
            "join_name": "iSponsorBlockTV",
        },
    )
    assert r.status_code == 200
    on_disk = json.loads((tmp / "config.json").read_text())
    # config_io.sanitize() coerces both fields to int.
    assert on_disk["devices"][0]["offset"] == 750
    assert on_disk["minimum_skip_length"] == 5


def test_round5_skip_categories_sorted(app_with_tmp_config) -> None:
    """Round 5 item C1: skip categories render alphabetically.

    Canonical order in config_io.ALL_SKIP_CATEGORIES has 'sponsor' first
    and 'selfpromo' second; alphabetical pushes 'exclusive_access' before
    both. The rendered value="..." attributes on each checkbox preserve
    the iteration order, so we can find them in the body and confirm.
    """
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    body = r.text
    i_excl = body.index('value="exclusive_access"')
    i_filler = body.index('value="filler"')
    i_intro = body.index('value="intro"')
    i_sponsor = body.index('value="sponsor"')
    # Alphabetical: exclusive_access < filler < intro < sponsor.
    assert i_excl < i_filler < i_intro < i_sponsor


def test_round5_dropdown_unit_suffixes(app_with_tmp_config) -> None:
    """Round 5 items C5/C6: option text includes the unit; label drops it."""
    app, tmp = app_with_tmp_config
    # Seed a device so the offset dropdown renders.
    (tmp / "config.json").write_text(
        json.dumps({"devices": [{"screen_id": "scr-x", "name": "TV", "offset": 0}]})
    )
    client = TestClient(app)
    r = client.get("/")
    body = r.text
    # Min skip: every option text ends with " seconds".
    assert ">0 seconds<" in body
    assert ">10 seconds<" in body
    assert ">60 seconds<" in body
    # Label dropped the "(seconds)".
    assert "Minimum skip length (seconds)" not in body
    # Offset: option text ends with " ms" (signed too).
    assert ">0 ms<" in body
    assert ">250 ms<" in body
    assert ">-2000 ms<" in body
    assert ">2000 ms<" in body
    # Table header dropped "(ms)".
    assert "<th>Offset</th>" in body
    assert "<th>Offset (ms)</th>" not in body


def test_round5_skip_count_label(app_with_tmp_config) -> None:
    """Round 5 item C4: "Send anonymous data to SponsorBlock" replaces the
    longer round-4 copy."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    body = r.text
    assert "Send anonymous data to SponsorBlock" in body
    assert "Report skipped segments" not in body


def test_round5_logs_default_n_is_ten(app_with_tmp_config) -> None:
    """Round 5 item L4: /logs default is 10 lines."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs")
    assert r.status_code == 200
    # Number input renders the n value; default of 10 should appear.
    assert 'id="logs-n"' in r.text
    assert 'value="10"' in r.text


def test_round5_logs_has_pause_copy_and_links(app_with_tmp_config) -> None:
    """Round 5 items L1/L2/L3/L5: pause-refresh button, copy button, and
    project links present on /logs."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs")
    body = r.text
    # Buttons.
    assert 'id="logs-pause-btn"' in body
    assert "Pause refresh" in body
    assert 'id="logs-copy-btn"' in body
    # Project links open in new tab.
    assert 'href="https://github.com/toddwchapin/iSponsorblockTV_WebUI"' in body
    assert 'href="https://github.com/dmunozv04/iSponsorBlockTV"' in body
    assert body.count('target="_blank"') >= 2


def test_round5_channels_apikey_link(app_with_tmp_config) -> None:
    """Round 5 channels item: 'YouTube Data API key' phrase in the page
    caption is wrapped in an anchor to the docs, target=_blank."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/channels")
    body = r.text
    assert (
        '<a href="https://developers.google.com/youtube/v3/getting-started"'
        in body
    )
    assert "YouTube Data API key</a>" in body


def test_channels_page_warns_when_no_apikey(app_with_tmp_config) -> None:
    """Issue #25 IA: when no key is set, the search input is hidden and
    the help text explains how to enable it."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/channels")
    assert r.status_code == 200
    assert "Set a YouTube Data API key" in r.text
    # The search input must NOT render when no key is set.
    assert 'name="q"' not in r.text


def test_channels_remove_404_when_missing(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.delete("/channels/UC_does_not_exist")
    assert r.status_code == 404


def test_channels_search_errors_without_apikey(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/channels/search?q=foo")
    assert r.status_code == 200
    assert "No YouTube API key" in r.text


def test_pair_page_renders(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/pair")
    assert r.status_code == 200
    assert "Pair a YouTube TV device" in r.text


def test_pair_code_rejects_short_code(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.post("/pair/code", data={"code": "12345"})
    assert r.status_code == 200
    assert "12 digits" in r.text


def test_status_endpoint_shape(app_with_tmp_config) -> None:
    """Issue #4: GET /status returns method + running + detail."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"method", "running", "detail"}
    assert isinstance(body["running"], bool)


def test_status_badge_partial(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/status/badge")
    assert r.status_code == 200
    assert "status-badge" in r.text
    assert 'hx-get="/status/badge"' in r.text


def test_logs_page_renders(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs")
    assert r.status_code == 200
    assert "Service logs" in r.text


def test_logs_tail_partial(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs/tail?n=10")
    assert r.status_code == 200
    assert 'id="logs-tail"' in r.text


def test_logs_link_in_nav(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/logs"' in r.text
    assert 'id="status-badge"' in r.text


def test_save_button_disabled_when_running(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 4: with service running, save button starts disabled
    so dirty-tracking JS can enable it on first edit."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("docker", True, "container running")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="save-btn"' in r.text
    assert "Save and restart service" in r.text
    assert 'data-mode="restart"' in r.text
    assert "disabled" in r.text  # the save button is disabled


def test_save_button_start_mode_when_stopped(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 5: when service detected as stopped, button is
    labeled 'Start service' and is enabled (no dirty gate)."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("docker", False, "container stopped")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Start service" in r.text
    assert 'data-mode="start"' in r.text
    # The save-btn line itself must not be disabled. Other elements may be
    # disabled, so anchor on the button id.
    btn_line = next(
        line for line in r.text.splitlines() if 'id="save-btn"' in line
    )
    # button tag spans multiple lines — collect until '>'
    idx = r.text.index('id="save-btn"')
    tag_close = r.text.index(">", idx)
    btn_tag = r.text[r.text.rindex("<", 0, idx):tag_close + 1]
    assert "disabled" not in btn_tag


def test_save_button_legacy_when_unknown(app_with_tmp_config, monkeypatch) -> None:
    """When detection method is 'none', no dirty gate (user not locked out)."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("none", False, "no detection")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Save and restart service" in r.text
    idx = r.text.index('id="save-btn"')
    tag_close = r.text.index(">", idx)
    btn_tag = r.text[r.text.rindex("<", 0, idx):tag_close + 1]
    assert "disabled" not in btn_tag
    assert 'data-no-dirty-gate="1"' in btn_tag


def test_status_badge_short_labels(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 6: badge shows 'Running' / 'Stopped' / 'Unknown'."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    client = TestClient(app)

    monkeypatch.setattr(ss, "status", lambda: ss.Status("docker", True, "ok"))
    r = client.get("/status/badge")
    assert "Running" in r.text and "Stopped" not in r.text

    monkeypatch.setattr(ss, "status", lambda: ss.Status("docker", False, "down"))
    r = client.get("/status/badge")
    assert "Stopped" in r.text
    assert "status-badge err" in r.text  # red

    monkeypatch.setattr(ss, "status", lambda: ss.Status("none", False, "none"))
    r = client.get("/status/badge")
    assert "Unknown" in r.text
    assert "status-badge unknown" in r.text


def test_tab_bar_active_class_per_page(app_with_tmp_config) -> None:
    """Issue #15 round 3 item 1: nav becomes a tab bar with the current
    page's tab marked active."""
    app, _ = app_with_tmp_config
    client = TestClient(app)

    for path, label in [("/", "Config"), ("/pair", "Pair Device"),
                         ("/channels", "Channels"), ("/logs", "Logs")]:
        r = client.get(path)
        assert r.status_code == 200, path
        # The active tab gets the 'active' CSS class.
        idx = r.text.index(f">{label}<")
        # Walk back to the opening <a tag for this link
        tag_start = r.text.rindex("<a", 0, idx)
        anchor = r.text[tag_start:idx]
        assert "active" in anchor, f"{path} tab missing active class"


def test_pair_save_appends_device(app_with_tmp_config) -> None:
    app, tmp = app_with_tmp_config
    client = TestClient(app)
    r = client.post(
        "/pair/save",
        data={
            "screen_id": "abc-screen",
            "name": "TV",
            "display_name": "Bedroom",
            "offset": "0",
        },
    )
    assert r.status_code == 200
    assert "added to config" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["devices"] == [
        {"screen_id": "abc-screen", "name": "Bedroom", "offset": 0}
    ]
