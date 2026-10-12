variable "project" {
  description = "Name prefix for everything this project creates"
  type        = string
  default     = "ai-gateway"

}

variable "region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"

}

variable "model_id" {
  description = "Bedrock model or inference profile ID. Swap models here, no code changes."
  type        = string
  default     = "us.amazon.nova-2-lite-v1:0"
}

variable "max_output_tokens" {
  description = "Hard cap on response length. Also a cost control."
  type        = number
  default     = 512
}

variable "teams" {
  description = "Each team gets its own API key, rate limit, and daily quota"
  type = map(object({
    rate_limit         = number # steady-state requests per second
    burst_limit        = number # short spikes allowed above the rate
    daily_quota        = number # hard cap on requests per day
    monthly_budget_usd = number
  }))
  default = {
    engineering = { rate_limit = 2, burst_limit = 5, daily_quota = 200, monthly_budget_usd = 1.00 }
    marketing   = { rate_limit = 1, burst_limit = 2, daily_quota = 50, monthly_budget_usd = 0.25 }
    sandbox     = { rate_limit = 1, burst_limit = 2, daily_quota = 100, monthly_budget_usd = 0.001 }
  }
}

variable "price_per_million_input_tokens" {
  description = "USD per 1M input tokens for model_id. Update if you change models."
  type        = number
  default     = 0.30
}

variable "price_per_million_output_tokens" {
  description = "USD per 1M output tokens for model_id."
  type        = number
  default     = 2.50
}