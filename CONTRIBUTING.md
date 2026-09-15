# Contributing

## Change contract

1. Read `GOAL.md`, `STATE.md`, `TASKS.md`, `DECISIONS.md` and `AGENTS.md`.
2. Reference one or more task IDs.
3. Declare one primary objective, acceptance criteria and explicit non-goals.
4. Implement locally with tests beside the changed behavior.
5. Run `make check` and preserve the evidence.
6. Update state, decisions, task status and changelog when semantics change.
7. Use conventional, atomic commits.
8. Open one bounded draft PR with rollback instructions.

## WIP limits

During alpha recovery:

- implementation branches: maximum 1;
- open implementation PRs: maximum 1;
- GitHub workflows: exactly 1, manual only;
- scheduled workflows: 0;
- workflow-authored commits: prohibited;
- auto-merge: prohibited.

## Definition of done

A task is complete only when code, tests, executed evidence, commit SHA, remote tree verification, state update and rollback path all exist. A submitted operation is not completion until the resulting state is read back and verified.
