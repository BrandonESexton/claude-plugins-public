# The spend ledger. One row per team per month:
#   team = "engineering", period = "2026-10", spend_usd = 0.0042, request_count = 17 ...
resource "aws_dynamodb_table" "usage" {
  name         = "${var.project}-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "team"
  range_key    = "period"

  attribute {
    name = "team"
    type = "S"
  }

  attribute {
    name = "period"
    type = "S"
  }
}