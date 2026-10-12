# ---- The API itself ----
resource "aws_api_gateway_rest_api" "this" {
  name        = var.project
  description = "Governed AI gateway"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# /chat
resource "aws_api_gateway_resource" "chat" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "chat"
}

# POST /chat, and you must present an API key
resource "aws_api_gateway_method" "chat_post" {
  rest_api_id      = aws_api_gateway_rest_api.this.id
  resource_id      = aws_api_gateway_resource.chat.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

# Hand the whole request to Lambda as-is (proxy integration)
resource "aws_api_gateway_integration" "chat_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.chat.id
  http_method             = aws_api_gateway_method.chat_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.gateway.invoke_arn
}

# Let API Gateway invoke the Lambda, but only for POST /chat on THIS API
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.gateway.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/POST/chat"
}

# ---- Publishing ----
# A deployment is a snapshot of the API config. The triggers force a new
# snapshot whenever the route, method, or integration changes.
resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.chat.id,
      aws_api_gateway_method.chat_post.id,
      aws_api_gateway_integration.chat_lambda.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = "v1"
}

# ---- Per-team access ----
resource "aws_api_gateway_api_key" "team" {
  for_each = var.teams
  name     = "${var.project}-${each.key}"
}

resource "aws_api_gateway_usage_plan" "team" {
  for_each = var.teams
  name     = "${var.project}-${each.key}"

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.v1.stage_name
  }

  throttle_settings {
    rate_limit  = each.value.rate_limit
    burst_limit = each.value.burst_limit
  }

  quota_settings {
    limit  = each.value.daily_quota
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "team" {
  for_each      = var.teams
  key_id        = aws_api_gateway_api_key.team[each.key].id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.team[each.key].id
}