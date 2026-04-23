# DB 비밀번호 자동 생성
resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/finly/DB_PASSWORD"
  type  = "SecureString"
  value = random_password.db.result
}

# API 키 — terraform apply 시 var로 주입하거나 apply 후 콘솔에서 직접 설정
resource "aws_ssm_parameter" "claude_api_key" {
  name  = "/finly/CLAUDE_API_KEY"
  type  = "SecureString"
  value = var.claude_api_key
}

resource "aws_ssm_parameter" "alpaca_api_key" {
  name  = "/finly/ALPACA_API_KEY"
  type  = "SecureString"
  value = var.alpaca_api_key
}

resource "aws_ssm_parameter" "alpaca_api_secret" {
  name  = "/finly/ALPACA_API_SECRET"
  type  = "SecureString"
  value = var.alpaca_api_secret
}

resource "aws_ssm_parameter" "jwt_secret" {
  name  = "/finly/JWT_SECRET"
  type  = "SecureString"
  value = var.jwt_secret
}

resource "aws_ssm_parameter" "admin_username" {
  name  = "/finly/ADMIN_USERNAME"
  type  = "String"
  value = var.admin_username
}

resource "aws_ssm_parameter" "admin_password_hash" {
  name  = "/finly/ADMIN_PASSWORD_HASH"
  type  = "SecureString"
  value = var.admin_password_hash
}

resource "aws_ssm_parameter" "totp_secret" {
  count = var.totp_secret != "" ? 1 : 0
  name  = "/finly/TOTP_SECRET"
  type  = "SecureString"
  value = var.totp_secret
}
