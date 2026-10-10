---
name: architecture-review
description: "Reviews infrastructure as code (Terraform, CloudFormation, CDK output) and architecture descriptions against Well-Architected style pillars. Runs a deterministic static scan for hard evidence, adds judgment-based findings the scanner cannot see, ranks by severity, proposes remediations, and renders a self-contained HTML report. Use when the person asks to review an architecture, audit a landing zone or Terraform repo, check IaC for security or reliability gaps, do a Well-Architected review, or invokes /architecture-review."
---

# Architecture Review

Two layers: a scanner that finds provable issues in code, and your judgment on the things only a human architect notices (missing multi-AZ story, blast radius, no DR plan, account structure). Findings must be traceable to evidence; opinions are labeled as such.

## Workflow

1. **Scope.** Confirm the target path (default: current directory), the cloud, and the workload tier (prototype, internal, production, regulated). Severity is judged against the tier. Ask only if unclear.
2. **Scan.**
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/architecture-review/scripts/iac_scan.py <path> --out findings.json
   ```
   Covers Terraform (`.tf`), CloudFormation (`.yaml/.yml/.json` with `AWSTemplateFormatVersion` or `Resources`). Each finding has a rule id, pillar, severity, file, line, and resource. The scanner is regex and structure based, so treat its output as strong leads, and open the file to confirm any High or Critical finding before reporting it.
3. **Judgment pass.** Read the inventory the scanner prints (resource counts by type) and the code. Using `references/pillars.md`, add findings the scanner cannot detect. Mark them `"source": "review"` and give the evidence you did see (or the absence you checked for). Never assert a gap exists without searching for the control first.
4. **Prioritize.** Rank by severity, then by blast radius, then by fix effort. Group into: fix now (Critical/High), plan (Medium), note (Low/Info). Cap the executive summary at five bullets.
5. **Report.**
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/architecture-review/scripts/render_report.py findings.json --title "<System> Architecture Review" --out review.html
   ```
   Then summarize in chat: counts by severity, top 3 risks, and the path to the HTML.
6. **Offer follow-ups.** For any significant design gap, offer to start `adr-studio` so the remediation choice gets a recorded decision.

## Findings JSON shape
```json
{"findings": [{"id": "SEC-S3-001", "pillar": "Security", "severity": "High",
  "title": "S3 bucket allows public ACL", "file": "s3.tf", "line": 12,
  "resource": "aws_s3_bucket.logs", "evidence": "acl = \"public-read\"",
  "remediation": "Set acl private and add aws_s3_bucket_public_access_block.",
  "source": "scanner"}], "inventory": {"aws_s3_bucket": 3}}
```
Severities: Critical, High, Medium, Low, Info.

## Rules
- Evidence or it does not go in. Quote the line.
- Do not modify the reviewed code unless asked. This skill reports.
- Redact secrets in evidence (show the key name, never the value).
- No em dashes in output.
