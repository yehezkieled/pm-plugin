# ICM inside pm

ICM (Interpretable Context Methodology) treats a repository's folders as the agent's architecture: small routing files point at shelves, each working folder states its own contract, and plain files are the state. The pm skills apply it at the right moments, so a project needs only the `/pm:*` commands.

| File | What it holds | Read by |
| --- | --- | --- |
| [method.md](method.md) | The invariants, the two kinds of project, the restructure gate, the walk test, Verify, fixing the source | `/pm:init`, `/pm:map` |
| [workflow.md](workflow.md) | Building a workflow as ICM stages that package as a Claude skill | `/pm:init` for a workflow project |
| [system-map.md](system-map.md) | The System map in `docs/pm/map/`: slices, cards, change impact | `/pm:map` |
| [reference-integrity.md](reference-integrity.md) | Moving files safely: referrers, case-folded collisions, parity | any skill that moves files |
| [core.md](core.md) | Principles, the five context layers, contract format, naming, token budget | when a structural call is contested |
| [forms.md](forms.md) | The six ICM forms, for a workflow whose unit is not a run | `/pm:init`, rarely |
| [templates/](templates/) | Copyable starters for catalogs, contracts, and cards | the skills, when they write those files |

`scripts/pm_icm.py` runs the mechanical half of the walk test (`pm.py walk`), rebuilds the map's card index (`pm.py index`), and checks references before a move (`pm.py refs`).

## Credit

Method: Jake Van Clief and David McDermott, *Interpretable Context Methodology: Folder Structure as Agent Architecture*, [arXiv:2603.16021](https://arxiv.org/abs/2603.16021). The files here are adapted from [icm-architect](https://github.com/RinDig/icm-architect) (MIT, © 2026 Jake Van Clief; commit `e16cafe`) and the [Interpretable Context Methodology](https://github.com/RinDig/Interpretable-Context-Methodology) repository (MIT, © 2026 Model Workspace Protocol Contributors; commit `02ba5d8`). Both license notices are in [LICENSE](LICENSE). The adaptations fit ICM to pm's board, its placement rules, and Claude skill packaging; where pm and ICM disagreed, the rule chosen is in [docs/placement.md](../docs/placement.md).
