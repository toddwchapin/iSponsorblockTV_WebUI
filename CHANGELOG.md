# Changelog

All notable changes are recorded here. Versions follow
[Semantic Versioning](https://semver.org/), kept simple — patch bumps for
pure fixes, minor for new features. The pre-1.0 line is still in flux;
breaking template / route changes are still possible.

## [Unreleased]

### Docs
- README rewritten and shortened (~280 → ~120 lines). Page table, accurate
  feature list, and a single section for service detection and restart
  (#27).
- New `docs/SYSTEMD.md` — full systemd unit setup, DietPi note, sudoers,
  uninstall steps moved out of README.
- New `docs/ARCHITECTURE.md` — service detection internals, template +
  partial layout, design-token system, `/static` mount, a11y.
- New `CONTRIBUTING.md` — dev setup, lint, "adding a page" walkthrough.
- New `CHANGELOG.md` (this file).

## [0.2.0] — 2026-05-08

### Added
- **Design audit** ([#25] / [#26]) — design-token system in
  `app/assets/static/app.css` (terracotta accent ramp, status palette,
  type/spacing/motion scales, light/dark variants); self-hosted
  Bricolage Grotesque variable font (latin subset, ~77 KB woff2);
  `/static` StaticFiles mount; a11y additions (`aria-live` toast, hidden
  status announcer, `aria-current` on active tab, `:focus-visible` ring,
  `prefers-reduced-motion` guard); empty-config Quick start callout.
- **YouTube API key + proxy moved to `/channels`** ([#26]) — new
  `POST /channels/apikey` endpoint. The main config form preserves these
  fields from disk but no longer renders them. Channel search input is
  hidden until a key is saved.
- **Tab-bar nav, sticky chrome, fixed-bottom Save button** ([#15] round 3,
  [#24]) — header + tab nav pin to top, action bar pins to bottom, **Save
  and restart** is dirty-aware (disabled until form changes). When the
  service is detected as stopped, the same button switches to **Start
  service** and is enabled unconditionally.
- **Status badge labels tightened** ([#15] round 3) — Running (green) /
  Stopped (red) / Unknown (grey).
- **Config-page layout polish + restart indicator fix** ([#15] round 2,
  [#23]).
- **Observability** ([#4] / [#20]) — `/status` JSON, `/status/badge` HTML
  fragment, `/logs` page with auto-refreshing tail.
- **Mobile-stack device rows + pairing-code auto-hyphenation** ([#15]
  round 1, [#16]).

### Fixed
- Icon 404s on every page load ([#18] / [#19]).

### Docs
- Use absolute paths for the systemd unit edits ([#22]).
- Clarify systemd unit `User=` / `ExecStart=` edits ([#21]).
- Surface `--version` and `/healthz` in install + run-as-service docs
  ([#11] / [#12]).
- Document uninstall ([#8]).
- Fix install + run instructions for DietPi/root setups ([#7]).

### Changed
- Default port changed from 8080 to 8099 ([#13]).

### Removed
- Dead `/static` mount that crashed pipx installs ([#9] / [#10]) — later
  reintroduced intentionally for self-hosted CSS/JS/font assets in [#26].

## [0.1.0] — initial v1

- v1 web UI for iSponsorBlockTV configuration ([#2]) — config form,
  pairing flow, channel whitelist.

[#2]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/2
[#4]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/4
[#7]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/7
[#8]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/8
[#9]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/9
[#10]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/10
[#11]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/11
[#12]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/12
[#13]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/13
[#15]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/15
[#16]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/16
[#18]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/18
[#19]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/19
[#20]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/20
[#21]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/21
[#22]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/22
[#23]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/23
[#24]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/24
[#25]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/25
[#26]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/pull/26
[#27]: https://github.com/toddwchapin/iSponsorblockTV_WebUI/issues/27
