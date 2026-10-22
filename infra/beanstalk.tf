# CI already pushes images here; Terraform only reads it.
data "aws_ecr_repository" "app" {
  name = var.ecr_repository_name
}

data "aws_elastic_beanstalk_solution_stack" "docker" {
  most_recent = true
  name_regex  = "^64bit Amazon Linux 2023 (.*) running Docker$"
}

resource "aws_elastic_beanstalk_application" "app" {
  name        = var.name
  description = "GovScale scholarship and exam portal"
}

locals {
  database_uri = "postgresql+psycopg2://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${aws_db_instance.main.db_name}"

  # Non-secret settings. Secrets are written as explicit blocks further down.
  eb_settings = [
    # --- network ---
    { ns = "aws:ec2:vpc", name = "VPCId", value = aws_vpc.main.id },
    { ns = "aws:ec2:vpc", name = "Subnets", value = join(",", aws_subnet.app[*].id) },
    { ns = "aws:ec2:vpc", name = "ELBSubnets", value = join(",", aws_subnet.public[*].id) },
    { ns = "aws:ec2:vpc", name = "AssociatePublicIpAddress", value = "false" },

    # --- load balancer ---
    { ns = "aws:elasticbeanstalk:environment", name = "EnvironmentType", value = "LoadBalanced" },
    { ns = "aws:elasticbeanstalk:environment", name = "LoadBalancerType", value = "application" },
    { ns = "aws:elasticbeanstalk:environment", name = "ServiceRole", value = aws_iam_role.service.name },
    { ns = "aws:elbv2:loadbalancer", name = "SecurityGroups", value = aws_security_group.alb.id },
    { ns = "aws:elbv2:loadbalancer", name = "ManagedSecurityGroup", value = aws_security_group.alb.id },
    { ns = "aws:elasticbeanstalk:environment:process:default", name = "HealthCheckPath", value = "/health" },
    { ns = "aws:elasticbeanstalk:environment:process:default", name = "MatcherHTTPCode", value = "200" },
    { ns = "aws:elasticbeanstalk:environment:process:default", name = "HealthCheckInterval", value = "15" },
    { ns = "aws:elasticbeanstalk:environment:process:default", name = "DeregistrationDelay", value = "20" },

    # --- nginx on the instance forwards port 80 to the container's port 5000 ---
    { ns = "aws:elasticbeanstalk:environment:proxy", name = "ProxyServer", value = "nginx" },

    # --- instances and scaling ---
    { ns = "aws:autoscaling:launchconfiguration", name = "IamInstanceProfile", value = aws_iam_instance_profile.ec2.name },
    { ns = "aws:autoscaling:launchconfiguration", name = "SecurityGroups", value = aws_security_group.app.id },
    { ns = "aws:autoscaling:launchconfiguration", name = "DisableIMDSv1", value = "true" },
    { ns = "aws:ec2:instances", name = "InstanceTypes", value = var.instance_type },
    { ns = "aws:autoscaling:asg", name = "MinSize", value = tostring(var.min_instances) },
    { ns = "aws:autoscaling:asg", name = "MaxSize", value = tostring(var.max_instances) },
    { ns = "aws:autoscaling:trigger", name = "MeasureName", value = "CPUUtilization" },
    { ns = "aws:autoscaling:trigger", name = "Statistic", value = "Average" },
    { ns = "aws:autoscaling:trigger", name = "Unit", value = "Percent" },
    { ns = "aws:autoscaling:trigger", name = "UpperThreshold", value = "55" },
    { ns = "aws:autoscaling:trigger", name = "LowerThreshold", value = "20" },

    # --- zero-downtime deployments ---
    { ns = "aws:elasticbeanstalk:command", name = "DeploymentPolicy", value = var.deployment_policy },
    { ns = "aws:elasticbeanstalk:command", name = "BatchSizeType", value = "Percentage" },
    { ns = "aws:elasticbeanstalk:command", name = "BatchSize", value = "50" },

    # --- observability ---
    { ns = "aws:elasticbeanstalk:healthreporting:system", name = "SystemType", value = "enhanced" },
    { ns = "aws:elasticbeanstalk:cloudwatch:logs", name = "StreamLogs", value = "true" },
    { ns = "aws:elasticbeanstalk:cloudwatch:logs", name = "RetentionInDays", value = "7" },

    # --- non-secret app config ---
    { ns = "aws:elasticbeanstalk:application:environment", name = "GOVSCALE_ADMIN_EMAIL", value = var.admin_email },
    { ns = "aws:elasticbeanstalk:application:environment", name = "WEB_CONCURRENCY", value = "2" },
    { ns = "aws:elasticbeanstalk:application:environment", name = "GUNICORN_THREADS", value = "4" },
  ]
}

resource "aws_elastic_beanstalk_environment" "env" {
  name                   = "${var.name}-${var.environment}"
  application            = aws_elastic_beanstalk_application.app.name
  solution_stack_name    = data.aws_elastic_beanstalk_solution_stack.docker.name
  tier                   = "WebServer"
  wait_for_ready_timeout = "30m"

  dynamic "setting" {
    for_each = { for i, s in local.eb_settings : tostring(i) => s }
    content {
      namespace = setting.value.ns
      name      = setting.value.name
      value     = setting.value.value
    }
  }

  # Secrets (sensitive values cannot go through the dynamic block above).
  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "GOVSCALE_SECRET_KEY"
    value     = random_password.secret_key.result
  }
  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "GOVSCALE_DATABASE_URI"
    value     = local.database_uri
  }
  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "GOVSCALE_ADMIN_PASSWORD"
    value     = random_password.admin.result
  }

  # The first apply launches Beanstalk's sample app. The CD workflow deploys your image
  # and changes version_label, so Terraform must not try to revert it.
  lifecycle {
    ignore_changes = [version_label, solution_stack_name]
  }

  depends_on = [
    aws_iam_role_policy_attachment.ec2,
    aws_iam_role_policy_attachment.service,
    aws_nat_gateway.main,
    aws_vpc_security_group_ingress_rule.app_from_alb,
    aws_vpc_security_group_ingress_rule.db_from_app,
  ]
}
