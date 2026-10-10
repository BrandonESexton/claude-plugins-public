# saas-migration-planner

Plans migrations between SaaS platforms from the one thing that actually decides whether they succeed: the inventory of integrations and dependencies.

| Pack | Example moves | Typical killers it checks for |
|---|---|---|
| `idp` | Entra ID <-> Okta | Two provisioners fighting over one app, NameID mismatches, conditional access that does not port, MFA re-enrollment, Graph API consumers, the tenant that cannot be deleted |
| `hris` | Workday -> Rippling | Payroll and benefits calendars, YTD balances, worker ID continuity, carrier files, effective-dated history, I-9 retention, orphaned integrations |
| `mdm` | Jamf Pro <-> Kandji | One-MDM-at-a-time gap, FileVault key escrow, Activation Lock, SCEP certificates, EDR approvals, login-window tooling, ABM reassignment |

## What it does
1. Interviews you, then tells you exactly which exports to pull to build the inventory.
2. Validates the inventory (unknown types, missing dependencies, cycles).
3. Scores every integration 0-100 from integration type, business criticality, affected users, target support, dated constraints, and how many other things depend on it. Every score lists its drivers.
4. Sequences waves: dependencies first, a low-risk pilot, high-risk items last with gating, freeze windows skipped, payroll and benefits held for a quarter start.
5. Separates items with no target support as decisions instead of hiding them in a wave.
6. Produces cutover checklists, rollback, a communications calendar per wave, exit criteria, and an HTML roadmap with a timeline.

## Design principles
- **The script computes, Claude judges.** Scoring, ordering, and dates are deterministic and testable. Claude interviews, verifies vendor claims against current docs, and writes the narrative.
- **Domain knowledge lives in data.** Packs are JSON, so adding Google Workspace, Intune, or ServiceNow migrations is writing a file, not code.
- **Calendar reality beats technical readiness.** Payroll cannot move mid-quarter because the code is ready.
- **Plans do not execute.** It never touches a system. Humans own every cutover.
- **Honest unknowns.** `unknown` target support raises risk and demands verification rather than being assumed fine.

## Try it
```
S=skills/saas-migration-planner/scripts
python3 $S/plan.py examples/idp-entra-to-okta.csv --pack idp --source entra --target okta \
  --start 2026-11-02 --freeze 2026-12-21:2027-01-04 --wave-size 6 --out plan.json
python3 $S/render_plan.py plan.json --out plan.html
```
Pre-rendered: [IdP](examples/idp-plan.html), [HRIS](examples/hris-plan.html), [MDM](examples/mdm-plan.html). The sample inventories are fictional.

## Caveats
Pack gotchas reflect common field experience and vendor behavior at the time of writing. Vendors change features, so verify Critical and High items against current documentation (the skill does this as a step). Risk scores are decision aids, not predictions.

## Roadmap
More packs (Google Workspace, Intune, ITSM, CRM), Mermaid dependency graph in the report, ADR hand-off to `architect-toolkit`, cost and license overlap modeling.

Requires Python 3.8+. No dependencies.
