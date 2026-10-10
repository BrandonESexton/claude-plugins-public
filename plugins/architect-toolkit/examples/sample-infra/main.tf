resource "aws_security_group" "web" {
  name = "web"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_s3_bucket" "logs" {
  bucket = "acme-logs"
  acl    = "public-read"
}

resource "aws_db_instance" "orders" {
  engine              = "postgres"
  instance_class      = "db.m5.large"
  publicly_accessible = true
  storage_encrypted   = false
}

resource "aws_instance" "app" {
  ami                         = "ami-123"
  instance_type               = "t3.large"
  associate_public_ip_address = true
}

resource "aws_iam_policy" "admin" {
  name   = "admin"
  policy = jsonencode({ Statement = [{ "Action" : "*", "Effect" : "Allow", "Resource" : "*" }] })
}
