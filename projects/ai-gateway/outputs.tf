output "guardrail_id" {
  value = aws_bedrock_guardrail.this.guardrail_id
}

output "guardrail_version" {
  value = aws_bedrock_guardrail_version.this.version
}

output "api_url" {
  value = "${aws_api_gateway_stage.v1.invoke_url}/chat"
}

output "team_api_keys" {
  value     = { for k, v in aws_api_gateway_api_key.team : k => v.value }
  sensitive = true
}