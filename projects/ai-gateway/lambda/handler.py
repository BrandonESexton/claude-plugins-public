import json
import os
import time
import uuid
from datetime import datetime, timezone  # NEW
from decimal import Decimal  # NEW

import boto3

bedrock = boto3.client("bedrock-runtime")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])  # NEW

MODEL_ID = os.environ["MODEL_ID"]
GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION = os.environ["GUARDRAIL_VERSION"]
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "512"))
TEAM_MAP = json.loads(os.environ.get("TEAM_MAP", "{}"))
TEAM_BUDGETS = json.loads(os.environ.get("TEAM_BUDGETS", "{}"))  # NEW

# NEW: price per single token. Decimal, because floats drift when you add up money.
PRICE_IN = Decimal(os.environ["PRICE_IN_PER_M"]) / Decimal(1_000_000)
PRICE_OUT = Decimal(os.environ["PRICE_OUT_PER_M"]) / Decimal(1_000_000)


# ---------- NEW: spend ledger ----------

def current_period():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_spend(team):
    item = table.get_item(Key={"team": team, "period": current_period()}).get("Item")
    return item["spend_usd"] if item else Decimal("0")


def record_spend(team, input_tokens, output_tokens):
    cost = input_tokens * PRICE_IN + output_tokens * PRICE_OUT
    # ADD is atomic: two requests at the same moment can't overwrite each other
    table.update_item(
        Key={"team": team, "period": current_period()},
        UpdateExpression="ADD spend_usd :c, input_tokens :i, output_tokens :o, request_count :one",
        ExpressionAttributeValues={":c": cost, ":i": input_tokens, ":o": output_tokens, ":one": 1},
    )
    return cost


# ---------- guardrail (unchanged) ----------

def check_guardrail(text, source):
    resp = bedrock.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    hits = summarize(resp.get("assessments", []))
    blocked = any(h.endswith(":BLOCKED") for h in hits)
    outputs = resp.get("outputs", [])
    safe_text = outputs[0]["text"] if outputs else text
    return blocked, safe_text, hits


def summarize(assessments):
    hits = []
    for a in assessments:
        sip = a.get("sensitiveInformationPolicy", {})
        for e in sip.get("piiEntities", []):
            hits.append(f"pii:{e['type']}:{e['action']}")
        for r in sip.get("regexes", []):
            hits.append(f"regex:{r['name']}:{r['action']}")
        for f in a.get("contentPolicy", {}).get("filters", []):
            hits.append(f"content:{f['type']}:{f['action']}")
        for t in a.get("topicPolicy", {}).get("topics", []):
            hits.append(f"topic:{t['name']}:{t['action']}")
    return hits


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


# ---------- handler ----------

def lambda_handler(event, context):
    request_id = str(uuid.uuid4())
    started = time.time()

    body = json.loads(event["body"]) if "body" in event else event
    prompt = body.get("prompt", "").strip()
    user = body.get("user", "unknown")

    key_id = event.get("requestContext", {}).get("identity", {}).get("apiKeyId")
    team = TEAM_MAP.get(key_id, "direct-invoke")

    if not prompt:
        return respond(400, {"error": "prompt is required"})

    audit = {"request_id": request_id, "team": team, "user": user, "model": MODEL_ID}

    # NEW: 0. Budget check first. It's the cheapest check, so it runs before anything that costs money.
    budget = TEAM_BUDGETS.get(team)
    if budget is not None:
        spent = get_spend(team)
        if spent >= Decimal(str(budget)):
            audit.update(outcome="over_budget", spent_usd=float(spent), budget_usd=budget)
            print(json.dumps(audit))
            return respond(429, {
                "request_id": request_id,
                "team": team,
                "error": "Monthly AI budget reached for this team",
                "spent_usd": float(spent),
                "budget_usd": budget,
            })

    # 1. Check the prompt
    blocked, safe_prompt, in_hits = check_guardrail(prompt, "INPUT")
    audit["input_hits"] = in_hits

    if blocked:
        audit.update(outcome="blocked_input", latency_ms=int((time.time() - started) * 1000))
        print(json.dumps(audit))
        return respond(403, {"request_id": request_id, "team": team, "blocked": True, "message": safe_prompt})

    # 2. Call the model
    result = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": safe_prompt}]}],
        inferenceConfig={"maxTokens": MAX_OUTPUT_TOKENS},
    )
    answer = result["output"]["message"]["content"][0]["text"]
    usage = result["usage"]

    # NEW: record cost right away. The tokens are spent even if the output gets blocked next.
    cost = record_spend(team, usage["inputTokens"], usage["outputTokens"])

    # 3. Check the response
    blocked, safe_answer, out_hits = check_guardrail(answer, "OUTPUT")

    audit.update(
        output_hits=out_hits,
        outcome="blocked_output" if blocked else "ok",
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        cost_usd=float(cost),  # NEW
        latency_ms=int((time.time() - started) * 1000),
    )
    print(json.dumps(audit))

    return respond(200, {
        "request_id": request_id,
        "team": team,
        "blocked": blocked,
        "response": safe_answer,
        "prompt_as_sent": safe_prompt,
        "guardrail": {"input": in_hits, "output": out_hits},
        "usage": {"input_tokens": usage["inputTokens"], "output_tokens": usage["outputTokens"]},
        "cost_usd": float(cost),  # NEW
    })