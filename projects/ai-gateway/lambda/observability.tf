locals {
  logs = "SOURCE '${aws_cloudwatch_log_group.gateway.name}'"
}

resource "aws_cloudwatch_dashboard" "gateway" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "log"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Spend by team (USD, estimated)"
          region = var.region
          view   = "table"
          query  = "${local.logs} | filter ispresent(cost_usd) | stats sum(cost_usd) as spend_usd, count(*) as paid_requests by team | sort spend_usd desc"
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Outcomes by team"
          region = var.region
          view   = "table"
          query  = "${local.logs} | filter ispresent(outcome) | stats count(*) as requests by team, outcome | sort team"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Top input policy triggers (first hit per request)"
          region = var.region
          view   = "table"
          query  = "${local.logs} | filter ispresent(`input_hits.0`) | stats count(*) as hits by `input_hits.0` | sort hits desc"
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Latency by outcome (ms)"
          region = var.region
          view   = "table"
          query  = "${local.logs} | filter ispresent(latency_ms) | stats avg(latency_ms) as avg_ms, pct(latency_ms, 95) as p95_ms by outcome"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 12
        width  = 24
        height = 6
        properties = {
          title  = "Requests per hour"
          region = var.region
          view   = "timeSeries"
          query  = "${local.logs} | filter ispresent(outcome) | stats count(*) as requests by bin(1h)"
        }
      },
    ]
  })
}

output "dashboard_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards/dashboard/${var.project}"
}