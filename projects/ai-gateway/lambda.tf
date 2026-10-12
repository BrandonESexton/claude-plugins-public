# Zip the lambda folder on every plan. The hash triggers a redeploy when code changes.
data "archive_file" "gateway" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/gateway.zip"
}

data "aws_caller_identity" "current" {}

# Create the log group ourselves so we control retention (default is forever = slow cost creep)
resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/aws/lambda/${var.project}"
  retention_in_days = 14
}

# The identity the Lambda runs as
resource "aws_iam_role" "gateway" {
  name = "${var.project}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Least privilege: invoke models, use THIS guardrail, write to THIS log group. Nothing else.
resource "aws_iam_role_policy" "gateway" {
  name = "${var.project}-lambda"
  role = aws_iam_role.gateway.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeModels"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
        ]
      },
      {
        Sid      = "UseGuardrail"
        Effect   = "Allow"
        Action   = ["bedrock:ApplyGuardrail"]
        Resource = [aws_bedrock_guardrail.this.guardrail_arn]
      },
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.gateway.arn}:*"]
      },
      {
        Sid      = "SpendLedger"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.usage.arn]
      },
    ]
  })
}

resource "aws_lambda_function" "gateway" {
  function_name    = var.project
  role             = aws_iam_role.gateway.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.gateway.output_path
  source_code_hash = data.archive_file.gateway.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      MODEL_ID          = var.model_id
      GUARDRAIL_ID      = aws_bedrock_guardrail.this.guardrail_id
      GUARDRAIL_VERSION = aws_bedrock_guardrail_version.this.version
      MAX_OUTPUT_TOKENS = tostring(var.max_output_tokens)
      TEAM_MAP = jsonencode({
        for name, key in aws_api_gateway_api_key.team : key.id => name
      })
      TABLE_NAME      = aws_dynamodb_table.usage.name
      PRICE_IN_PER_M  = tostring(var.price_per_million_input_tokens)
      PRICE_OUT_PER_M = tostring(var.price_per_million_output_tokens)
      TEAM_BUDGETS    = jsonencode({ for name, t in var.teams : name => t.monthly_budget_usd })
    }
  }

  depends_on = [aws_cloudwatch_log_group.gateway]
}