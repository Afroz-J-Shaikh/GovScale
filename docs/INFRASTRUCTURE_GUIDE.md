# GovScale Infrastructure Guide

This guide explains every Terraform file in `infra/`, the AWS resources it creates, and how the pieces work together.

All infrastructure is defined as code so the environment can be recreated, reviewed, version-controlled, and destroyed consistently.

## File map

| File | Purpose |
|---|---|
| `versions.tf` | Terraform version, AWS provider, tags, and S3 remote state backend |
| `variables.tf` | Configurable deployment inputs |
| `network.tf` | VPC, subnets, routing, Internet Gateway, and NAT Gateway |
| `security.tf` | Security groups and traffic rules |
| `database.tf` | RDS PostgreSQL and Secrets Manager credentials |
| `iam.tf` | Elastic Beanstalk and EC2 IAM roles |
| `secrets_access.tf` | Permissions allowing EC2 instances to read Secrets Manager |
| `beanstalk.tf` | Elastic Beanstalk application, environment, scaling, and deployment settings |
| `domain.tf` | Optional Route 53, ACM, and HTTPS configuration |
| `outputs.tf` | Values returned after `terraform apply` |
| `terraform.tfvars` | Local non-committed variable values |
| `terraform.tfvars.example` | Example variable configuration |
| `destroy.sh` | Helper script for infrastructure cleanup |

## versions.tf

This file defines the Terraform and provider requirements.

It requires:

- Terraform 1.10 or newer
- AWS provider version 5.x
- Random provider version 3.6 or newer

It configures a remote S3 backend:

```hcl
backend "s3" {
  bucket       = "govscale-tfstate"
  key          = "govscale/terraform.tfstate"
  region       = "ap-south-1"
  use_lockfile = true
  encrypt      = true
}
```

This means Terraform state is stored centrally in S3, encrypted at rest, and locked using S3-native state locking. A separate DynamoDB lock table is not needed because `use_lockfile = true` is enabled. [file:26]

It also applies default tags to AWS resources:

- `Project = govscale`
- `ManagedBy = terraform`

## variables.tf

This file defines the inputs used across the deployment.

| Variable | Default | Purpose |
|---|---|---|
| `aws_region` | `ap-south-1` | AWS region for all resources |
| `name` | `govscale` | Base resource name |
| `environment` | `prod` | Environment suffix |
| `ecr_repository_name` | `govscale` | Existing ECR repository containing the application image |
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR block |
| `instance_type` | `t3.medium` | EC2 instance type for EB |
| `min_instances` | `1` | Minimum EB instances |
| `max_instances` | `4` | Maximum EB instances |
| `deployment_policy` | `Rolling` | EB deployment strategy |
| `db_instance_class` | `db.t4g.micro` | RDS instance class |
| `db_engine_version` | `16` | PostgreSQL version |
| `db_multi_az` | `false` | Enables RDS Multi-AZ failover |
| `admin_email` | `admin@gmail.com` | Initial administrator email |
| `domain_name` | `""` | Optional custom domain |
| `create_www_record` | `true` | Creates `www.<domain>` when a domain is configured |

The defaults are suitable for a hackathon deployment. For a production-like demonstration, use at least two application instances and consider enabling `db_multi_az`. [file:25]

## network.tf

This file creates a highly available, multi-AZ network.

### Resources created

- 1 VPC
- 2 Availability Zones
- 2 public subnets
- 2 private application subnets
- 2 private database subnets
- 1 Internet Gateway
- 1 NAT Gateway
- 1 Elastic IP for NAT
- 3 route tables
- 6 route-table associations

### Subnet layout

| Subnet type | Count | Purpose | Internet access |
|---|---:|---|---|
| Public | 2 | ALB and NAT Gateway | Yes, through Internet Gateway |
| Private application | 2 | Elastic Beanstalk EC2 instances | Outbound only, through NAT |
| Private database | 2 | RDS PostgreSQL | No internet route |

The VPC uses `10.0.0.0/16` by default. Terraform automatically selects the first two available Availability Zones and creates matching subnets in each. [file:18]

### Routing behavior

- Public subnets route `0.0.0.0/0` to the Internet Gateway.
- Application subnets route `0.0.0.0/0` to the NAT Gateway.
- Database subnets have no internet route.

This means users reach the ALB, the ALB reaches GovScale instances in private subnets, and the application reaches RDS in isolated database subnets. The EC2 instances can download packages or reach AWS services through NAT without being directly reachable from the internet.

### Cost note

The project uses one NAT Gateway to keep hackathon costs low. A production deployment should use one NAT Gateway per Availability Zone to remove the NAT Gateway as a single point of failure. [file:18]

## security.tf

This file creates security groups and controls network traffic.

Typical traffic flow:

```text
Internet
  -> ALB security group
  -> GovScale EC2 security group
  -> RDS security group
```

Security groups are used to ensure:

- The ALB accepts public HTTP traffic and, when configured, HTTPS traffic.
- Application instances accept traffic only from the ALB.
- RDS accepts PostgreSQL traffic only from application instances.
- RDS is not publicly accessible.

The HTTPS ingress rule on the ALB is conditional. It is created only when `domain_name` is not empty. [file:16]

## database.tf

This file creates the production database and application credentials.

### RDS PostgreSQL

The RDS instance uses:

- PostgreSQL 16
- `db.t4g.micro` by default
- 20 GB gp3 storage
- Encrypted storage
- Private database subnets
- No public accessibility
- Configurable Multi-AZ mode
- 1-day backup retention
- Automatic minor-version upgrades

The database name is `govscale`, and the database user is `govscale`. [file:14]

### Generated credentials

Terraform generates:

- A database password
- A 48-character Flask secret key
- A 20-character administrator password

These are stored in AWS Secrets Manager under a secret named:

```text
govscale-prod-credentials
```

The secret stores the Flask key, administrator password, database password, and RDS endpoint. [file:14]

### Production warning

The current settings are hackathon-friendly:

```hcl
skip_final_snapshot = true
deletion_protection = false
```

For real citizen data, change them to:

```hcl
skip_final_snapshot = false
deletion_protection = true
```

Also increase backup retention and enable Multi-AZ.

## iam.tf

This file creates the IAM roles needed by Elastic Beanstalk.

It creates:

- An Elastic Beanstalk service role
- An EC2 instance profile
- Policies allowing Elastic Beanstalk and EC2 to perform their managed operations

The EC2 instance profile is attached to the Beanstalk launch configuration, allowing instances to interact with AWS services securely. [file:13]

## secrets_access.tf

This file grants the EC2 instances permission to read the GovScale Secrets Manager secret.

This supports a least-privilege pattern: application instances can read the specific GovScale credential secret, but they do not receive broad Secrets Manager access. [file:13]

## beanstalk.tf

This is the main application-deployment file.

### Resources created

- Elastic Beanstalk application
- Elastic Beanstalk web-server environment
- Docker platform selection
- Load-balanced environment
- Auto Scaling configuration
- Health checks
- CloudWatch Logs streaming
- Application environment variables

### Networking

The EB environment uses:

- The GovScale VPC
- Private application subnets for EC2 instances
- Public subnets for the ALB
- No public IP on EC2 instances
- Nginx as the reverse proxy
- Container port `5000` [file:13]

### Load balancing and health

The ALB uses:

- `/health` as the health-check path
- HTTP 200 as the healthy response code
- 15-second health-check interval
- 20-second deregistration delay [file:13]

### Autoscaling

Scaling is based on average CPU utilization:

| Condition | Action |
|---|---|
| Average CPU above 55% | Add instances |
| Average CPU below 20% | Remove instances |
| Instance count | Between `min_instances` and `max_instances` |

With the default configuration, EB can scale from 1 to 4 `t3.medium` instances. [file:13][file:25]

### Deployment strategy

The default deployment policy is `Rolling` with a 50% batch size. This updates half of the instances at a time, helping avoid a full outage during deployment. [file:13]

Available policies include:

- `AllAtOnce`
- `Rolling`
- `RollingWithAdditionalBatch`
- `Immutable`
- `TrafficSplitting`

For stronger zero-downtime behavior, use `Immutable` or `TrafficSplitting`, understanding that these can consume more temporary capacity and cost.

### Environment variables

Non-secret configuration:

| Variable | Value |
|---|---|
| `GOVSCALE_ADMIN_EMAIL` | From `var.admin_email` |
| `WEB_CONCURRENCY` | `2` |
| `GUNICORN_THREADS` | `4` |

Sensitive configuration:

| Variable | Source |
|---|---|
| `GOVSCALE_SECRET_KEY` | Terraform-generated random password |
| `GOVSCALE_DATABASE_URI` | Constructed RDS PostgreSQL URI |
| `GOVSCALE_ADMIN_PASSWORD` | Terraform-generated random password |

These sensitive values are injected directly into the Elastic Beanstalk environment configuration. [file:13]

## domain.tf

This file is entirely optional.

If `domain_name = ""`:

- No Route 53 hosted-zone lookup occurs.
- No ACM certificate is requested.
- No HTTPS listener is created.
- No HTTPS security-group rule is created.
- The application remains available through the Elastic Beanstalk URL.

If `domain_name = "example.com"`:

- Terraform finds the existing Route 53 hosted zone.
- It requests an ACM certificate for the apex domain.
- If `create_www_record = true`, it also includes `www.example.com`.
- It creates DNS validation records.
- It waits for certificate validation.
- It creates alias A records for the apex and `www` domains.
- It attaches the certificate to the ALB HTTPS listener. [file:16][file:13]

This design means a user without a domain can still deploy and test the complete application safely.

## outputs.tf

After a successful apply, Terraform returns values such as:

- Elastic Beanstalk environment URL
- Custom HTTPS URL, empty when no domain is configured
- RDS endpoint
- Secrets Manager secret name

Use these outputs to connect the deployment guide, CI/CD workflow, and operational checks. [file:16]

## Resource dependency flow

```text
variables.tf
   |
   v
network.tf
   |
   +--> security.tf
   |         |
   |         v
   +--> database.tf
   |
   +--> iam.tf
   |
   +--> secrets_access.tf
   |
   v
beanstalk.tf
   |
   +--> domain.tf, optional
   |
   v
outputs.tf
```

## What gets created

With no custom domain:

- VPC and networking
- Security groups
- RDS PostgreSQL
- Secrets Manager secret
- IAM roles
- Elastic Beanstalk application and environment
- ALB and Auto Scaling Group
- CloudWatch Logs

With a custom domain, additionally:

- ACM certificate
- DNS validation records
- Route 53 alias records
- HTTPS ALB listener
- HTTPS security-group rule [file:16][file:13]
