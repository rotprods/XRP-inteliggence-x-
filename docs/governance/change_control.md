# Change-Control Workflow

## WIP limits

- one active implementation branch;
- one open pull request;
- one CI workflow during foundation recovery;
- zero scheduled workflows before shadow mode;
- zero auto-merge.

## Standard change

1. Lock initial state and acceptance criteria.
2. Implement and test locally.
3. Run compile, tests, coverage, lint, type, security, repository and build gates.
4. Update `STATE.md`, `TASKS.md`, `DECISIONS.md` and `CHANGELOG.md` as required.
5. Commit atomically and generate a source manifest.
6. Push once to a clean branch.
7. Open one draft PR with evidence and rollback.
8. Run the bounded manual workflow.
9. Read back the remote tree and compare it with the local manifest.
10. Merge only after review and green evidence.

## Emergency change

An emergency change may shorten review latency but may not skip local reproduction, tests,
rollback or the read-only boundary. It must be followed by a post-incident review.

## Prohibited change mechanisms

- workflows that author implementation code;
- recursive workflow dispatch;
- remote trial-and-error loops;
- force-push to `main`;
- self-merging agents;
- silent model-weight changes;
- direct commits of generated databases, secrets or licensed datasets.
