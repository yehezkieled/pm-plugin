# {NN}_{stage-name}: {the job in five words}

One job: {the single thing this stage does}.

## Inputs

- Working (this run): `runs/{run}/{previous stage folder}/{file}`; the previous stage's real folder name, so renumbering means editing this path.
- Reference (every run): [{rules file}](../../_shared/{rules-file}.md)
- Reference (every run): [{stage guide}](references/{guide}.md)

Do not load: {what an eager agent would wrongly pull in: other stages' references, earlier runs, the whole _shared folder}.

## Process

1. {Read the inputs.}
2. {Transform them, following the reference constraints.}
3. {Hard limits worth restating: length, count, format.}

## Outputs

- `runs/{run}/{NN}_{stage-name}/{artifact}.md`

## Verify

Before the human check, re-read {the earlier output or input to compare against, by path} and check {what must still match}. List each mismatch at the top of the output instead of smoothing it over.

## Human check

{One concrete act: read it aloud, check the numbers against X, confirm the order survived. Edit the output in place; the next stage reads whatever is there.}
