# Scoring input schema

```json
{
  "decision": "Message broker for order events",
  "criteria": [
    {"name": "Operational burden", "weight": 8},
    {"name": "Total cost (3 yr)", "weight": 6}
  ],
  "options": [
    {
      "name": "Amazon SQS + SNS",
      "scores": {
        "Operational burden": {"score": 5, "why": "Fully managed, no patching", "assumed": false},
        "Total cost (3 yr)":  {"score": 4, "why": "Pay per request, est. $300/mo at 50M msgs", "assumed": true}
      }
    }
  ]
}
```

- `weight`: 1-10. `score`: 1-5 (5 best). Every option must score every criterion.
- Phrase criteria so higher is always better (use "Operational burden" scored as ease, not as burden).
- `assumed: true` flags scores without evidence. The script reports the assumed share per option.
