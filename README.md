# LEAF Bosland pipeline

This is the manual for the automated chain that takes LEAF scanner data from
the university file share and publishes it as a PAI dashboard.

It covers what runs, what to check when something goes wrong, and what to
change when things move.

Everything runs on one machine, from one cron entry, as one user. There is no
daemon, no queue and no database.

---

## Contents

1. [What happens, in order](#1-what-happens-in-order)
2. [The four stages](#2-the-four-stages)
3. [Where the data lives](#3-where-the-data-lives)
4. [Settings reference](#4-settings-reference)
5. [Logs and exit codes](#5-logs-and-exit-codes)
6. [Checking that it worked](#6-checking-that-it-worked)
7. [When something breaks](#7-when-something-breaks)
8. [Making changes](#8-making-changes)
9. [Moving the pipeline elsewhere](#9-moving-the-pipeline-elsewhere)
10. [Known quirks](#10-known-quirks)

---

## 1. What happens, in order

Every Monday at 02:00, five things happen one after another.

**Step 1.** Cron starts `bosland_sync.sh`.

**Step 2.** `rsync` copies any new scan files from the university share onto
local disk.

**Step 3.** `bospai.py` reads those new scans and works out PAI values, adding
them to the time-series CSVs.

**Step 4.** `genrate_dashboard.py` builds `index.html` from the CSVs.

**Step 5.** `git push` publishes that page to GitHub Pages.

Steps 2 to 5 all run inside `bosland_sync.sh`. Each one only runs if the
previous one succeeded, so a failed sync stops the chain rather than publishing
a stale page.

### The basics

- **Host**: `cave012.ugent.be`
- **User**: `kdayal`
- **Trigger**: `0 2 * * 1 /Stor1/karun/bosland_sync.sh`
- **Runs**: weekly, Mondays at 02:00 local time
- **Output**: GitHub Pages, served from `krdyl/leaf_monitor`, branch `main`

---

## 2. The four stages

### Stage 1: cron starts the run

One crontab entry runs `bosland_sync.sh` as `kdayal`.

Cron gives a script very little to work with. There is no conda activation, no
SSH agent, no profile, and `PATH` is only `/usr/bin:/bin`.

Every path in the chain is therefore absolute, and the Python interpreter is
named explicitly rather than looked up.

One thing to remember: cron does not catch up on missed runs. If the machine is
asleep or switched off at 02:00 on a Monday, that week is simply skipped.

### Stage 2: sync from the university share

Script: `/Stor1/karun/bosland_sync.sh`

The share `//files.ugent.be/kdayal/shares/bosland` is mounted over CIFS at
`/mnt/kdayal/bosland`.

It is a systemd automount, not a permanent mount. It attaches when something
touches it, and detaches again after roughly seventeen minutes of inactivity.
The script's `[ -d "$SOURCE" ]` check is what triggers the mount, and also what
notices when mounting has failed.

```
SOURCE = /mnt/kdayal/bosland/BOS      read-only, the university share
DEST   = /Stor1/karun/data/BOS        the local mirror
```

For each of the eight scanners it runs:

```bash
rsync -a --itemize-changes "$SRC" "$DST"
```

Three safety features are deliberate, and worth keeping.

The source is treated as strictly read-only, with no `--delete` and no
`--remove-source-files`. The comment block at the top of the script says as
much, and it should stay there.

Path guards refuse to run if `SOURCE` or `DEST` are not what they should be.
This stops a typo turning into an rsync onto the wrong tree.

A missing source directory is treated as a warning rather than a crash. The
other seven scanners still sync, and the run is marked as failed at the end.

New files are counted by picking `^>f` lines out of the itemised output.

### Stage 3: work out PAI

Script: `/home/kdayal/Documents/projects/qfl/pylidar-tls-canopy/src/bospai.py`

Run with: `/home/kdayal/miniforge3/envs/pylidar-tls-canopy/bin/python`

This reads the local mirror rather than the share, so it needs no network
access and no mount.

For every scan file not already in the output CSVs, it builds a
`pylidar_tls_canopy.plant_profile.Jupp2009` profile and takes three total-PAI
estimates from it. The results are appended to one CSV per scanner.

The step is incremental. A record is identified by `(date, scan_type, hour)`,
and anything already present is skipped. Re-running when there is nothing new
takes seconds.

```
Output: /Stor1/karun/data/pai_timeseries/<PLOT>_<SENSORDIR>_<SERIAL>.csv

For example: BOS004_B04_ESS00328.csv
```

### Stage 4: build and publish the dashboard

Script: `/home/kdayal/Documents/projects/qfl/leaf_monitor/src/genrate_dashboard.py`

This collects every CSV in `pai_timeseries/`, embeds them as JSON in a single
self-contained `index.html`, writes that into the local clone of
`leaf_monitor`, commits it and pushes to `main`.

GitHub Pages serves that branch, so the site updates a minute or two after the
push.

Authentication uses the SSH key at `~/.ssh/id_ed25519`. That key has no
passphrase, which is necessary, because cron has no agent to unlock one.

---

## 3. Where the data lives

### Directory layout

Both the share and the local mirror use the same structure.

```
BOS/
└── <plot>/              001, 002, 003, 004
    └── LF/
        └── <sensor>/    D08, H04, D04, H08, D06, H06, B04, H04
            ├── data/    scan files, the only thing the PAI step reads
            ├── pwr/     instrument power logs
            └── log/     instrument logs
```

### The eight scanners

| Plot | Sensors | Serials |
|---|---|---|
| BOS001 | D08, H04 | ESS00332, ESS00331 |
| BOS002 | D04, H08 | ESS00334, ESS00333 |
| BOS003 | D06, H06 | ESS00329, ESS00330 |
| BOS004 | B04, H04 | ESS00328, ESS00327 |

Note that `H04` appears under both BOS001 and BOS004. These are two different
instruments. Output filenames include the plot, so they do not collide.

### Scan filenames

```
ESS00328_1057_hemi_20260728-080028Z_0800_0400.csv
└──┬───┘ └─┬┘ └─┬┘ └──────┬───────┘ └───┬────┘
 serial  count type    UTC timestamp   resolution
```

The resolution field holds the zenith and azimuth shot counts. This is what
distinguishes the scan variants from one another.

| Scan type | Code | Label |
|---|---|---|
| hemi | `0200_0100` | low |
| hemi | `0400_0200` | medium |
| hemi | `0800_0400` | high |
| hinge or ground | `0001_8500` | low |
| hinge or ground | `0003_8500` | medium |
| hinge or ground | `0005_8500` | high |

Anything not in that table is logged as unrecognised and left out.

`ground` scans are read but never used. A `zenith` scan type also exists in the
data, and is ignored.

### When the scans happen

| Scan | UTC hour | Recorded as |
|---|---|---|
| hinge, high | 21 and 00 | `hinge_hi` |
| hemi, low | 20 | `hemi_low` |
| hemi, high | 02 | `hemi_hi` |
| ground | n/a | ignored |

Every timestamp, in filenames and in the output, is UTC.

Belgium is UTC+1 in winter and UTC+2 in summer, so the local time of a scan
shifts by an hour across the daylight-saving boundary.

### What the output CSVs contain

One row per date, scan type and hour. One file per scanner.

| Column | Meaning |
|---|---|
| `date` | scan date, UTC |
| `plot` | for example `BOS003` |
| `sensor` | instrument serial, for example `ESS00330` |
| `scan_type` | `hinge_hi`, `hemi_hi` or `hemi_low` |
| `hour` | UTC hour; blank on aggregated multi-scan days |
| `pai_hinge`, `pai_hinge_std` | hinge-angle PAI |
| `pai_hemi`, `pai_hemi_std` | solid-angle weighted PAI |
| `pai_linear`, `pai_linear_std` | linear-model PAI |
| `n_scans` | how many scans went into this row |

The dashboard depends on `date`, `scan_type` and the six `pai_*` columns by
name. Everything else is free to change.

Adding columns is safe. The dashboard ignores any it does not recognise.

A note on the `_std` columns. They hold the spread across repeat scans within
the same group. Most groups contain a single scan, so most of these values are
a flat `0.0`. They only mean anything on days with several scans of the same
type.

---

## 4. Settings reference

### In `bosland_sync.sh`

| Setting | Purpose |
|---|---|
| `SOURCE` | share mount path |
| `DEST` | local mirror path |
| `LOGDIR` | where logs are written |
| `SENSORS` | plot to sensor-directory mapping |
| `PY` | Python interpreter for both downstream scripts |
| `PAI_SCRIPT` | path to `bospai.py` |
| `DASH_SCRIPT` | path to `genrate_dashboard.py` |

### In `bospai.py`

| Setting | Default | Notes |
|---|---|---|
| `BOS_ROOT` | `/Stor1/karun/data/BOS` | must match `DEST` above |
| `OUTPUT_DIR` | `/Stor1/karun/data/pai_timeseries` | must match the dashboard's `PAI_DIR` |
| `LOG_DIR` | `/Stor1/karun/logs` | shared with the sync script |
| `SCANNER_DIRS` | four plots, two sensors each | add new instruments here |
| `SENSOR_HEIGHT` | `1.8` m | applied to every scanner |
| `MAX_H` | `50` m | top of the vertical profile |
| `HRES` | `0.5` m | vertical bin size |
| `ZRES` and `ARES` | `5°` and `90°` | zenith and azimuth bin size |
| `MIN_ZENITH` to `MAX_ZENITH` | `55°` to `60°` | the hinge-angle window |
| `HINGE_NORMAL_HOURS` | `{21, 0}` | UTC hours accepted for hinge scans |
| `RESOLUTION_CODES` | see the table above | add new scan configurations here |

### In `genrate_dashboard.py`

| Setting | Purpose |
|---|---|
| `PAI_DIR` | where to read the CSVs from |
| `REPO_DIR` | local clone of `leaf_monitor` |
| `FIELD_VISITS` | dates drawn as vertical reference lines |

### Running `bospai.py` by hand

```bash
bospai.py                  # incremental update, all scanners
bospai.py --dry-run        # report what would change, write nothing
bospai.py --plot BOS003    # restrict to one plot, repeatable
bospai.py --sensor D06     # restrict to one sensor directory, repeatable
bospai.py --rebuild        # discard existing records, recompute everything
bospai.py --verbose        # debug logging
```

`--dry-run` is the safe first move after any change.

It counts candidate records without processing them, so the number it reports
is an upper bound. Groups whose scans all turn out empty produce no row.

---

## 5. Logs and exit codes

### Where the logs are

```
/Stor1/karun/logs/
├── bosland_sync_YYYYMMDD.log     everything one day's runs did
├── compute_pai_YYYYMMDD.log      detail from the PAI stage
└── status.log                    one line per run, kept indefinitely
```

`status.log` is the quickest health check available:

```bash
tail -5 /Stor1/karun/logs/status.log
```

```
2026-08-19 sync=0 pai=0 dash=0 new_files=0
```

All zeros means healthy.

The dated logs are deleted after 180 days by the sync script. `status.log` is
not, so it stays as the long-term record.

### Exit codes

For `bosland_sync.sh`:

- **0**: the whole chain is fine
- **1**: the rsync stage failed, so PAI and dashboard were skipped
- **anything else**: passed up from a downstream stage

For `bospai.py`:

- **0**: success, including having nothing to do
- **1**: finished, but some scans errored; the CSVs were still updated
- **2**: fatal, meaning a bad environment, a missing data root, or another
  copy already running

Empty scans are counted separately from errors, and do not fail the run. They
are routine.

A lock file at `/tmp/compute_pai.lock` stops two PAI runs overlapping. If a run
reports that another instance is already running and you are sure nothing is,
check with `pgrep -af bospai` before removing the lock.

---

## 6. Checking that it worked

After any Monday, in order of decreasing effort.

The quickest look:

```bash
tail -3 /Stor1/karun/logs/status.log
```

What the last run actually did:

```bash
cat /Stor1/karun/logs/bosland_sync_$(date +%Y%m%d).log
```

Whether anything reached the website:

```bash
git -C /home/kdayal/Documents/projects/qfl/leaf_monitor log --oneline -3
```

One distinction is worth holding on to. **A missing log file means the script
never ran at all**, not that it ran and failed. That points at cron, at the
machine being asleep, or at the script being unreadable, rather than at
anything inside the pipeline.

To check the data itself:

```bash
python - <<'EOF'
import pandas as pd, glob
from pathlib import Path
for f in sorted(glob.glob("/Stor1/karun/data/pai_timeseries/*.csv")):
    df = pd.read_csv(f, parse_dates=["date"])
    print(f"{Path(f).stem:26s} {len(df):5d} rows  "
          f"{df.date.min().date()} → {df.date.max().date()}  "
          f"dupes={df.duplicated(['date','scan_type','hour']).sum()}")
EOF
```

`dupes` must be zero everywhere. The latest date should keep pace with the
newest data on the share.

---

## 7. When something breaks

### No log file for a Monday

The script never started.

Check for a `CRON ... CMD` entry:

```bash
sudo grep -i bosland /var/log/syslog*
```

If cron did fire, `/Stor1` was probably unwritable. If it did not, the machine
was asleep, or cron is not running.

### "share not mounted?" in the log

The automount failed, usually because of credentials or a network problem at
02:00.

Reproduce it with `ls /mnt/kdayal/bosland/BOS`, and check
`systemctl status mnt-kdayal-bosland.mount`.

### Sync worked, but the PAI section is missing from the log

The downstream block is unreachable. Almost always this is a stray `exit` left
above it in `bosland_sync.sh`.

```bash
grep -n '^exit' /Stor1/karun/bosland_sync.sh
```

There should be no `exit` before the downstream block.

### "cannot import pylidar_tls_canopy"

`PY` is pointing at the wrong interpreter.

It has to be the conda environment's Python, given as an absolute path. Cron
never activates conda.

### The dashboard builds, but the website does not change

The push failed.

Test authentication the way cron sees it:

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin ssh -o BatchMode=yes -T git@github.com
```

You want `Hi krdyl! You've successfully authenticated`. Anything else, whether
a prompt, a hang, or `Permission denied`, is what cron will hit too.

Also confirm `git config user.email` is set. A commit with no identity fails
before the push is even attempted.

### Lots of empty scans

Normal. Scans with no usable returns produce no row, and are retried on each
run.

A sudden increase suggests an instrument problem rather than a pipeline
problem.

---

## 8. Making changes

### Adding a plot or a sensor

Two files, and they have to agree.

1. `bosland_sync.sh`: add it to the `SENSORS` array.
2. `bospai.py`: add it to `SCANNER_DIRS`.

Then confirm it finds the scans, and run it once by hand:

```bash
bospai.py --dry-run --plot BOSxxx
```

A new CSV appears in `pai_timeseries/`, and the dashboard picks it up as a new
nav entry on its own. No dashboard changes are needed.

### Adding a scan resolution or type

Add the code to `RESOLUTION_CODES` in `bospai.py`.

Until you do, matching files are logged as unrecognised and left out, so check
the warnings in the PAI log after any change to instrument configuration.

Adding a genuinely new `scan_type`, beyond `hinge_hi`, `hemi_hi` and
`hemi_low`, also means editing `SCAN_TYPES` in `genrate_dashboard.py`, which
expects exactly those three.

### Adding field visit dates

Edit `FIELD_VISITS` in `genrate_dashboard.py` and re-run it. The dates are
plain `YYYY-MM-DD` strings, and they appear as dotted vertical lines on every
panel.

### Changing processing parameters

`SENSOR_HEIGHT`, `MAX_H`, `HRES`, the zenith window and the weighting method
all determine the numbers themselves.

Changing any of them makes new records incomparable with the existing ones.

So do not simply append after such a change. Either recompute everything:

```bash
bospai.py --rebuild
```

Or archive the old CSVs first, if you want to keep the previous series:

```bash
cp -r /Stor1/karun/data/pai_timeseries \
      /Stor1/karun/data/pai_timeseries.bak-$(date +%F)
```

A full `--rebuild` over the whole archive takes roughly an hour.

### Changing the schedule

Edit the crontab with `crontab -e`.

The five fields are minute, hour, day of month, month, and day of week.
Minutes and hours are plain integers. Day of week 1 is Monday, so `0 2 * * 1`
is Mondays at 02:00 local time.

If the machine is ever suspended overnight, a systemd timer with
`Persistent=true` is the better choice. It runs a missed job on resume; cron
does not.

---

## 9. Moving the pipeline elsewhere

What to do to move everything to a different machine or user account.

### Step 1: recreate the environment

```bash
conda env create -f environment.yml     # from the pylidar-tls-canopy repo
```

Note the new interpreter path, which is `which python` inside the activated
environment. You will need it in step 4.

### Step 2: set up the share mount

Recreate the CIFS mount for `//files.ugent.be/<user>/shares/bosland`, along
with its credentials.

Keep it as an automount if you like, but confirm that it mounts on first access
from a non-interactive context, because that is how the script will touch it:

```bash
env -i PATH=/usr/bin:/bin ls /mnt/<user>/bosland/BOS | head
```

### Step 3: copy the data and the scripts

```
/Stor1/karun/data/BOS/               the local mirror
/Stor1/karun/data/pai_timeseries/    the time series
/Stor1/karun/logs/status.log         run history
bosland_sync.sh
bospai.py
```

The mirror can be rebuilt from the share, slowly. The time series can be
rebuilt with `--rebuild`, also slowly.

Copying both is faster, and safer.

### Step 4: update every path

| File | Settings to change |
|---|---|
| `bosland_sync.sh` | `SOURCE`, `DEST`, `LOGDIR`, `PY`, `PAI_SCRIPT`, `DASH_SCRIPT` |
| `bospai.py` | `BOS_ROOT`, `OUTPUT_DIR`, `LOG_DIR` |
| `genrate_dashboard.py` | `PAI_DIR`, `REPO_DIR` |

Two of these have to match each other:

- `BOS_ROOT` must equal `DEST`
- `OUTPUT_DIR` must equal `PAI_DIR`

Those are the joints where the chain comes apart if you miss one, and nothing
checks them for you.

### Step 5: set up push access

```bash
git clone git@github.com:krdyl/leaf_monitor.git
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519      # no passphrase
```

Add the public key to GitHub as a deploy key with write access.

Then check it works from a bare environment, and set a commit identity:

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin ssh -o BatchMode=yes -T git@github.com

git config --global user.email "you@example.com"
git config --global user.name  "Your Name"
```

### Step 6: test in stages

```bash
<newpy> bospai.py --dry-run          # sees the scans, wants to add nothing
bash -n bosland_sync.sh              # syntax only
./bosland_sync.sh; echo "exit=$?"    # the whole chain, interactively
```

### Step 7: test the way cron will run it

This is the step people skip, and it is where migrations usually fail.

```bash
env -i HOME=/home/<user> USER=<user> LOGNAME=<user> SHELL=/bin/sh \
    PATH=/usr/bin:/bin /path/to/bosland_sync.sh; echo "exit=$?"
```

`env -i` strips conda, the SSH agent and your shell profile, leaving roughly
what cron provides. If it passes here, it will pass at 02:00.

### Step 8: install the crontab

```bash
crontab -e        # 0 2 * * 1 /path/to/bosland_sync.sh
```

### Moving only the dashboard

Change `REPO_DIR` in `genrate_dashboard.py`, clone the new repository, and
enable GitHub Pages on `main` in the repository settings.

The CSV schema is the only contract between the PAI stage and the dashboard, so
nothing upstream needs to know about the move.

---

## 10. Known quirks

Things that look like bugs but are not, plus a few real limitations.

### The instrument clocks are wrong

Scan file modification times are dated 2056 and 2086. The loggers' real-time
clocks are either unset or have rolled over, and rsync preserves these
faithfully.

The dates in the filenames are correct. The filesystem timestamps are not.

So never use `find -mtime`, `-newermt`, or "sort by date" on the raw scan
files. The pipeline reads dates from filenames, and is unaffected.

### `pai_hemi` duplicates `pai_hinge`

The profile is populated through a 55–60° window, so only the hinge-angle
zenith ring carries any data. The solid-angle method then normalises against
that single ring and returns the hinge total.

The two scalar columns therefore agree by construction.

This is understood and accepted. The value of the hemi method here is in the
shape of the vertical PAVD profile, not in the scalar.

### `pai_linear` is not trustworthy as it stands

Same underlying cause. The linear model fits across zenith rings, and the
thirteen unpopulated rings enter that fit carrying a fill value of `log(1e-5)`
rather than being excluded.

If the linear estimate ever matters, the hemi scans need processing through a
wide zenith window, roughly 5–70°, in a separate pass.

### The share unmounts itself

The idle timeout is about seventeen minutes.

This is expected and harmless. The sync script's directory check re-triggers
the mount.

### Cron mail goes nowhere

There is no MTA on this machine, so anything a script prints outside its own
log file is discarded.

This is why every stage writes to its own log and to `status.log`. Do not rely
on cron emailing you about a failure.

### Empty and failed scans are retried forever

They leave no record, so they are offered again on every run.

This is cheap at current volumes. But a permanently corrupt file will reappear
in the log every week.

### The workstation can suspend

If it sleeps through 02:00 on a Monday, cron skips that week silently and
leaves no log.

At a glance this is indistinguishable from the script never having been
installed at all.

Worth disabling idle suspend on this machine, or moving to a systemd timer with
`Persistent=true`.
