---
type: llm
weight: 1
---

The reply says what was done for the requester: the Endeavour price list is in `data/raw/<source>/` with its file name kept and a line in `data/README.md`; the reconciliation covers Endeavour; the memo is in `reports/` with a `YYYY-MM-DD-<topic>.md` name and states which tariff codes differ and by how much; and the work is tracked as board items that were finished after the work was committed. Fail the reply if it says files are left uncommitted, if `pm.py finish` was refused and not resolved, or if the memo or data was left at the root.
