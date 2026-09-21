# Rollback Plan

1. Disable scheduler and outbound alerts.
2. Revert the PR or redeploy the previous immutable image/tag.
3. Keep the database read-only for incident analysis.
4. Restore the prior model/config version.
5. Validate provider health and API contract.
6. Document cause, affected snapshots and corrective action.
