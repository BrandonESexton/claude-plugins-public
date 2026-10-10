#!/usr/bin/env python3
"""Static scanner for Terraform and CloudFormation. Stdlib only.

Usage: iac_scan.py <path> [--out findings.json]
Heuristic: regex over resource blocks. Treat results as leads to confirm.
"""
import json
import os
import re
import sys
from collections import Counter

SKIP_DIRS = {".git", ".terraform", "node_modules", "cdk.out", "__pycache__"}


def F(rule, pillar, sev, title, rem):
    return dict(id=rule, pillar=pillar, severity=sev, title=title, remediation=rem)


# ---------- Terraform ----------
TF_RES = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.M)


def tf_blocks(text):
    """Yield (type, name, body, start_line) using brace matching."""
    for m in TF_RES.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            c = text[i]
            depth += (c == "{") - (c == "}")
            i += 1
        yield m.group(1), m.group(2), text[m.end():i - 1], text.count("\n", 0, m.start()) + 1


def line_of(text, body_start_line, body, pattern):
    m = re.search(pattern, body)
    if not m:
        return body_start_line, ""
    return body_start_line + body.count("\n", 0, m.start()), m.group(0).strip()


def scan_tf(path, text, all_text):
    out, inv = [], Counter()
    has_pab = "aws_s3_bucket_public_access_block" in all_text
    has_sse = "aws_s3_bucket_server_side_encryption_configuration" in all_text
    for rtype, name, body, ln in tf_blocks(text):
        inv[rtype] += 1
        res = f"{rtype}.{name}"

        def add(f, pattern=None, pos=None):
            l, ev = line_of(text, ln, body, pattern) if pattern else (ln, "")
            if pos is not None:
                l, ev = ln + body.count("\n", 0, pos), body[pos:pos + 40].split("\n")[0].strip()
            out.append({**f, "file": path, "line": l, "resource": res, "evidence": ev, "source": "scanner"})

        if rtype == "aws_security_group" or rtype == "aws_security_group_rule" or rtype == "aws_vpc_security_group_ingress_rule":
            for m in re.finditer(r'(cidr_blocks|cidr_ipv4)\s*=\s*\[?\s*"0\.0\.0\.0/0"', body):
                seg = body[body.rfind("{", 0, m.start()) + 1: body.find("}", m.end())]
                sensitive = re.search(r'(from_port|to_port)\s*=\s*(22|3389|3306|5432|1433|27017|6379|9200)\b', seg)
                if sensitive:
                    add(F("SEC-SG-001", "Security", "Critical", "Admin or database port open to the internet",
                          "Restrict to known CIDRs, use SSM Session Manager instead of SSH/RDP, keep data stores private."), pos=m.start())
                else:
                    add(F("SEC-SG-002", "Security", "Medium", "Ingress open to 0.0.0.0/0",
                          "Confirm this is an intended public endpoint, ideally behind a load balancer or WAF."), pos=m.start())
        if rtype == "aws_s3_bucket":
            if re.search(r'acl\s*=\s*"public', body):
                add(F("SEC-S3-001", "Security", "High", "S3 bucket has a public ACL",
                      "Use private ACL and add aws_s3_bucket_public_access_block."), r'acl\s*=\s*"public[^"]*"')
            if not has_pab:
                add(F("SEC-S3-002", "Security", "Medium", "No S3 public access block defined in scanned code",
                      "Add aws_s3_bucket_public_access_block with all four flags true, or enforce at account level."))
            if not has_sse and "server_side_encryption_configuration" not in body:
                add(F("SEC-S3-003", "Security", "Medium", "No explicit S3 encryption configuration",
                      "Add SSE-KMS with a customer-managed key for sensitive data."))
            if not re.search(r'versioning', all_text):
                add(F("REL-S3-001", "Reliability", "Low", "No S3 versioning configured in scanned code",
                      "Enable versioning on buckets holding state or irreplaceable data."))
        if rtype in ("aws_db_instance", "aws_rds_cluster"):
            if re.search(r'storage_encrypted\s*=\s*false', body) or "storage_encrypted" not in body:
                add(F("SEC-RDS-001", "Security", "High", "Database storage not encrypted", "Set storage_encrypted = true with a KMS key."),
                    r'storage_encrypted\s*=\s*false')
            if re.search(r'publicly_accessible\s*=\s*true', body):
                add(F("SEC-RDS-002", "Security", "Critical", "Database is publicly accessible", "Set publicly_accessible = false and place in private subnets."),
                    r'publicly_accessible\s*=\s*true')
            if rtype == "aws_db_instance" and not re.search(r'multi_az\s*=\s*true', body):
                add(F("REL-RDS-001", "Reliability", "Medium", "RDS instance is single-AZ", "Set multi_az = true for production workloads."))
            if not re.search(r'backup_retention_period\s*=\s*([1-9]\d*)', body):
                add(F("REL-RDS-002", "Reliability", "Medium", "Automated backups disabled or unset", "Set backup_retention_period to 7 or more days."))
            if not re.search(r'deletion_protection\s*=\s*true', body):
                add(F("REL-RDS-003", "Reliability", "Low", "Deletion protection not enabled", "Set deletion_protection = true for production."))
        if rtype == "aws_ebs_volume" and not re.search(r'encrypted\s*=\s*true', body):
            add(F("SEC-EBS-001", "Security", "Medium", "EBS volume not encrypted", "Set encrypted = true, or enable account-level default encryption."))
        if rtype in ("aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy"):
            if re.search(r'"Action"\s*:\s*"\*"|actions\s*=\s*\[\s*"\*"\s*\]', body) and re.search(r'"Resource"\s*:\s*"\*"|resources\s*=\s*\[\s*"\*"\s*\]', body):
                add(F("SEC-IAM-001", "Security", "Critical", "IAM policy grants all actions on all resources", "Scope to required actions and resource ARNs."), r'"Action"\s*:\s*"\*"|actions\s*=\s*\[\s*"\*"\s*\]')
            elif re.search(r'"Action"\s*:\s*"\*"|"[a-z0-9]+:\*"', body):
                add(F("SEC-IAM-002", "Security", "Medium", "IAM policy uses wildcard actions", "Replace service-wide wildcards with the specific actions needed."), r'"Action"\s*:\s*"\*"|"[a-z0-9]+:\*"')
        if rtype == "aws_iam_user":
            add(F("SEC-IAM-003", "Security", "Low", "IAM user defined", "Prefer SSO/roles with short-lived credentials over IAM users."))
        if rtype == "aws_instance":
            if not re.search(r'http_tokens\s*=\s*"required"', body):
                add(F("SEC-EC2-001", "Security", "Medium", "IMDSv2 not enforced", 'Add metadata_options { http_tokens = "required" }.'))
            if re.search(r'associate_public_ip_address\s*=\s*true', body):
                add(F("SEC-EC2-002", "Security", "Medium", "Instance gets a public IP", "Place behind a load balancer; use SSM for access."), r'associate_public_ip_address\s*=\s*true')
        if rtype in ("aws_lb", "aws_alb"):
            if not re.search(r'access_logs', body):
                add(F("OPS-LB-001", "Operational Excellence", "Low", "Load balancer access logs not enabled", "Enable access_logs to an S3 bucket."))
        if rtype == "aws_lb_listener" and re.search(r'protocol\s*=\s*"HTTP"', body) and not re.search(r'redirect', body):
            add(F("SEC-LB-001", "Security", "Medium", "HTTP listener without redirect to HTTPS", "Redirect to HTTPS or terminate TLS."), r'protocol\s*=\s*"HTTP"')
        if rtype == "aws_cloudtrail" and not re.search(r'is_multi_region_trail\s*=\s*true', body):
            add(F("SEC-CT-001", "Security", "Medium", "CloudTrail is not multi-region", "Set is_multi_region_trail = true."))
        if rtype == "aws_nat_gateway":
            inv["_nat"] += 1
        if rtype.startswith("aws_") and "tags" not in body and rtype not in ("aws_s3_bucket_public_access_block", "aws_security_group_rule", "aws_route", "aws_iam_role_policy_attachment") and rtype in (
                "aws_instance", "aws_s3_bucket", "aws_db_instance", "aws_vpc", "aws_lb", "aws_ebs_volume", "aws_rds_cluster"):
            add(F("OPS-TAG-001", "Operational Excellence", "Low", "Resource has no tags", "Apply a tagging standard (owner, env, cost-center) or default_tags."))
    return out, inv


# ---------- CloudFormation ----------
def scan_cfn(path, text):
    out, inv = [], Counter()
    for m in re.finditer(r'^  (\w+):\s*\n\s+Type:\s*([\w:]+)', text, re.M):
        name, rtype = m.group(1), m.group(2)
        inv[rtype] += 1
        start = m.start()
        nxt = re.search(r'^  \w+:\s*\n\s+Type:', text[m.end():], re.M)
        body = text[start: m.end() + (nxt.start() if nxt else len(text))]
        ln = text.count("\n", 0, start) + 1

        def add(f):
            out.append({**f, "file": path, "line": ln, "resource": name, "evidence": rtype, "source": "scanner"})

        if rtype == "AWS::EC2::SecurityGroup" and re.search(r'CidrIp:\s*0\.0\.0\.0/0', body) and re.search(r'(22|3389|3306|5432)\b', body):
            add(F("SEC-SG-001", "Security", "Critical", "Admin or database port open to the internet", "Restrict CIDRs; use SSM Session Manager."))
        if rtype == "AWS::S3::Bucket":
            if "BucketEncryption" not in body:
                add(F("SEC-S3-003", "Security", "Medium", "No explicit S3 encryption configuration", "Add BucketEncryption with SSE-KMS."))
            if "PublicAccessBlockConfiguration" not in body:
                add(F("SEC-S3-002", "Security", "Medium", "No S3 public access block", "Add PublicAccessBlockConfiguration with all flags true."))
            if "VersioningConfiguration" not in body:
                add(F("REL-S3-001", "Reliability", "Low", "S3 versioning not configured", "Enable versioning."))
        if rtype == "AWS::RDS::DBInstance":
            if not re.search(r'StorageEncrypted:\s*true', body, re.I):
                add(F("SEC-RDS-001", "Security", "High", "Database storage not encrypted", "Set StorageEncrypted: true."))
            if re.search(r'PubliclyAccessible:\s*true', body, re.I):
                add(F("SEC-RDS-002", "Security", "Critical", "Database is publicly accessible", "Set PubliclyAccessible: false."))
            if not re.search(r'MultiAZ:\s*true', body, re.I):
                add(F("REL-RDS-001", "Reliability", "Medium", "RDS instance is single-AZ", "Set MultiAZ: true for production."))
        if rtype in ("AWS::IAM::Policy", "AWS::IAM::ManagedPolicy", "AWS::IAM::Role") and re.search(r'Action:\s*[\'"]?\*[\'"]?\s*$', body, re.M):
            add(F("SEC-IAM-001", "Security", "Critical", "IAM policy grants wildcard actions", "Scope to required actions and resources."))
    return out, inv


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = sys.argv[1]
    outp = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    files = []
    if os.path.isfile(root):
        files = [root]
    else:
        for d, dirs, fs in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            files += [os.path.join(d, f) for f in fs if f.endswith((".tf", ".yaml", ".yml", ".json", ".template"))]

    tf_texts = {p: open(p, errors="ignore").read() for p in files if p.endswith(".tf")}
    all_tf = "\n".join(tf_texts.values())
    findings, inv = [], Counter()
    for p, t in tf_texts.items():
        f, i = scan_tf(os.path.relpath(p), t, all_tf)
        findings += f
        inv.update(i)
    for p in files:
        if p.endswith(".tf"):
            continue
        t = open(p, errors="ignore").read()
        if "AWSTemplateFormatVersion" in t or re.search(r'^Resources:', t, re.M):
            f, i = scan_cfn(os.path.relpath(p), t)
            findings += f
            inv.update(i)

    # de-duplicate project-wide findings that repeat per resource
    seen, uniq = set(), []
    for f in findings:
        k = (f["id"], f["file"], f["resource"], f["line"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    uniq.sort(key=lambda f: (order[f["severity"]], f["file"], f["line"]))
    inv.pop("_nat", None)
    result = {"findings": uniq, "inventory": dict(inv.most_common())}

    if outp:
        with open(outp, "w") as fh:
            json.dump(result, fh, indent=2)
    c = Counter(f["severity"] for f in uniq)
    print(f"Scanned {len(files)} files, {sum(inv.values())} resources, {len(uniq)} findings")
    print("  " + ", ".join(f"{s}: {c.get(s, 0)}" for s in order))
    print("Inventory: " + ", ".join(f"{k} x{v}" for k, v in list(inv.most_common(12))))
    for f in uniq[:15]:
        print(f"  [{f['severity']}] {f['id']} {f['file']}:{f['line']} {f['title']}")
    if outp:
        print(f"Wrote {outp}")


if __name__ == "__main__":
    main()
