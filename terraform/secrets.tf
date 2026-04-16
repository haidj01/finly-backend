# 시크릿은 finly-agent/terraform에서 생성됨. 이 모듈은 참조만 함.
# 실제 값 확인:
#   aws secretsmanager get-secret-value --secret-id finly/CLAUDE_API_KEY

data "aws_secretsmanager_secret" "claude_api_key" {
  name = "finly/CLAUDE_API_KEY"
}

data "aws_secretsmanager_secret" "alpaca_api_key" {
  name = "finly/ALPACA_API_KEY"
}

data "aws_secretsmanager_secret" "alpaca_api_secret" {
  name = "finly/ALPACA_API_SECRET"
}
