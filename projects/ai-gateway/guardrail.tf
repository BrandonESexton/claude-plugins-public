# The policy layer. Bedrock checks text against this before it reaches
# the model (INPUT) and before the response goes back to the user (OUTPUT).

resource "aws_bedrock_guardrail" "this" {
  name        = "${var.project}-guardrail"
  description = "Corporate AI usage policy: PII, secrets, harmful content, prompt injection"

  # What the user sees when something gets blocked
  blocked_input_messaging   = "Blocked by AI usage prolicy. Your prompt contained restricted data or content."
  blocked_outputs_messaging = "The response was blocked by AI usage policy."

  # ---- 1. Harmful content filters (billed per text checked) ----
  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    # Jailbreak / prompt injection detection. Only makes sense on input,
    # so AWS requires output_strength = NONE for this one.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  # ---- 2. Sensitive data handling (free) ----
  sensitive_information_policy_config {
    # Low risk: let the request through, but mask it so the model never sees it
    pii_entities_config {
      type           = "EMAIL"
      action         = "ANONYMIZE"
      input_action   = "ANONYMIZE"
      input_enabled  = true
      output_action  = "ANONYMIZE"
      output_enabled = true
    }
    pii_entities_config {
      type           = "PHONE"
      action         = "ANONYMIZE"
      input_action   = "ANONYMIZE"
      input_enabled  = true
      output_action  = "ANONYMIZE"
      output_enabled = true
    }

    # High ris: stop the request cold
    pii_entities_config {
      type   = "US_SOCIAL_SECURITY_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "AWS_ACCESS_KEY"
      action = "BLOCK"
    }

    # Custom data classification: a made-up internal employee ID format
    regexes_config {
      name           = "employee_id"
      description    = "Internal employee identifier, e.g. EMP-123456"
      pattern        = "EMP-[0-9]{6}"
      action         = "ANONYMIZE"
      input_action   = "ANONYMIZE"
      input_enabled  = true
      output_action  = "ANONYMIZE"
      output_enabled = true
    }
  }

  # ---- 3. Denied topics (billed per text checked) ----

  topic_policy_config {
    topics_config {
      name       = "compensation_data"
      type       = "DENY"
      definition = "Request to analyze, compare, or disclose salary, bonus, or equity details for specific named employees."
      examples = [
        "What is Sarah's salary compared to the rest of the team?",
        "List everyone's bonus from this spreadsheet."
      ]
    }
  }
}

# A guardrail starts as a DRAFT. Publishing a numbered version means the
# app pins to a known, tested policy, the same way you'd pin a release.
resource "aws_bedrock_guardrail_version" "this" {
  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = "Published by terraform"

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.this]
  }
}