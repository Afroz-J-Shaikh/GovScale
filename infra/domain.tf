# HTTPS for the app on your own domain:
#   Route 53 (existing zone) -> ACM certificate -> ALB :443 -> Beanstalk
#
# The hosted zone is looked up, NOT created here, on purpose: a zone created by
# Terraform would get new nameservers after every destroy/apply and break your
# registrar delegation. Create it once by hand (see the notes in the chat).

variable "domain_name" {
  type    = string
  default = "afrozdevops.online"
}

data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# Certificate must be in the same region as the ALB (ap-south-1), which is the provider default.
resource "aws_acm_certificate" "app" {
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for o in aws_acm_certificate.app.domain_validation_options : o.domain_name => {
      name   = o.resource_record_name
      type   = o.resource_record_type
      record = o.resource_record_value
    }
  }

  zone_id         = data.aws_route53_zone.main.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# HTTPS into the load balancer. Port 80 stays open only so nginx can redirect it to HTTPS.
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

# The ALB that Beanstalk created for the environment.
data "aws_lb" "app" {
  arn = aws_elastic_beanstalk_environment.env.load_balancers[0]
}

resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = data.aws_lb.app.dns_name
    zone_id                = data.aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = data.aws_lb.app.dns_name
    zone_id                = data.aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

output "app_https_url" {
  value = "https://${var.domain_name}"
}
