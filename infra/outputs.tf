output "app_url" {
  value = "http://${aws_elastic_beanstalk_environment.env.cname}"
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
