Goal: goal-20260515-5day-auto-improve-runtime

Build and operate a five-day bounded auto-improve goal runtime with clean release evidence, private GitHub baseline, resumable audit trail, heartbeats, checkpoints, and no promotion until sealed authority is clean.

PROMOTION BAN: do not promote, release, or claim a learning improvement.
Promotion remains forbidden until can_promote_result=true and sealed authority clean pass are both current.
Reason: Promotion remains forbidden until can_promote_result=true and sealed authority clean pass are both current..

Execution ladder:
- 30-minute-trial: max_minutes=30, max_proposals=1
- 6-hour-ramp: max_minutes=360, max_proposals=6
- 2-day-candidate: max_minutes=2880, max_proposals=24
- 5-day-sustained: max_minutes=7200, max_proposals=60

Stop immediately on:
- allowed-root violation
- repeated blocker cannot be converted to remediation backlog
- status, audit, or heartbeat write failure
- sealed authority or readiness regression
- any need to bypass release, promotion, or learning-claim gates
