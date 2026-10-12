terraform {
  backend "s3" {
    bucket       = "ai-gateway-tfstate-<YOUR_ACCOUNT_ID>" # replace with your AWS account ID
    key          = "ai-gateway/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}