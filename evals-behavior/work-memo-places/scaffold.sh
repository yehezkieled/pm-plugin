#!/usr/bin/env bash
# The tariff-check analysis already laid out by /pm:init: a Where things go table, data in data/raw/<source>/,
# code in src/, an empty board. No remote, so board writes stay local.
# Endeavour's price list is then dropped at the root, untracked; the agent should move it into data/raw/.
set -euo pipefail
mkdir -p data data/raw/aer data/raw/ausgrid docs docs/pm notebooks src
cat > README.md <<'EOF_FIXTURE'
# tariff-check

Checks the AER's 2025-26 network tariff file against each NSW distributor's own published price list, so the pricing team knows which tariff codes disagree before retail prices are set.

Run `python3 src/recon.py`; it writes `out/discrepancies.csv`.

Distributors covered so far: Ausgrid. Endeavour Energy and Essential Energy still to do.
EOF_FIXTURE
cat > AGENTS.md <<'EOF_FIXTURE'
# tariff-check

Checks the AER's 2025-26 network tariff file against each NSW distributor's own price list. Shape: analysis. Product overview: [README.md](README.md).

This file routes; the facts live in the files it points at. Where each kind of knowledge goes: `/pm:help`.

## Where things go

Before creating any file, find its kind here and put it in that place. No row fits: ask once, recommend a place, and add the row in the same change. Nothing else goes at the root. A place that exists is a link, to its folder's `README.md` when it has one; a place with no file yet stays a plain path until its first file lands. `out/` is never a link: it is gitignored.

| Kind of thing | Place | Rule |
| --- | --- | --- |
| Tasks: what is being done and what is next | `docs/pm/items/` | `/pm:plan` adds them and `/pm:work` claims them; never made by hand |
| How it works, decisions, gotchas | [`docs/`](docs/) | one file per topic; update it, don't duplicate it |
| Deliverables for people: memos, reports, findings | `reports/` | written by a person or an agent; `YYYY-MM-DD-<topic>.md`; cite the data and the command behind each number |
| Generated outputs | `out/` | written only by code; never hand-edited; gitignored |
| Project files at the root | `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `requirements.txt` | nothing else at the root |
| Raw data as received | [`data/raw/<source>/`](data/raw/) | never edited; keep the publisher's file name |
| Where each dataset came from | [`data/README.md`](data/README.md) | one line per file: source, date received, what reads it |
| Reusable code | [`src/`](src/) | loaders, checks, transforms; run from the root |
| Exploration | [`notebooks/`](notebooks/) | `YYYY-MM-DD-<question>.ipynb`; findings worth keeping go to `reports/` |

## When you finish a task

Before you finish, update what this table names for your change, and keep every link working: the pm plugin's walk test (`pm.py walk`) fails on a broken or missing link.

| If your change | Update |
| --- | --- |
| adds a folder or a new kind of file | a row above whose place links to the folder's new `README.md`; that `README.md` says what the folder holds, links each file it describes, and links back to [AGENTS.md](AGENTS.md) |
| puts the first file in a place above that is still a plain path | that row: make the place a link |
| changes what a folder holds or how it is used | that folder's `README.md` or `CONTEXT.md`, linked from its row |
| changes how to install, run, or use the project | [README.md](README.md), and Every session below for build and test commands |
| changes a part that has a card in the System map | that card, its date and commit, or `status: stale` |

## Route by task

| If you are | Go to |
| --- | --- |
| adding or tracking work | `/pm:plan` |
| doing any project work (code, data, a deliverable) | `/pm:work`: it claims the item first, adding it with `/pm:plan` if it is not on the board |
| asking what is in flight or next | `/pm:status` |
| re-running the comparison | `python3 src/recon.py`, which writes `out/discrepancies.csv` |
| checking what was already asked about a tariff | `docs/notes.md` |

## Every session

- Run: `python3 src/recon.py`.
- Claim an item before changing code or data; keep the requester's words verbatim in the item.
EOF_FIXTURE
cat > CLAUDE.md <<'EOF_FIXTURE'
@AGENTS.md
EOF_FIXTURE
cat > .gitignore <<'EOF_FIXTURE'
out/
__pycache__/
EOF_FIXTURE
cat > requirements.txt <<'EOF_FIXTURE'
pandas>=2.2
matplotlib>=3.9
EOF_FIXTURE
cat > docs/notes.md <<'EOF_FIXTURE'
# notes

- 2025-10-02: Ausgrid EA025 peak is 25.043 in their price list vs 24.733 in the AER file (0.31 c/kWh). Asked Priya in pricing whether the AER file is the pre-approval version.
- 2025-10-03: EA225 off-peak 3.901 vs 3.874. Same question.
- Endeavour uses NUOS codes (N70...) and calls fixed charges "Supply"; map before comparing.
- Manager wants a one-page memo per distributor, not the raw CSV.
EOF_FIXTURE
cat > docs/pm/config.json <<'EOF_FIXTURE'
{"workers": {"model": "claude-sonnet-5-5", "effort": "medium"}, "validators": {"model": "claude-sonnet-5-5", "effort": "medium"}}
EOF_FIXTURE
cat > data/README.md <<'EOF_FIXTURE'
# Data

Each dataset, where it came from, and what reads it. Listed in [AGENTS.md](../AGENTS.md) › Where things go.

| File | Source | Received | Read by |
| --- | --- | --- | --- |
| [raw/aer/aer_network_tariffs_2025-26.csv](raw/aer/aer_network_tariffs_2025-26.csv) | AER network tariff file, 2025-26 | 2025-10-01 | `src/recon.py` |
| [raw/ausgrid/ausgrid_price_list_2025-26.csv](raw/ausgrid/ausgrid_price_list_2025-26.csv) | Ausgrid published price list, 2025-26 | 2025-10-01 | `src/recon.py` |
EOF_FIXTURE
cat > data/raw/aer/aer_network_tariffs_2025-26.csv <<'EOF_FIXTURE'
distributor,tariff_code,tariff_name,charge_type,period,rate,unit
Ausgrid,EA010,Residential flat,energy,anytime,9.214,c/kWh
Ausgrid,EA010,Residential flat,fixed,daily,52.81,c/day
Ausgrid,EA025,Residential time of use,energy,peak,24.733,c/kWh
Ausgrid,EA025,Residential time of use,energy,shoulder,6.402,c/kWh
Ausgrid,EA025,Residential time of use,energy,offpeak,3.215,c/kWh
Ausgrid,EA025,Residential time of use,fixed,daily,52.81,c/day
Ausgrid,EA116,Residential demand,demand,peak,28.104,c/kW/day
Ausgrid,EA116,Residential demand,energy,anytime,2.981,c/kWh
Ausgrid,EA225,Small business TOU,energy,peak,26.115,c/kWh
Ausgrid,EA225,Small business TOU,energy,offpeak,3.874,c/kWh
Endeavour,N70,Residential flat,energy,anytime,10.402,c/kWh
Endeavour,N70,Residential flat,fixed,daily,49.20,c/day
Endeavour,N71,Residential seasonal TOU,energy,peak,27.310,c/kWh
Endeavour,N71,Residential seasonal TOU,energy,shoulder,7.120,c/kWh
Endeavour,N71,Residential seasonal TOU,energy,offpeak,3.988,c/kWh
Endeavour,N71,Residential seasonal TOU,fixed,daily,49.20,c/day
Endeavour,N73,Residential demand,demand,peak,31.550,c/kW/day
Endeavour,N90,Small business flat,energy,anytime,11.870,c/kWh
Endeavour,N91,Small business TOU,energy,peak,29.004,c/kWh
Endeavour,N91,Small business TOU,energy,offpeak,4.410,c/kWh
Essential,BLNN2AU,Residential anytime,energy,anytime,12.906,c/kWh
Essential,BLNT3AU,Residential TOU,energy,peak,30.218,c/kWh
Essential,BLNT3AU,Residential TOU,energy,offpeak,5.102,c/kWh
EOF_FIXTURE
cat > data/raw/ausgrid/ausgrid_price_list_2025-26.csv <<'EOF_FIXTURE'
Tariff code,Description,Charge,Time period,Price (c/kWh or c/day)
EA010,Residential flat,Energy,Anytime,9.214
EA010,Residential flat,Network access,Daily,52.810
EA025,Residential time of use,Energy,Peak,25.043
EA025,Residential time of use,Energy,Shoulder,6.402
EA025,Residential time of use,Energy,Off-peak,3.215
EA025,Residential time of use,Network access,Daily,52.810
EA116,Residential demand,Demand,Peak,28.104
EA116,Residential demand,Energy,Anytime,2.981
EA225,Small business TOU,Energy,Peak,26.115
EA225,Small business TOU,Energy,Off-peak,3.901
EOF_FIXTURE
cat > src/recon.py <<'EOF_FIXTURE'
"""Compare the AER 2025-26 network tariff file with Ausgrid's own price list."""
import csv
import os

AER = "data/raw/aer/aer_network_tariffs_2025-26.csv"
AUSGRID = "data/raw/ausgrid/ausgrid_price_list_2025-26.csv"
OUT = "out/discrepancies.csv"
TOLERANCE = 0.0005  # c/kWh; the AER file rounds to 3 dp

PERIOD = {"Anytime": "anytime", "Peak": "peak", "Shoulder": "shoulder", "Off-peak": "offpeak", "Daily": "daily"}
CHARGE = {"Energy": "energy", "Network access": "fixed", "Demand": "demand"}


def load_aer(distributor):
    with open(AER, newline="") as f:
        return {(r["tariff_code"], r["charge_type"], r["period"]): float(r["rate"])
                for r in csv.DictReader(f) if r["distributor"] == distributor}


def load_ausgrid():
    with open(AUSGRID, newline="") as f:
        return {(r["Tariff code"], CHARGE[r["Charge"]], PERIOD[r["Time period"]]): float(r["Price (c/kWh or c/day)"])
                for r in csv.DictReader(f)}


def main():
    aer, published = load_aer("Ausgrid"), load_ausgrid()
    rows = []
    for key in sorted(set(aer) | set(published)):
        a, p = aer.get(key), published.get(key)
        if a is None or p is None or abs(a - p) > TOLERANCE:
            rows.append({"distributor": "Ausgrid", "tariff_code": key[0], "charge_type": key[1], "period": key[2],
                         "aer_rate": a, "published_rate": p, "diff": None if a is None or p is None else round(p - a, 3)})
    os.makedirs("out", exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["distributor", "tariff_code", "charge_type", "period", "aer_rate", "published_rate", "diff"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} discrepancies written to {OUT}")


if __name__ == "__main__":
    main()
EOF_FIXTURE
cat > notebooks/2025-10-02-ausgrid-vs-aer.ipynb <<'EOF_FIXTURE'
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Ausgrid vs AER, quick look"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "import pandas as pd\n",
    "d = pd.read_csv('out/discrepancies.csv')\n",
    "d.sort_values('diff')"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "d.plot.bar(x='tariff_code', y='diff')"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
EOF_FIXTURE
git init -q
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
# Dropped after the commit: new and untracked, as a file the owner just saved there.
cat > endeavour_price_list_2025-26.csv <<'EOF_FIXTURE'
NUOS code,Tariff,Component,Period,Rate,Unit
N70,Domestic flat,Energy,All times,10.402,c/kWh
N70,Domestic flat,Supply,Per day,49.200,c/day
N71,Domestic seasonal TOU,Energy,High season peak,28.115,c/kWh
N71,Domestic seasonal TOU,Energy,Shoulder,7.120,c/kWh
N71,Domestic seasonal TOU,Energy,Off peak,3.988,c/kWh
N71,Domestic seasonal TOU,Supply,Per day,49.200,c/day
N73,Domestic demand,Demand,Peak,31.550,c/kW/day
N90,General supply flat,Energy,All times,11.870,c/kWh
N91,General supply TOU,Energy,Peak,29.400,c/kWh
N91,General supply TOU,Energy,Off peak,4.410,c/kWh
EOF_FIXTURE
# The person's earlier choice for this clone: worker sessions run in auto mode.
mkdir -p .git/pm-workers && printf '%s\n' '{"permission_mode": "auto"}' > .git/pm-workers/settings.json
