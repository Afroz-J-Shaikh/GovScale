# GovScale Operations Guide

This guide explains how to operate GovScale after deployment: checking health, reading logs, scaling, deploying updates, handling failures, backing up data, and cleaning up AWS resources.

## Daily health checks

### Application health endpoint

Test the application:

```bash
curl -I http://<your-eb-url>/health
```

With HTTPS:

```bash
curl -I https://example.com/health
```

An HTTP 200 response means the application is healthy.

The Elastic Beanstalk ALB uses `/health` with an expected HTTP 200 response and checks every 15 seconds. [file:13]

### Elastic Beanstalk health

Open:

```text
AWS Console -> Elastic Beanstalk -> govscale-prod -> Health
```

Health meanings:

| Status | Meaning |
|---|---|
| Green | Environment is healthy |
| Yellow | Warning; investigate logs and metrics |
| Red | Environment is failing; act immediately |
| Grey | Health information is not yet available |

Check from the CLI:

```bash
aws elasticbeanstalk describe-environment-health \
  --environment-name govscale-prod \
  --attribute-names All
```

## Logs

### Elastic Beanstalk logs

Request recent logs:

```bash
aws elasticbeanstalk request-environment-info \
  --environment-name govscale-prod \
  --type tail

aws elasticbeanstalk retrieve-environment-info \
  --environment-name govscale-prod \
  --type tail
```

### CloudWatch Logs

The EB environment streams logs to CloudWatch with seven-day retention. [file:13]

Open:

```text
AWS Console -> CloudWatch -> Log groups
```

Look for Elastic Beanstalk log groups related to:

- Web application
- Nginx access logs
- Nginx error logs
- EB platform logs

Useful searches:

- `ERROR`
- `Traceback`
- `502`
- `503`
- `timeout`
- `database`
- `psycopg2`

## Monitoring

Monitor these signals:

| Signal | Where | Why it matters |
|---|---|---|
| ALB target health | EB console / CloudWatch | Detects unhealthy application instances |
| CPU utilization | CloudWatch | Drives Auto Scaling |
| Request count | ALB / CloudWatch | Shows traffic load |
| Latency | ALB / CloudWatch | Detects slowdowns |
| HTTP 4xx and 5xx | ALB / application logs | Detects client and server errors |
| RDS CPU | CloudWatch | Detects database pressure |
| RDS connections | CloudWatch | Detects connection exhaustion |
| RDS storage | CloudWatch | Prevents disk-full failures |
| EB environment health | EB console | Overall deployment status |

## Scaling

### Automatic scaling

The EB Auto Scaling Group scales based on average CPU utilization:

- Scale out above 55% CPU
- Scale in below 20% CPU
- Minimum and maximum instance counts come from Terraform variables [file:13]

Default values:

```hcl
min_instances = 1
max_instances = 4
```

### Manual scaling

To change scaling limits, update `infra/terraform.tfvars`:

```hcl
min_instances = 2
max_instances = 6
```

Apply:

```bash
cd infra
terraform plan
terraform apply
```

For a high-availability demonstration, use:

```hcl
min_instances = 2
max_instances = 4
```

This places one instance in each of the two application subnets and improves resilience against an Availability Zone issue. [file:18]

## Deploying an update

Preferred method:

1. Push the change to `main`.
2. GitHub Actions builds and pushes a new Docker image to ECR.
3. GitHub Actions creates and deploys a new EB application version.
4. Monitor EB health during deployment.

The Terraform configuration ignores later changes to `version_label`, so CI/CD can update the deployed version without Terraform reverting it. [file:13]

### Deployment policy

The default is:

```hcl
deployment_policy = "Rolling"
```

With a 50% batch size, EB updates half of the instances at a time. [file:13]

For stronger zero-downtime behavior:

```hcl
deployment_policy = "Immutable"
```

Immutable deployments launch a new set of instances, validate them, and then switch traffic. They are safer but can be slower and more expensive.

## Handling common incidents

### EB health is red

1. Check EB events.
2. Check CloudWatch Logs.
3. Test `/health`.
4. Check whether RDS is reachable.
5. Check whether the latest deployment introduced an error.
6. Roll back if needed.

### Application returns 502 or 503

Possible causes:

- Gunicorn is not running
- Container failed its health check
- Application crashed after startup
- Database connection failed
- Security-group misconfiguration

Check EB logs first, then RDS connectivity and security groups.

### RDS connection errors

Check:

- RDS instance status
- RDS endpoint
- Database security group
- Application security group
- Database credentials in Secrets Manager
- VPC routing

RDS is intentionally private and should never be publicly accessible. [file:14]

### Traffic spike

1. Confirm EB is scaling.
2. Check CPU, latency, and target health.
3. Increase `max_instances` if the ceiling is too low.
4. Check RDS CPU and connections.
5. Consider increasing Gunicorn workers only after reviewing instance CPU and memory.

### Terraform state lock

If Terraform reports a state lock:

1. Confirm no other `terraform apply` is running.
2. Check the S3 lockfile.
3. Wait for the active operation to finish.
4. Remove a stale lock only after confirming no Terraform process is running.

This project uses S3 lockfile locking rather than DynamoDB locking. [file:26]

## Backups and recovery

### RDS backups

The current configuration retains one day of automated backups:

```hcl
backup_retention_period = 1
```

For real data, increase this value and enable deletion protection. [file:14]

### Restore procedure

1. Open Amazon RDS.
2. Select the GovScale database.
3. Choose **Actions -> Restore to point in time** or select a snapshot.
4. Create a restored instance.
5. Update the application database endpoint.
6. Validate the application.
7. Switch traffic only after verification.

### Terraform state backup

S3 versioning protects previous Terraform state versions. Never edit or delete Terraform state manually unless you fully understand the consequences.

## Safe cleanup

To avoid unexpected AWS charges, destroy resources when finished:

```bash
cd infra
terraform destroy
```

Or use:

```bash
./destroy.sh
```

Before destroying a database with real data:

```hcl
deletion_protection = true
skip_final_snapshot = false
```

The current hackathon configuration allows easier teardown by skipping the final snapshot and disabling deletion protection. [file:14]

## Operational runbook

| Situation | First action | Next action |
|---|---|---|
| Site down | Check EB health | Check ALB, EC2, and application logs |
| Slow site | Check ALB latency and CPU | Scale out or inspect database load |
| Deployment failed | Check GitHub Actions logs | Check EB events and health |
| Database unreachable | Check RDS status | Check security groups and credentials |
| Certificate pending | Check Route 53 validation records | Confirm nameservers and DNS propagation |
| High error rate | Check CloudWatch Logs | Roll back recent deployment if needed |
| Unexpected cost | Check AWS Cost Explorer | Identify NAT, EC2, RDS, and load-balancer charges |
