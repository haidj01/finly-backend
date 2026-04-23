output "elastic_ip" {
  value       = aws_eip.app.public_ip
  description = "EC2 퍼블릭 IP"
}

output "ssh_command" {
  value       = "ssh -i <key.pem> ec2-user@${aws_eip.app.public_ip}"
  description = "SSH 접속 명령어"
}

output "cloudfront_backend_origin" {
  value       = var.aws_region == "us-east-1" ? "ec2-${replace(aws_eip.app.public_ip, ".", "-")}.compute-1.amazonaws.com" : "ec2-${replace(aws_eip.app.public_ip, ".", "-")}.${var.aws_region}.compute.amazonaws.com"
  description = "CloudFront custom origin용 EC2 public DNS (IP 직접 사용 불가)"
}

output "ecr_backend_url" {
  value       = aws_ecr_repository.backend.repository_url
  description = "finly-backend ECR URL"
}

output "ecr_agent_url" {
  value       = aws_ecr_repository.agent.repository_url
  description = "finly-agent ECR URL"
}
