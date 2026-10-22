# Optional custom domain + HTTPS.
# Leave var.domain_name empty ("") to deploy using only the AWS Elastic Beanstalk URL over HTTP.

variable "domain_name" {
  description = "Custom apex domain, e.g. example.com. Leave empty to use the Elastic Beanstalk URL only."
  type        = string
  default     = ""
}

variable "create_www_record" {
  description = "Also create a www.<domain> alias record. Only used when domain_name is set."
  type        = bool
  default     = true
}

locals {
  has_domain = var.domain_name != ""
}

data "aws_route53_zone" "main" {
  count = local.has_domain ? 1 : 0

  name         = var.domain_name
  private_zone = false
}

resource "aws_acm_certificate" "app" {
  count = local.has_domain ? 1 : 0

  domain_name               = var.domain_name
  subject_alternative_names = var.create_www_record ? ["www.${var.domain_name}"] : []
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.has_domain ? {
    for o in aws_acm_certificate.app[0].domain_validation_options : o.domain_name => {
      name   = o.resource_record_name
      type   = o.resource_record_type
      record = o.resource_record_value
    }
  } : {}

  zone_id         = data.aws_route53_zone.main[0].zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "app" {
  count = local.has_domain ? 1 : 0

  certificate_arn         = aws_acm_certificate.app[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# HTTPS security-group rule only when a domain/certificate is configured.
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  count = local.has_domain ? 1 : 0

  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# The ALB created by Elastic Beanstalk.
data "aws_lb" "app" {
  count = local.has_domain ? 1 : 0

  arn = aws_elastic_beanstalk_environment.env.load_balancers[0]
}

resource "aws_route53_record" "apex" {
  count = local.has_domain ? 1 : 0

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = data.aws_lb.app[0].dns_name
    zone_id                = data.aws_lb.app[0].zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "www" {
  count = local.has_domain && var.create_www_record ? 1 : 0

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = data.aws_lb.app[0].dns_name
    zone_id                = data.aws_lb.app[0].zone_id
    evaluate_target_health = true
  }
}

output "app_https_url" {
  description = "Custom HTTPS URL; empty when no custom domain is configured."
  value       = local.has_domain ? "https://${var.domain_name}" : ""
}