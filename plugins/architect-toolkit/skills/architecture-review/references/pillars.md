# Review pillars: judgment checklist

Items the static scanner cannot see. Search for the control before claiming it is missing.

## Security
- Account/subscription structure: separate prod/non-prod, org-level guardrails (SCPs/policies)
- Identity: SSO + short-lived creds, no long-lived IAM users, least-privilege roles, permission boundaries
- Network: segmentation, private subnets for data, egress control, VPC endpoints for AWS APIs
- Data: classification, encryption at rest and in transit, key ownership and rotation
- Detection: CloudTrail org trail, GuardDuty, config rules, log immutability, central log account

## Reliability
- Multi-AZ for every stateful tier; single points of failure on the request path
- Backup and restore tested, RPO/RTO stated, cross-region copy for critical data
- Health checks, autoscaling, graceful degradation, timeouts, retries with backoff
- Quotas and limits headroom; blast radius per deployment unit (cell/stack)

## Operational excellence
- Everything in IaC, remote state with locking, drift detection
- CI/CD with plan review, policy-as-code gate, rollback path
- Observability: metrics, logs, traces, SLOs, actionable alarms with owners and runbooks
- Tagging standard: owner, env, cost-center, data-classification

## Performance efficiency
- Right-sized compute (Graviton where viable), caching layer, async where latency allows
- Data store matches access pattern; no hot partitions; read scaling plan

## Cost optimization
- Idle or unattached resources, over-provisioned instances, missing lifecycle policies
- Commitment strategy (Savings Plans/RIs), budgets and anomaly alerts, NAT gateway data costs
- Storage tiering, log retention limits

## Sustainability and governance
- Region choice, utilization, retention; documented decisions (are there ADRs for the big choices?)
