# hut-monitor

Watches campgrounds for openings on your dates and alerts you when something
**new** opens up. It works like a restock monitor, but for campsites.

- **Recreation.gov**: real checks via the availability JSON the website itself uses.
  Supports multi-night stays (every night must be `Available`), stays that span
  months, flexible arrival windows, and filters by site type, loop, or site number.
- **AMC huts** (Galehead, etc.): **stub only**. AMC has no public API we can
  confirm, and this tool won't scrape anything behind a login. The provider just
  prints your booking link with a "not supported yet" note so the watch stays
  visible. It never reports openings.

Alerts go to stdout always, to Discord if `DISCORD_WEBHOOK_URL` is set, and to
macOS Notification Center with `--mac-notify`.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp watches.example.toml watches.toml   # watches.toml and state.json are gitignored
```

Find a campground id:

```sh
.venv/bin/python -m hutmonitor find "Lower Pines"
#     232450  Lower Pines Campground  (Yosemite National Park, California)  https://...
```

## Config (`watches.toml`)

```toml
[[watch]]
name = "Upper Pines, 2 nights"
provider = "recgov"
campground_id = "232447"
arrive = 2027-05-21          # first night
nights = 2
# arrive_end = 2027-05-23    # optional flexible window: any arrival in range
# site_types = ["TENT", "STANDARD"]   # substring of campsite_type, case-insensitive
# loops = ["Upper Pines"]
# sites = ["044"]
# min_interval_s = 300       # per-campground poll floor (default 300)

[[watch]]
name = "Galehead Hut"
provider = "amc"             # stub
campground_id = "galehead"
arrive = 2027-08-14
url = "https://www.outdoors.org/"   # put your real booking page here
```

See `watches.example.toml` for more.

## Run

```sh
.venv/bin/python -m hutmonitor check                 # one pass
.venv/bin/python -m hutmonitor check --mac-notify    # + macOS notification
.venv/bin/python -m hutmonitor watch --every 10m     # loop (jittered, min 5m)
.venv/bin/python -m hutmonitor -v check              # verbose logging to stderr
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... .venv/bin/python -m hutmonitor check
```

Options: `--config PATH` (default `watches.toml`), `--state PATH` (default
`state.json`), and `--force` on `check` to ignore the poll interval (use sparingly).

### How alerting works

`state.json` stores, for each watch, the openings seen on the last successful
check. You're alerted only for openings that weren't in that set. If a site
disappears (someone booked it) and later comes back (cancellation), it alerts
again. A failed fetch leaves state untouched, so a network error never looks
like "everything vanished, then reappeared". The same file records when each
campground was last polled, so cron and launchd runs also respect the 5 minute floor.

## Run on a schedule

**cron** (every 10 minutes). Keep the webhook in a file only you can read
rather than in the crontab:

```cron
*/10 * * * * cd "/path/to/hut-monitor" && . ./.env 2>/dev/null; .venv/bin/python -m hutmonitor check >> monitor.log 2>&1
```

where `.env` holds `export DISCORD_WEBHOOK_URL=...` (`chmod 600 .env`; add it to
`.gitignore` if you keep it in the repo folder).

**launchd** (macOS): save as `~/Library/LaunchAgents/local.hutmonitor.plist`, then
`launchctl load ~/Library/LaunchAgents/local.hutmonitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>local.hutmonitor</string>
  <key>WorkingDirectory</key><string>/path/to/hut-monitor</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/hut-monitor/.venv/bin/python</string>
    <string>-m</string><string>hutmonitor</string>
    <string>check</string><string>--mac-notify</string>
  </array>
  <key>StartInterval</key><integer>600</integer>
  <key>StandardOutPath</key><string>/path/to/hut-monitor/monitor.log</string>
  <key>StandardErrorPath</key><string>/path/to/hut-monitor/monitor.log</string>
  <!-- Optional. Note that plists are plain text, so prefer a wrapper script that reads a 600 file:
  <key>EnvironmentVariables</key>
  <dict><key>DISCORD_WEBHOOK_URL</key><string>...</string></dict>
  -->
</dict>
</plist>
```

## Be polite

The recreation.gov endpoints are undocumented internals of the public website,
not an official API (the official one is RIDB). They can change or start
blocking without notice. Using them is subject to recreation.gov's Terms of Use.
Built-in limits:

- At most one poll per campground every 5 minutes by default (`min_interval_s`,
  hard floor 60s), and `watch --every` is clamped to at least 5 minutes.
- Requests within a pass get 1 to 4s of random jitter. The loop interval is
  jittered too, and watches on the same campground share one fetch.
- Exponential backoff on 429 and 5xx (honours `Retry-After`), then it gives up until the next pass.

Please don't crank these down, run many copies, or use this to auto-book or
resell sites. It's for getting a ping so *you* can go book a cancellation.
Don't commit `watches.toml`, `state.json`, or your webhook URL.

## Layout

```
hutmonitor/
  cli.py            check / watch / find
  runner.py         one pass: rate limits -> providers -> dedupe -> notify
  models.py         Watch, Opening
  config.py         watches.toml loader
  state.py          dedupe + last-polled state (JSON)
  notifiers.py      stdout, Discord webhook, osascript
  http.py           UA, jitter, backoff
  providers/
    base.py         Provider.check(watch) -> list[Opening]
    recgov.py       recreation.gov
    amc.py          AMC stub
tests/              pytest, fixtures only, network blocked
```

Add a provider by subclassing `providers.base.Provider` and registering it in
`providers/__init__.py:get_provider`.

## Tests

```sh
.venv/bin/python -m pytest -q
```
