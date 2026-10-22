# GovScale Domain and HTTPS Guide

This guide explains how to connect a custom domain to GovScale using Route 53, GoDaddy, AWS Certificate Manager, and an Application Load Balancer.

GovScale also works without a custom domain. In `infra/terraform.tfvars`, leave:

```hcl
domain_name = ""
```

Terraform will then deploy the application using only the Elastic Beanstalk URL over HTTP. It will not create Route 53 records, an ACM certificate, an HTTPS listener, or an HTTPS security-group rule. [file:16][file:13]

## Two deployment modes

| Mode | `domain_name` | URL | HTTPS |
|---|---|---|---|
| No custom domain | `""` | `http://<eb-environment-url>` | No |
| Custom domain | `"example.com"` | `https://example.com` | Yes |

This conditional design is intentional: the infrastructure remains valid and deployable even when you do not own or want to configure a domain. [file:16]

## Recommended approach: Route 53 as DNS authority

The approach used in this project is:

1. Register or manage the domain in GoDaddy.
2. Create a Route 53 public hosted zone.
3. Copy the four Route 53 name servers.
4. Replace GoDaddy’s default nameservers with the Route 53 name servers.
5. Let Terraform create ACM validation records and ALB alias records.
6. Access GovScale through HTTPS.

This is the simplest approach for AWS deployments because Route 53 can create certificate-validation records and ALB alias records automatically through Terraform. [file:16]

## Step 1: Create a Route 53 hosted zone

You can create it through the AWS Console or CLI:

```bash
aws route53 create-hosted-zone \
  --name example.com \
  --caller-reference "govscale-$(date +%s)" \
  --hosted-zone-config Comment="GovScale public hosted zone"
```

Note the hosted zone ID and the four assigned name servers.

Example:

```text
ns-123.awsdns-45.com
ns-456.awsdns-67.net
ns-789.awsdns-89.org
ns-012.awsdns-01.co.uk
```

## Step 2: Update GoDaddy nameservers

In GoDaddy:

1. Open **My Products**.
2. Find your domain.
3. Choose **DNS** or **Manage DNS**.
4. Open **Nameservers**.
5. Select **Custom** nameservers.
6. Replace the default GoDaddy nameservers with the four Route 53 name servers.
7. Save the changes.

DNS propagation can take from a few minutes to 48 hours, although it is often much faster.

Verify delegation:

```bash
dig NS example.com +short
```

The output should show the Route 53 name servers.

## Step 3: Configure Terraform

In `infra/terraform.tfvars`, set:

```hcl
domain_name       = "example.com"
create_www_record = true
```

Then run:

```bash
cd infra
terraform init
terraform plan
terraform apply
```

Terraform will:

1. Find the Route 53 hosted zone for `example.com`.
2. Request an ACM certificate for `example.com`.
3. Add `www.example.com` as a subject alternative name if `create_www_record = true`.
4. Create DNS validation records in Route 53.
5. Wait for ACM validation.
6. Create alias A records for `example.com` and `www.example.com`.
7. Attach the validated certificate to the Elastic Beanstalk ALB HTTPS listener. [file:16][file:13]

## Step 4: Verify HTTPS

After `terraform apply` completes:

```bash
terraform output app_https_url
```

Then test:

```bash
curl -I https://example.com/health
curl -I https://www.example.com/health
```

You should receive an HTTP 200 response once DNS and certificate validation are complete.

## Important ACM region note

For an Application Load Balancer, the ACM certificate must be created in the same region as the load balancer.

This project defaults to `ap-south-1`, so the ACM certificate and ALB are created in `ap-south-1`. Do not manually create the certificate in `us-east-1` for this ALB-based setup; `us-east-1` is required for CloudFront, not for a regional ALB. [file:16][file:13]

## Alternative approaches

### Keep DNS at GoDaddy

You do not strictly need to move nameservers to Route 53.

Instead:

1. Keep GoDaddy as the DNS provider.
2. Create the ACM certificate and validate it using CNAME records added in GoDaddy.
3. Add a CNAME or ALIAS-style record in GoDaddy pointing `example.com` or `www.example.com` to the ALB DNS name.

This works, but it has drawbacks:

- Terraform cannot fully manage DNS validation and alias records.
- Apex-domain routing is less clean because GoDaddy may not support ALIAS records the way Route 53 does.
- Certificate renewal and DNS automation require more manual work.

Use this only if you cannot or do not want to change nameservers.

### Cloudflare

Cloudflare can manage DNS and provide a CDN or proxy layer.

Possible benefits:

- Global DNS performance
- DDoS protection
- Caching for static assets
- Additional security features

Trade-offs:

- Extra configuration complexity.
- You must ensure SSL/TLS mode is set correctly to avoid redirect loops or insecure origin connections.
- ACM validation and ALB behavior need careful testing.
- Caching dynamic scholarship, exam, or application pages can cause incorrect data to be shown.

For this project, Route 53 plus ACM is simpler and more directly integrated with Terraform.

### Elastic Beanstalk-managed HTTPS

Elastic Beanstalk can manage HTTPS through its own configuration, but the Route 53 plus ACM approach gives you:

- Terraform-managed DNS records
- Automatic certificate validation
- ALB alias records
- Cleaner infrastructure-as-code control

## HTTPS listener details

When a domain is configured, Terraform adds an HTTPS listener to the ALB with:

- Protocol: HTTPS
- Port: 443
- Certificate: ACM certificate ARN
- Security policy: `ELBSecurityPolicy-TLS13-1-2-2021-06` [file:13]

The ALB security group also receives an inbound rule allowing TCP port 443 from the internet. This rule is not created when no domain is configured. [file:16]

## Troubleshooting

### Certificate remains pending

Check that:

- The Route 53 hosted zone is the authoritative zone for the domain.
- GoDaddy is using the Route 53 name servers.
- The validation CNAME records exist.
- DNS has propagated.

Check:

```bash
dig NS example.com +short
dig CNAME _<validation-id>.example.com +short
```

### HTTPS does not work

Check:

```bash
terraform output app_https_url
aws acm list-certificates --region ap-south-1
aws elbv2 describe-listeners --load-balancer-arn <alb-arn>
```

Confirm the certificate status is `ISSUED` and attached to the ALB listener.

### Site works on `www` but not apex

Ensure the Route 53 apex alias record exists. Terraform creates it when `domain_name` is set. [file:16]

### DNS still points to GoDaddy

Nameserver changes can take time. Confirm with:

```bash
dig NS example.com +short
```

## Security recommendation

After HTTPS is working:

- Use HTTPS URLs in all shared links.
- Keep the ACM certificate managed by Terraform.
- Do not expose RDS publicly.
- Restrict administrative pages to authenticated administrators.
- Rotate the Flask secret key and administrator password if they may have been exposed.
