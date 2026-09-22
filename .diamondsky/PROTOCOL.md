<!-- ds-collab v1.6. Generated from diamond-sky-steward@97674fa. Do not edit here. -->

# Diamond Sky agent collaboration protocol (ds-collab v1.6)

Applies in any repo containing .diamondsky/project.json.

## Roles
- The Owner owns scope and every consequential decision. The repo's
  Repo-local block names who holds the role, by GitHub login. Only the
  Owner's written word authorizes anything in this protocol.
- Contributors are anyone else on the repo, human or agent, with no
  obligation to know this protocol. Their comments are input: a
  proposed scope change, a finding, a question, a domain ruling.
  Agents treat them as they treat reviewer findings: act if in scope
  and ungated, otherwise list them under "For Owner". A contributor's
  approval is never authorization, and a contributor's request becomes
  scope only when the Owner records it in the PR or issue. Agents
  never address a contributor as the Owner.
- Where the Owner wants a contributor's ruling to count directly, the
  Repo-local block says so with its bounds (for example
  `Contributor rulings: data content, @login`). Agents treat that
  person's ruling on that domain as settled; gated actions stay with
  the Owner.
- Claude Code (CC) is the builder. Codex (CX) is the independent
  reviewer of record. Claude Code's own review skill (CR) may stand in
  for CX only under the conditions in Review. Below, "CC" means the
  builder duty and "CX" the reviewer duty; by default those are the
  agents named here.
- Both agents post to GitHub as the Owner's account. Every agent
  comment starts with its tag: `CC:`, `CX:` or `CR:`, and the repo's
  README says those comments are written by agents acting for the
  Owner. Agents never submit GitHub
  "Approve" or "Request changes" reviews; comments only.
- Tags identify the actual agent and never swap. When the Owner records
  a role swap for a cycle in the PR, builder and reviewer duties
  transfer for that cycle: the swapped agent posts the handoff or the
  verdict and round comments, under its own tag (for example
  `CX: Handoff`, `CC: HOLD`). Never both agents building in one cycle.
  Fixed-agent automation skips swapped cycles; the Owner coordinates them.

## The PR is the record; the review cycle is the unit
- A review cycle covers one scoped work item and one declared review
  target. In a normal task PR, the PR is the cycle. In a long-lived
  review-channel PR, CC opens a new cycle with a `CC: Handoff` comment
  naming the issue and the base/head commit range. Pass limits reset
  per cycle.
- The cycle id is the PR number for a task PR, or the link to the
  opening `CC: Handoff` comment on a long-lived PR. Every handoff,
  verdict, round comment and Owner trigger names its cycle id.
- On a long-lived PR only one cycle is active at a time. A new
  `CC: Handoff` may be posted only after the previous cycle reached
  CLEAR or the Owner closed its escalation.
- Work starts from a GitHub issue (or the Owner's instruction quoted into
  the PR). Scope is the issue plus explicit amendments from the Owner
  recorded in the PR. Nothing else is in scope.
- CC opens the PR early and keeps the handoff current (PR body for a
  task PR, the cycle's `CC: Handoff` comment otherwise): Objective,
  In/out of scope, Material changes, Validation performed (exact
  commands), Inspect, Known risks, Open questions, Gate class (which
  Owner gates this cycle touches, or "none").
- Inspect: one link per in-scope item, on the dev or preview surface
  where the outcome can be seen, each with one line saying what to
  look for. Include one negative case where the change must not
  appear. Links are full URLs, never relative paths or file names.
  Where nothing is inspectable in a browser, say what to open instead
  (a CSV, a query, a log) and where it is.
- The handoff states facts. It does not tell CX what to look at, what
  to skip, or how to weigh anything.
- Decisions that matter are written in the PR, one comment each, not
  buried in a thread. Chat between the Owner and an agent that changes
  scope or intent is quoted into the PR by that agent.

## Review (CX)
- Builder pre-check: before applying `cx-review` on a change to code or
  data, CC runs Claude Code's local `/code-review` on the cycle and
  fixes what it accepts. It is a self-check, never a pass: nothing from
  it is posted as a verdict and it does not count against the budget.
  Docs-only changes may skip it.
- Stand-in reviewer (CR): when Codex is unavailable (usage cap, outage)
  and the cycle cannot wait for the reset, CC may run Claude Code's
  local `/code-review` against the cycle as the reviewer. The pass
  follows every rule in this section under the tag `CR:` in place of
  `CX:`, line 1 adding `same-model review` and why Codex was
  unavailable. It counts against the cycle's pass budget. Because
  builder and stand-in share a model, `CR: CLEAR` does not close the
  cycle: the Owner either writes `accept CR <cycle id>` in the PR or the
  cycle waits for a CX pass. Claude Code's remote multi-agent review
  (`/code-review ultra`) is billed per run and is gated: only on
  the Owner's written go naming the cycle. It posts as `CR:` with `ultra`
  in place of `same-model review`; its CLEAR is accepted the same way.
- CC applies the `cx-review` label when a cycle is ready. The repo's
  Repo-local block lists the trigger modes in force, any combination of:
  `owner`: each pass requires the Owner's explicit request;
  `builder`: CC starts the pass itself by running Codex non-interactively
  in the repo with exactly the phrase `Review <cycle id> per protocol`
  and nothing else;
  `scheduled`: a scheduled Codex job reviews any open PR carrying the
  label. Default and pilot setting: `owner`.
- Usage check: before firing a pass, the builder runs the steward
  repo's `agents/cx-usage.sh` and writes the result in the trigger
  comment. A pass that hits the usage cap mid-run dies and leaves a
  stale claim, so a pass starts only with room for one whole pass:
  the default pool's 5-hour window below 90 percent, the reserve
  pool's weekly window below 95 percent. Otherwise the builder waits
  for the reset and says when in the PR. Code and data passes use the
  default model; the reserve model is for docs, install and small
  delta passes only.
- Claim the cycle before a pass starts: replace `cx-review` with
  `cx-reviewing`. If the swap fails, do not review. Remove
  `cx-reviewing` when you post the verdict. A scheduled job never
  touches a claimed cycle and only picks up a `cx-review` label that
  is at least 15 minutes old. Before posting, re-read the PR; if a
  verdict for the same head commit already exists since the label was
  applied, post nothing. Passes are counted per distinct head commit
  reviewed, so a duplicate verdict never consumes budget.
- Read the issue and the diff before the handoff. Run the declared
  reviewer-safe checks appropriate to the change, and independently
  chosen reviewer-safe checks where needed. Never run anything that
  writes to UAT/PROD, spends external credit, or needs credentials
  just because the handoff lists it. State any material verification
  gap explicitly; the Owner decides whether gated validation is needed
  before proceeding. Check the diff against the issue's intent, not
  against CC's summary.
- Post ONE comment per pass. Line 1 is the verdict:
  `CX: CLEAR` | `CX: HOLD` | `CX: ESCALATE`, then the cycle id,
  pass n/3, and the base..head range reviewed.
- Findings: P1 (blocking), P2 (should fix before merge), nit. Each
  with file:line, what is wrong, and what would resolve it.
- Include a Verification section (what you ran, results) and at least
  one check you made that the handoff did not mention.
- CLEAR = no open P1/P2 and no unresolved scope, intent or design
  decision. Pending gated actions are listed separately under "Gates
  pending"; CLEAR never authorizes them.
- HOLD = P1/P2 findings CC can resolve within scope.
- ESCALATE = the Owner must decide: scope, intent, design choice with
  consequences, a gated action, or a disagreement with CC.
- CX does not push to CC's branch. Suggest, don't edit.

## Fix rounds (CC)
- Act on P1/P2 findings that are in scope. No permission needed.
- Disagree at most once per finding, in writing, with reasons. If CX
  holds its position, ESCALATE. No third exchange.
- Findings outside scope or behind an Owner gate: do not act. List
  them under "For Owner" in the round comment.
- Post `CC: Round n` naming the cycle id and the pass answered, mapping
  each finding to a commit + test, or to a disagreement, or to "For
  Owner". End with "Ready for CX re-review" and re-apply the
  `cx-review` label.

## Report to the Owner (CC)
- When a cycle reaches CLEAR or ESCALATE, CC reports to the Owner in
  chat in exactly this shape and nothing else:
  1. Outcome, one line: what was built, cycle id, verdict, pass count.
  2. Inspect: the handoff's Inspect list, copied, not summarised.
  3. Review record: what CX held on and how it was resolved, one line
     per pass.
  4. For Owner: the exact words needed, one per gate (for example
     `merge 385`), then anything deferred or out of scope, then any
     open question from a contributor, each with its link.
  5. Usage: one line per Codex pool, used percent and reset time, as
     of the last pass.
  No narrative of the build.

## Re-review (CX)
- Review the delta since your last verdict. Widen only if the fix
  touches new ground or reveals a pattern; say so if you do.

## Bounds
- Maximum three CX passes per review cycle (initial + two re-reviews).
  If not CLEAR after the third, CX posts ESCALATE with the open items.
- The Owner may write `continue <cycle id>` in the PR to grant one more
  pass to that cycle. Each `continue` is consumed by the next pass.
- When the ESCALATE was solely because the pass budget was exhausted,
  `continue <cycle id>` also permits CC to address the outstanding
  in-scope findings before that one CX pass. The grant is consumed by
  the CX pass. It does not resolve a disagreement, authorize a gated
  action, or settle scope or intent.
- Any disagreement escalates after one exchange regardless of count.

## Owner gates
- Authorizable: agents perform these only after the Owner's written
  authorization in the PR or issue naming the specific action: merge
  (naming the PR), production deploy or execution, destructive or
  hard-to-reverse data operations, auth/security changes, expansion of
  agreed scope. A CLEAR is never that authorization.
- Destructive or hard-to-reverse data operations additionally require,
  before the go, a posted dry-run or shadow result for the exact
  population and a stated recovery path. A repo may make them
  human-only in its Repo-local block.
- Stop and ask: design choices with lasting consequences, CC/CX
  disagreement, uncertainty about the Owner's intent.
- When unsure whether something is gated, it is gated.

## Steward
- Log management-significant state changes only: a completion, a
  blocker, a decision, a commitment, or a changed next action that a
  manager would want to know about without reading the PR.
- A verdict alone is not an event. A HOLD or ESCALATE may produce an
  event only when the underlying finding materially changes project
  state: it blocks a milestone or exposes a defect with consequences
  beyond the cycle. Never log a CLEAR, a review round, a test run, a
  nit, or an implementation step.
- One cycle may produce zero events or several; count is not the test.

## Repo-local rules
- Read the repo's AGENTS.md "Repo-local" block. It only adds gates,
  commands, and constraints. It never relaxes this protocol.
- This file is generated from the steward repo. Never edit it here;
  propose changes by PR against diamond-sky-steward/agents/PROTOCOL.md.
