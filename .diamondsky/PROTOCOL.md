<!-- ds-collab v1.1. Generated from diamond-sky-steward@c8debbc. Do not edit here. -->

# Diamond Sky agent collaboration protocol (ds-collab v1.1)

Applies in any repo containing .diamondsky/project.json.

## Roles
- George owns scope and every consequential decision.
- Claude Code (CC) is the builder. Codex (CX) is the independent
  reviewer. Below, "CC" means the builder duty and "CX" the reviewer
  duty; by default those are the agents named here.
- Both agents post to GitHub as George's account. Every agent comment
  starts with its tag: `CC:` or `CX:`. Agents never submit GitHub
  "Approve" or "Request changes" reviews; comments only.
- Tags identify the actual agent and never swap. When George records
  a role swap for a cycle in the PR, builder and reviewer duties
  transfer for that cycle: the swapped agent posts the handoff or the
  verdict and round comments, under its own tag (for example
  `CX: Handoff`, `CC: HOLD`). Never both agents building in one cycle.
  Fixed-agent automation skips swapped cycles; George coordinates them.

## The PR is the record; the review cycle is the unit
- A review cycle covers one scoped work item and one declared review
  target. In a normal task PR, the PR is the cycle. In a long-lived
  review-channel PR, CC opens a new cycle with a `CC: Handoff` comment
  naming the issue and the base/head commit range. Pass limits reset
  per cycle.
- The cycle id is the PR number for a task PR, or the link to the
  opening `CC: Handoff` comment on a long-lived PR. Every handoff,
  verdict, round comment and George trigger names its cycle id.
- On a long-lived PR only one cycle is active at a time. A new
  `CC: Handoff` may be posted only after the previous cycle reached
  CLEAR or George closed its escalation.
- Work starts from a GitHub issue (or George's instruction quoted into
  the PR). Scope is the issue plus explicit amendments from George
  recorded in the PR. Nothing else is in scope.
- CC opens the PR early and keeps the handoff current (PR body for a
  task PR, the cycle's `CC: Handoff` comment otherwise): Objective,
  In/out of scope, Material changes, Validation performed (exact
  commands), Known risks, Open questions, Gate class (which George
  gates this cycle touches, or "none").
- The handoff states facts. It does not tell CX what to look at, what
  to skip, or how to weigh anything.
- Decisions that matter are written in the PR, one comment each, not
  buried in a thread. Chat between George and an agent that changes
  scope or intent is quoted into the PR by that agent.

## Review (CX)
- CC applies the `cx-review` label when a cycle is ready. The trigger
  mode is set in the repo's Repo-local block: `george` (default, and
  the pilot setting): the label records readiness only and each pass
  requires George's explicit request; `label`: the label itself starts
  the pass. Remove the label when you post your verdict.
- Read the issue and the diff before the handoff. Run the declared
  reviewer-safe checks appropriate to the change, and independently
  chosen reviewer-safe checks where needed. Never run anything that
  writes to UAT/PROD, spends external credit, or needs credentials
  just because the handoff lists it. State any material verification
  gap explicitly; George decides whether gated validation is needed
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
- ESCALATE = George must decide: scope, intent, design choice with
  consequences, a gated action, or a disagreement with CC.
- CX does not push to CC's branch. Suggest, don't edit.

## Fix rounds (CC)
- Act on P1/P2 findings that are in scope. No permission needed.
- Disagree at most once per finding, in writing, with reasons. If CX
  holds its position, ESCALATE. No third exchange.
- Findings outside scope or behind a George gate: do not act. List
  them under "For George" in the round comment.
- Post `CC: Round n` naming the cycle id and the pass answered, mapping
  each finding to a commit + test, or to a disagreement, or to "For
  George". End with "Ready for CX re-review" and re-apply the
  `cx-review` label.

## Re-review (CX)
- Review the delta since your last verdict. Widen only if the fix
  touches new ground or reveals a pattern; say so if you do.

## Bounds
- Maximum three CX passes per review cycle (initial + two re-reviews).
  If not CLEAR after the third, CX posts ESCALATE with the open items.
- George may write `continue <cycle id>` in the PR to grant one more
  pass to that cycle. Each `continue` is consumed by the next pass.
- When the ESCALATE was solely because the pass budget was exhausted,
  `continue <cycle id>` also permits CC to address the outstanding
  in-scope findings before that one CX pass. The grant is consumed by
  the CX pass. It does not resolve a disagreement, authorize a gated
  action, or settle scope or intent.
- Any disagreement escalates after one exchange regardless of count.

## George gates
- Authorizable: agents perform these only after George's written
  authorization in the PR or issue naming the specific action: merge
  (naming the PR), production deploy or execution, destructive or
  hard-to-reverse data operations, auth/security changes, expansion of
  agreed scope. A CLEAR is never that authorization.
- Destructive or hard-to-reverse data operations additionally require,
  before the go, a posted dry-run or shadow result for the exact
  population and a stated recovery path. A repo may make them
  human-only in its Repo-local block.
- Stop and ask: design choices with lasting consequences, CC/CX
  disagreement, uncertainty about George's intent.
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
