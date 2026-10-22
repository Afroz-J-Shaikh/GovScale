# GovScale Security Guide

This guide explains the security controls used by GovScale across the application, container, AWS infrastructure, database, and CI/CD layers.

GovScale is a hackathon demonstration project. Some workflows, especially reward payouts, are simulated and must not be treated as production financial infrastructure.

## Security principles

GovScale follows these principles:

- No secrets in Git
- Required AWS access
- Private database networking
- Encrypted secrets and storage
- HTTPS for user traffic
- Non-root containers
- Restricted container capabilities
- Automated dependency updates
- Health checks and centralized logging

## Application security

### Authentication and sessions

GovScale uses Flask-based authentication and session management.

Security controls include:

- Password hashing
- Flask login sessions
- CSRF protection
- Admin-role authorization
- Separate student and administrator access

Students cannot access administrator routes. Administrator access is protected through authentication and an admin-role check. [file:11]

### Secret key

The Flask secret key signs sessions and must be kept secret.

Locally, set it in `.env`:

```env
GOVSCALE_SECRET_KEY=<long-random-value>
```

Generate it with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

On AWS, Terraform generates a 48-character secret key and injects it into the Elastic Beanstalk environment. [file:14][file:13]

### Administrator credentials

The initial administrator email and password come from configuration:

- Local: `.env`
- AWS: Terraform-generated password stored in Secrets Manager

Never use default or example credentials in a publicly accessible deployment. [file:28][file:14]

### Simulated payments

Payment details and reward payouts are simulated. GovScale records payout attempts, recipient details, status, timestamps, and failure reasons for auditability, but it does not process real financial transactions. [file:11]

Do not enter real card numbers, bank credentials, or other sensitive financial data.

## Container security

The Docker image uses a multi-stage build:

1. A builder stage installs Python dependencies.
2. A runtime stage copies only the required application files.
3. The runtime runs as a non-root `govscale` user.
4. Gunicorn serves the Flask application. [file:10]

Security controls include:

| Control | Benefit |
|---|---|
| Non-root user | Limits damage if the container is compromised |
| Read-only root filesystem | Prevents unexpected writes to the container filesystem |
| Writable `/tmp` and `/app/instance` only | Gives the app only the writable locations it needs |
| Dropped capabilities | Removes unnecessary Linux privileges |
| `no-new-privileges` | Prevents gaining additional privileges |
| CPU, memory, and process limits | Limits resource exhaustion |
| Health check | Detects unhealthy application containers |
| Configurable Gunicorn workers and threads | Helps tune concurrency safely |

The Compose application service uses a read-only filesystem, temporary filesystems for `/tmp` and `/app/instance`, dropped capabilities, resource limits, and a `/health` health check. [file:9]

## AWS network security

The deployment uses a layered network:

```text
Internet
  -> ALB
  -> Private EB instances
  -> Private RDS
```

### VPC design

The VPC contains:

- Two public subnets for the ALB and NAT Gateway
- Two private application subnets for Elastic Beanstalk EC2 instances
- Two private database subnets for RDS
- One Internet Gateway
- One NAT Gateway
- Separate route tables for public, application, and database traffic [file:18]

### Database isolation

RDS is:

- Deployed in private database subnets
- Not publicly accessible
- Reachable only from the application security group
- Placed in database subnets with no internet route [file:14][file:18]

This prevents direct internet access to PostgreSQL.

### Elastic Beanstalk instances

EB instances run in private subnets and do not receive public IP addresses. They use the NAT Gateway for outbound access, such as package updates or AWS API calls. [file:13][file:18]

## Secrets management

### Local development

Secrets are stored in `.env`, which must never be committed.

The repository’s `.gitignore` should exclude:

- `.env`
- Terraform state files
- Terraform plan files
- Credentials and key material

### AWS deployment

Terraform generates and stores these values in AWS Secrets Manager:

- Flask secret key
- Administrator password
- Database password
- RDS endpoint [file:14]

The EC2 instances receive permission to read the specific GovScale secret, following a least-privilege pattern. [file:13]

### GitHub Actions

Use GitHub OIDC rather than long-lived AWS access keys.

Store only:

- AWS region
- IAM role ARN
- ECR repository name

Do not store AWS secret access keys, database passwords, or the Flask secret key in GitHub. [file:14]

## HTTPS and TLS

When a custom domain is configured, GovScale uses:

- AWS Certificate Manager
- Route 53 DNS validation
- ALB HTTPS listener on port 443
- Modern TLS security policy: `ELBSecurityPolicy-TLS13-1-2-2021-06` [file:16][file:13]

Without a custom domain, the application is available over the Elastic Beanstalk HTTP URL. This is acceptable for local-style demonstration but HTTPS should be enabled before exposing the platform publicly.

## IAM security

The deployment uses dedicated IAM roles for:

- Elastic Beanstalk service operations
- EC2 instances
- Secrets Manager access

Follow these additional practices:

- Use OIDC for GitHub Actions.
- Avoid administrator-level IAM users for routine deployment.
- Scope deployment permissions to ECR, Elastic Beanstalk, S3, and CloudWatch Logs.
- Review IAM policies before production use.
- Enable AWS CloudTrail for audit visibility.

## Database security

Current RDS protections:

- Encrypted storage
- Private subnets
- No public accessibility
- Security-group restriction to application instances
- Automated minor-version upgrades
- Backup retention of one day [file:14]

For real citizen data, strengthen this further:

- Enable Multi-AZ
- Enable deletion protection
- Disable `skip_final_snapshot`
- Increase backup retention
- Use a stronger instance class
- Restrict security-group access as tightly as possible
- Use AWS KMS customer-managed keys if required

## Dependency security

The repository includes Dependabot configuration to keep dependencies updated. [file:4]

Recommended practices:

- Review Dependabot pull requests weekly.
- Prioritize security updates.
- Rebuild and redeploy after dependency updates.
- Scan Docker images before production deployment.
- Pin or review major dependency upgrades carefully.

## Logging and monitoring

Elastic Beanstalk is configured with:

- Enhanced health reporting
- CloudWatch Logs streaming
- Seven-day log retention
- `/health` endpoint monitoring
- ALB health checks every 15 seconds [file:13]

For operational security, monitor:

- Failed logins
- Administrator actions
- Application errors
- EB environment health
- RDS CPU, storage, and connections
- ALB target health
- Unusual traffic spikes

## Security checklist before public demo

- [ ] Changed the administrator email and password
- [ ] Generated a unique Flask secret key
- [ ] Confirmed `.env` is not committed
- [ ] Enabled HTTPS with a custom domain, if publicly accessible
- [ ] Confirmed RDS is private
- [ ] Confirmed security groups allow only required traffic
- [ ] Enabled GitHub branch protection
- [ ] Reviewed IAM permissions
- [ ] Reviewed Dependabot updates
- [ ] Confirmed payment and payout workflows are clearly marked as simulated
