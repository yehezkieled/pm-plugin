---
type: llm
weight: 1
---

The final reply reports the walk test in both halves. It must state the `pm.py walk` result and, separately, the cold walk: one line per cold-walk question (where am I and where to go for the common task, whether a contract or card names its inputs and outputs, whether status can be read from files, whether a routing file carries content or a fact sits in two places), each naming the file opened and the answer. Fail the reply if it reports only the `pm.py walk` result, says the cold walk was skipped or left for later, or gives no cold-walk answers.
