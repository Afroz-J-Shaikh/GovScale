output "app_url" {
  description = "Primary application URL: custom HTTPS domain when configured, otherwise the Elastic Beanstalk HTTP URL."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_elastic_beanstalk_environment.env.cname}"
}

output "eb_http_url" {
  description = "Always-available Elastic Beanstalk HTTP URL."
  value       = "http://${aws_elastic_beanstalk_environment.env.cname}"
}

output "eb_application_name" {
  value = aws_elastic_beanstalk_application.app.name
}

output "eb_environment_name" {
  value = aws_elastic_beanstalk_environment.env.name
}

output "ecr_repository_url" {
  value = data.aws_ecr_repository.app.repository_url
}


output "admin_email" {
  value = var.admin_email
}
