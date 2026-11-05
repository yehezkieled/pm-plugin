---
type: llm
weight: 1
---

The reply names the project's shape as analysis (possibly with a second shape) and shows or summarises the `## Where things go` table as one row per kind of thing (raw data, generated outputs, deliverables, code, exploration), not one row per file. It lists the files it moved out of the root: the two source CSVs into `data/raw/<source>/`, the generated `discrepancies.csv` into `out/` (or removed from Git as an output `recon.py` now writes there), the script into a code folder with its paths updated, the notebook into `notebooks/`, and the notes into a place the table names. Fail the reply if source data or generated output is still at the root without a stated reason, or if it says the moves are waiting on a yes the prompt already gave.
