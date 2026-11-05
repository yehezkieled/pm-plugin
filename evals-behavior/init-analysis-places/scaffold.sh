#!/usr/bin/env bash
# A data analysis with everything at the root: two source CSVs, a script that writes discrepancies.csv
# beside them, a notebook, and working notes. No board and no remote, so /pm:init runs without a push.
set -euo pipefail
cat > README.md <<'EOF_FIXTURE'
# tariff-check

Checks the AER's 2025-26 network tariff file against each NSW distributor's own published price list, so the pricing team knows which tariff codes disagree before retail prices are set.

Run `python3 recon.py`; it writes `discrepancies.csv`.

Distributors covered so far: Ausgrid. Endeavour Energy and Essential Energy still to do.
EOF_FIXTURE
cat > notes.md <<'EOF_FIXTURE'
# notes

- 2025-10-02: Ausgrid EA025 peak is 25.043 in their price list vs 24.733 in the AER file (0.31 c/kWh). Asked Priya in pricing whether the AER file is the pre-approval version.
- 2025-10-03: EA225 off-peak 3.901 vs 3.874. Same question.
- Endeavour uses NUOS codes (N70...) and calls fixed charges "Supply"; map before comparing.
- Manager wants a one-page memo per distributor, not the raw CSV.
EOF_FIXTURE
cat > recon.py <<'EOF_FIXTURE'
"""Compare the AER 2025-26 network tariff file with Ausgrid's own price list."""
import csv

AER = "aer_network_tariffs_2025-26.csv"
AUSGRID = "ausgrid_price_list_2025-26.csv"
OUT = "discrepancies.csv"
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
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["distributor", "tariff_code", "charge_type", "period", "aer_rate", "published_rate", "diff"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} discrepancies written to {OUT}")


if __name__ == "__main__":
    main()
EOF_FIXTURE
cat > requirements.txt <<'EOF_FIXTURE'
pandas>=2.2
matplotlib>=3.9
EOF_FIXTURE
cat > aer_network_tariffs_2025-26.csv <<'EOF_FIXTURE'
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
cat > ausgrid_price_list_2025-26.csv <<'EOF_FIXTURE'
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
cat > discrepancies.csv <<'EOF_FIXTURE'
distributor,tariff_code,charge_type,period,aer_rate,published_rate,diff
Ausgrid,EA025,energy,peak,24.733,25.043,0.31
Ausgrid,EA225,energy,offpeak,3.874,3.901,0.027
EOF_FIXTURE
cat > explore.ipynb <<'EOF_FIXTURE'
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
    "d = pd.read_csv('discrepancies.csv')\n",
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
