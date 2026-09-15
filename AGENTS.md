# AGENTS.md

## Diamond Sky Steward

This repository is Steward-enabled. Read `.diamondsky/project.json` for the
permitted project IDs (here: `mim-plus`, the MIM+ Phase 1 Pilot — EO-GOS is a
workstream of that project, not a project of its own). Before substantial
work, read recent relevant Steward activity (`recent_events`). Log management-significant
state changes only (`log_event`): a completion, a blocker, a decision, a
commitment, or a changed next action a manager would want to know about
without reading the work. A review verdict alone is never an event. Never log
CLEARs, review rounds, test runs, routine implementation steps, exploration,
or chatter. Never log against a project not
permitted by `.diamondsky/project.json`; if attribution is uncertain, do not
log.

## Diamond Sky agent protocol (ds-collab v1.1)

Read `.diamondsky/PROTOCOL.md` before building or reviewing. Minimum
rules if you read nothing else: Claude Code builds, Codex reviews, the PR
is the record, every agent comment starts with `CC:` or `CX:`. Review
verdicts are CLEAR / HOLD / ESCALATE; CLEAR never means merge or deploy.
At most three reviewer passes per review cycle, then ESCALATE. Agents
merge, deploy, run production actions, change auth, or expand scope only
after George has authorized that specific action in the PR or issue.
Unsure means gated.
`.diamondsky/PROTOCOL.md` is generated from diamond-sky-steward; never
edit it here.

## Repo-local
- Review trigger: george (pilot)
- Gates in addition to the protocol: any ESA imagery change (background removal is banned; every ESA image
  carries the ESA-Standard-Licence notice), publishing or removing any asset
  with licensing consequences (`ASSET-LICENSING.md` is binding), and any
  change to `ATTRIBUTIONS.csv` rows beyond the task
- Tests the reviewer must run: `python3 tools/check_index.py` and `python3 -m pytest tools/test_gates.py`
- Conventions: branch naming `feat/`, `fix/`, `chore/`, `docs/`, `design/`;
  squash merge on George's written go; delete the remote branch right after
  merge or close; parallel sessions use `.claude/worktrees/`, never two
  sessions writing one checkout
