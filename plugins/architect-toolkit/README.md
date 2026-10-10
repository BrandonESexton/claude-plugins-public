# architect-toolkit

Two Claude Code skills and one agent for architecture work that has to survive scrutiny.

| Component | What it does |
|---|---|
| `adr-studio` skill | Interviews you, builds weighted criteria, scores options with a rationale for every score, runs a deterministic sensitivity analysis, drafts an ADR with a Mermaid diagram |
| `adr-challenger` agent | Adversarial pre-mortem on the draft: top failure modes, steelman of the runner-up, scoring audit |
| `architecture-review` skill | Static scan of Terraform and CloudFormation plus a Well-Architected style judgment pass, rendered as a self-contained HTML report |

## Design principles
- **Math is code, not vibes.** Scoring and scanning run in stdlib-only Python scripts, so results are reproducible. The model supplies judgment and prose.
- **Evidence or it does not go in.** Every score has a stated reason; every finding has a file, line, and quoted evidence. Assumptions are flagged and counted.
- **Robustness is reported.** A decision that flips under a 30% weight change is called fragile, not winner.
- **Humans approve.** ADRs are written as `Proposed`; the review skill reports and never edits the reviewed code.

## Try it in two minutes
```
# 1. Sensitivity-tested decision matrix
python3 skills/adr-studio/scripts/score_matrix.py examples/message-broker.json

# 2. Scan deliberately flawed infrastructure and render a report
python3 skills/architecture-review/scripts/iac_scan.py examples/sample-infra --out findings.json
python3 skills/architecture-review/scripts/render_report.py findings.json --title "Sample Review" --out review.html
```
Pre-rendered outputs: [examples/sample-adr.md](examples/sample-adr.md), [examples/sample-review.html](examples/sample-review.html).

In Claude Code, ask naturally ("write an ADR for choosing a message broker", "review the Terraform in ./infra") or use the skill names.

## Scanner coverage (v0.1)
Security groups, S3, RDS, EBS, IAM wildcards, EC2 IMDSv2 and public IPs, load balancer TLS and logging, CloudTrail, tagging. Heuristic, regex-based: confirm High and Critical findings in code. Not a replacement for tfsec, Checkov, or cfn-lint; it pairs with them and adds the judgment layer.

## Roadmap
Azure and GCP rule packs, Checkov/tfsec output ingestion, C4 diagram generation from the inventory, ADR index and supersession tracking.

## Requirements
Python 3.8+. No dependencies.
