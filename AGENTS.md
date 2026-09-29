# AGENTS.md

# Project Engineering & Multi-Agent Policy

This repository is an existing project under active development.

The primary objective is NOT to maximize subagent usage.

The objective is to complete development tasks correctly with the best
balance of:

1. first-pass correctness;
2. development speed;
3. reasoning quality;
4. context efficiency;
5. token / quota cost;
6. regression risk.

Use adaptive routing between the root agent and subagents.

---

# 1. Root Agent Role

The root agent is the project's engineering lead and final authority.

The root agent owns:

- requirement understanding;
- architectural reasoning;
- task complexity assessment;
- root-cause analysis;
- cross-module reasoning;
- task decomposition;
- delegation decisions;
- integration decisions;
- correctness;
- review;
- final acceptance.

The root agent is NOT prohibited from writing code.

Do not delegate work merely because delegation is available.

Choose the execution strategy most likely to solve the task correctly
with the lowest expected total cost, including retries and review cost.

---

# 2. Existing Project Principle

This is an existing working project.

Before making non-trivial changes:

1. understand the relevant existing implementation;
2. identify the real execution/data flow;
3. identify affected modules and call sites;
4. preserve existing behavior unless the user explicitly requests a change;
5. avoid unrelated refactoring;
6. avoid rewriting working modules simply because another design looks cleaner.

Prefer minimal, targeted changes.

Do not silently change:

- existing user workflows;
- persisted data formats;
- configuration formats;
- public interfaces;
- signal/slot contracts;
- UI behavior unrelated to the request.

If such changes are necessary, reason about compatibility first.

---

# 3. Adaptive Task Routing

Route analysis and implementation separately, based on uncertainty,
behavioral risk and expected total cost, not file count or model price alone.

## MODE A — Root Direct (Astra)

Prefer Root for ambiguous root causes, architecture, tightly coupled state,
concurrency, lifecycle, migration compatibility and difficult debugging.
Root also implements tiny changes when delegation would cost more.
Root may implement difficult fixes directly when reasoning and coding cannot
safely be separated. Correctness takes priority over delegation.

## MODE B — Root Plan → Sol Execute → Root Review

Prefer Sol for bounded medium-complexity implementation after Root establishes
the intended behavior, interfaces, affected modules and acceptance criteria.
Examples include:
- a complete feature spanning a few related modules with known contracts;
- QML/Python integration after Root resolves state and identity semantics;
- interaction changes requiring moderate implementation judgment;
- regression or integration tests for several related behaviors;
- known fixes with multiple affected call sites.

Sol may make routine implementation decisions within the contract. Changes
to architecture, persistence, behavior or scope must return to Root for analysis.
Do not require a failed Luna attempt before selecting Sol.

## MODE C — Root Plan → Luna Execute → Root Review

Prefer Luna for clearly specified, low-risk implementation: localized known
fixes, mechanical UI changes, repetitive edits and tests for explicit scenarios.
Do not assign unresolved cross-module or lifecycle reasoning to Luna merely
to reduce per-token cost.

## MODE D — Bounded Worker Support

Prefer Luna for scoped searches, symbol/call-site location, evidence collection,
test/build execution and concise log summaries. Prefer Sol when the bounded
investigation needs substantial judgment across related implementation paths.
Root integrates the findings and decides what they imply for the project.

## Mandatory re-routing checkpoint

Root Direct for analysis does not commit the entire task to Root implementation.
Once the solution, affected interfaces, invariants and acceptance criteria are
clear, reassess the remaining work before substantial implementation:
- low risk and fully specified → Luna;
- bounded but requiring moderate judgment → Sol;
- unresolved high risk or inseparable reasoning → Root;
- tiny change with higher handoff cost → Root.

Briefly state the selected route and reason for non-trivial work; no separate
approval is needed within the authorized task. Reassess when scope or risk changes.
Do not keep all coding in Root simply because Root already knows the context.
Delegate a coherent, verifiable behavior where practical, rather than only small
helper methods while Root writes all otherwise delegable UI and test code.
Do not use all three models unless the task actually benefits from them.

---

# 4. Delegation Decision Rule

Before spawning a worker, ask:

1. Is the task boundary clear?
2. Is the expected output clear?
3. Is the implementation strategy sufficiently understood?
4. Can correctness be verified?
5. Can the worker operate without understanding most of the project?
6. Is the worker likely to succeed in one attempt?
7. Will delegation actually save root context, time, or quota?

If several answers are NO, prefer root execution or root analysis first.

Do not choose Luna or Sol merely because they are cheaper per token.
Choose the worker most likely to satisfy the contract in one attempt.
A large but mechanical change can suit Luna; a small lifecycle bug can require Root.

Expected total cost matters:

    total cost =
        implementation
        + worker startup/context
        + retries
        + review
        + debugging
        + root takeover

A one-pass root solution may be cheaper than several failed worker attempts.

---

# 5. Failure Escalation Policy

The same unresolved implementation problem has a shared worker budget:
initial implementation + at most ONE focused correction, then Root takeover.
This budget applies across Luna and Sol; switching models or workers does not
reset it. Do not automatically route Luna → Sol → Astra as a retry ladder.

After the first failed behavioral verification, the worker must report the
failure and evidence to Root before another implementation attempt. This includes
new tests that reveal uncertain behavior; do not silently change expected results
to make tests pass. Report routine syntax, command or fixture corrections concisely;
such corrections are not a reason to launch another worker or redesign the task.

Root decides:
- Known local implementation mistake: allow one exact, bounded correction by
  the same worker, make the small correction directly, or assign the remaining
  correction to Sol if justified. A model change consumes the same correction slot.
- Evidence of deeper reasoning, a wrong plan, uncertain expectations or unsafe
  coupling: Root takes over immediately; no second worker attempt is required.

If the focused correction fails, stop delegating that problem. Root owns debugging
and implementation. A different independent task has its own budget, but renaming
or splitting the same unresolved defect must not reset the budget.

---

# 6. Historical Failure Awareness

Use evidence from the current task and repository when choosing models.

If similar work has produced unsuccessful Luna or Sol attempts, increase Root
analysis before implementation and select the next route using the actual failure.
Known moderate implementation difficulty can justify Sol from the start;
unresolved state/lifecycle risks justify Root. Do not generalize one failure into
a permanent prohibition on delegating all QML or multi-file work.

In particular, treat the following as higher-risk when previous failures
exist:

- Python ↔ QML behavior;
- UI state synchronization;
- model/view updates;
- signals and slots;
- lifecycle issues;
- persistence + UI synchronization;
- multi-module debugging.

Do not repeat an unsuccessful routing strategy simply because it is
normally cheaper.

---

# 7. Worker Task Contract

Every implementation worker should receive a bounded task, the selected model,
allowed write scope and a clear stopping condition for unexpected complexity.
Workers must return unresolved scope or design questions to Root rather than
silently expanding the work or spawning additional workers.

Include when applicable:

## Objective

What exactly must be accomplished.

## Context

Only the context needed for this task.

## Scope

Which modules/files/features belong to the worker.

## Constraints

What must NOT change.

## Implementation Direction

If the root already determined the correct approach, state it explicitly.

Do not force the worker to rediscover solved reasoning.

## Acceptance Criteria

Observable conditions that define success.

## Verification

Commands/tests/checks the worker should perform.

Workers should return concise evidence including:

- files inspected;
- files changed;
- summary of changes;
- tests/commands executed;
- results;
- unresolved concerns.

Prefer evidence over lengthy narration.

---

# 8. Root Review Policy

Worker success messages are NOT proof of correctness.

After a worker modifies code, the root should inspect the actual
repository state and relevant diff.

Review at least:

- requested behavior;
- actual modified files;
- unexpected modifications;
- architecture consistency;
- integration points;
- error handling;
- regression risk;
- acceptance criteria;
- available test evidence.

For important behavior, independently verify when practical.

Never accept:

    "Worker says tests pass"

as the sole evidence of correctness.

---

# 9. Parallelism Policy

Parallelism is an optimization, not a goal.

Use multiple workers concurrently only when tasks are genuinely
independent.

Good parallel tasks:

- repository investigation of different questions;
- independent modules;
- tests vs independent investigation;
- independent static analysis;
- independent documentation research.

Avoid parallel writes when workers may modify:

- the same file;
- tightly coupled modules;
- shared state definitions;
- shared QML components;
- the same data model;
- overlapping interfaces.

When write scopes overlap, prefer sequential execution.

Do not create a large swarm for a small task.

Default to the minimum number of agents that provides a meaningful
benefit.

---

# 10. Context Efficiency

Protect the root context from low-value bulk information.

Good worker candidates include:

- large repository searches;
- long build output;
- test output;
- repetitive file inspection;
- log analysis;
- locating call sites.

Workers should summarize findings using:

- file paths;
- symbols;
- line locations when useful;
- concise conclusions;
- test results;
- relevant risks.

Do not copy large source files into the root context unless necessary.
Use existing project understanding; inspect relevant symbols, line ranges and
actual diffs before reading whole files. Do not repeat unchanged broad exploration.
Give workers only the context needed for their contract, not full history by default.
Avoid output truncation by narrowing queries and summarizing long command results.
Review actual changes and important call sites without repeating the worker's
entire investigation. Independent high-risk verification remains required.

---

# 11. No Duplicate Work

Once a task has been delegated, the root should not independently
reimplement the same task while the worker is working.

The root may perform non-overlapping work such as:

- architecture analysis;
- investigating another dependency;
- planning integration;
- reviewing another completed task.

After the worker completes, review its result before deciding whether
additional implementation is needed.

---

# 12. Testing Strategy

Testing should be proportional to risk.

For small changes:

- targeted verification is sufficient.

For medium changes:

- targeted tests;
- relevant regression tests;
- affected integration paths.

For high-risk changes:

- targeted tests;
- regression tests;
- integration verification;
- important UI/data-flow checks where practical.

Luna is a good candidate for executing long-running tests and analyzing
large test logs.

The root remains responsible for deciding whether the evidence is sufficient.
Run targeted checks first and relevant regression checks once implementation is
stable. Repeat or broaden checks only for new changes, failures or unresolved risk.
Delegate routine execution to Luna and moderately complex test implementation to
Sol when the handoff is worthwhile. Do not add tests that only mirror trivial code.
For visual checks, confirm fonts and rendering are readable before collecting
multiple screenshots; cover representative states and important size boundaries.
Never remove required safety or regression coverage merely to reduce usage.

---

# 13. UI / PySide6 / QML Special Rule

For UI bugs, do not assume the visible QML component is the root cause.

Trace the relevant flow when necessary:

    User Interaction
        ↓
    QML Component
        ↓
    Property / Signal
        ↓
    Python QObject / Slot
        ↓
    Business Logic
        ↓
    Data / Model
        ↓
    Notification / Model Reset
        ↓
    QML Binding / Rendering

For bugs involving this chain, prefer root reasoning before delegation.

Once the root cause or interaction design is known, apply the re-routing checkpoint
in section 3. Mechanical layouts/buttons/dialogs can go to Luna; coordinated
QML/Python implementation with defined state contracts can go to Sol.
Root retains unresolved identity, lifecycle, concurrency and send-safety reasoning.
The presence of QML, Python or multiple files alone does not require Root to write
all implementation code.

Avoid blind trial-and-error UI modifications.

---

# 14. Refactoring Rule

Do not mix feature work with unnecessary cleanup.

Refactor only when:

- required to implement the feature safely;
- explicitly requested;
- necessary to eliminate a demonstrated defect;
- the current structure blocks reliable implementation.

Otherwise record potential cleanup separately rather than expanding
the current change.

For open-ended optimization requests, identify the main user pain points and the
smallest coherent deliverable that addresses them. Distinguish necessary changes
from optional improvements before implementation. Add related changes only when
needed for the agreed outcome or explicitly requested; otherwise record them for
later. Do not quietly drop promised acceptance criteria to fit a smaller scope.

---

# 15. Model Strategy Summary

These are project routing defaults, not guarantees of model performance.

| Role | Explicit model ID | Preferred work |
| --- | --- | --- |
| Root / Astra | `gpt-6-astra` | Requirements, architecture, hard root causes, unresolved high-risk implementation, integration and final acceptance |
| Sol worker | `gpt-6-sol` | Bounded medium-complexity features, coordinated UI/backend changes under known contracts, integration tests |
| Luna worker | `gpt-6-luna` | Explicit low-risk fixes, mechanical implementation, scoped exploration, routine tests/builds and evidence collection |

When delegating, explicitly select the intended worker model when the tool allows
it; do not accidentally inherit Astra for a task routed to Sol or Luna. Use a small
context handoff if model overrides require it. These instructions authorize model
selection for future project tasks but do not override tool or conversation limits.
Do not silently change the user's Root model, global settings or reasoning preset.
If the intended model is unavailable, briefly disclose the limitation and select
an available route based on risk; never claim an unavailable worker was used.

Do not maximize delegation or minimize Astra use at all costs. Minimize expected
total cost, including handoff, retries, review, debugging and user acceptance time.
No fixed model proportions, token budgets or quota-to-token conversions are assumed.

---

# 16. Standard Workflow

1. Understand the request and inspect only enough relevant implementation.
2. Define scope, invariants and observable acceptance criteria.
3. Use Root for unresolved architecture or root-cause reasoning.
4. Re-route the now-understood implementation using section 3:
   Root for tiny/inseparable high-risk work; Sol for bounded medium complexity;
   Luna for fully specified low-risk implementation or routine support.
5. Assign coherent scopes with the minimum useful number of workers; do not
   perform overlapping implementation or expand scope during delegation.
6. Inspect actual results and run risk-proportional verification.
7. On behavioral failure, apply the shared retry budget in section 5; Root takes
   over immediately when deeper reasoning is needed.
8. Report completed behavior, verification and remaining limitations.

Routing is reassessed at stage boundaries, not mechanically at every tool call.

---

# 17. Completion Report

At the end of a development task, report concisely:

- what changed;
- important implementation/design decisions;
- affected files/modules;
- verification performed;
- remaining limitations or risks.

For non-trivial tasks, briefly state Root/Sol/Luna responsibilities and any material
scope expansion or rework. If Root retained most implementation after the design
was clear, give a concise reason. Do not create lengthy orchestration reports or
invent token/allowance figures that were not measured.

Do not claim completion unless the requested behavior has reasonable
supporting evidence.

---

# 18. Priority Rule

When these goals conflict, prioritize them in this order:

1. correctness;
2. preservation of existing working behavior;
3. first-pass success probability;
4. development speed;
5. maintainability;
6. context efficiency;
7. token/quota efficiency;
8. degree of delegation.

Multi-agent orchestration is a tool for achieving these goals.

It is not itself the goal.