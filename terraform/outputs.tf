output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  description = "CloudFront 오리진으로 사용할 ALB DNS 이름"
  value       = aws_lb.app.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}
