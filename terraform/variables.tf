variable "aws_region" {
  default = "us-east-1"
}

variable "app_name" {
  default = "finly-backend"
}

variable "image_tag" {
  description = "ECR 이미지 태그 (CI/CD에서 주입)"
  default     = "latest"
}

variable "container_port" {
  default = 8000
}

variable "cpu" {
  default = "256"
}

variable "memory" {
  default = "512"
}

variable "frontend_origin" {
  description = "CORS 허용 오리진, CloudFront 배포 후 실제 URL로 업데이트"
  default     = "*"
}
