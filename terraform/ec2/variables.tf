variable "aws_region" {
  default = "us-east-1"
}

variable "app_name" {
  default = "finly"
}

# t3.micro = 프리티어 (첫 12개월 무료), 이후 t4g.micro로 전환 시 더 저렴
variable "instance_type" {
  default = "t3.micro"
}

variable "key_name" {
  description = "EC2 Key Pair 이름 — AWS 콘솔에서 사전 생성 필요"
}

variable "frontend_origin" {
  description = "CORS 허용 오리진 (CloudFront 도메인 확정 후 업데이트)"
  default     = "*"
}

variable "claude_api_key" {
  description = "Anthropic Claude API Key"
  sensitive   = true
}

variable "alpaca_api_key" {
  description = "Alpaca API Key"
  sensitive   = true
}

variable "alpaca_api_secret" {
  description = "Alpaca API Secret"
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT signing secret"
  sensitive   = true
}

variable "admin_username" {
  description = "Admin login username"
  default     = "admin"
}

variable "admin_password_hash" {
  description = "bcrypt hash of admin password"
  sensitive   = true
}

variable "totp_secret" {
  description = "TOTP base32 secret (leave empty to generate via /api/auth/mfa/setup)"
  default     = ""
  sensitive   = true
}
