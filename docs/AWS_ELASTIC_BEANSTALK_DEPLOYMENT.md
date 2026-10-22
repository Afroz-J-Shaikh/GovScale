# GovScale AWS Elastic Beanstalk Deployment

This guide explains how to deploy GovScale to AWS using Terraform, Amazon Elastic Beanstalk, Amazon RDS PostgreSQL, an Application Load Balancer, and optional Route 53 HTTPS.

The deployment is designed so that it works even without a custom domain. If `domain_name` is set to an empty string, Terraform deploys GovScale using the Elastic Beanstalk URL over HTTP and does not create Route 53, ACM, or HTTPS resources. [file:16][file:13]

## Architecture deployed

```text
Users
  |
  v
Route 53, optional
  |
  v
Application Load Balancer
  |
  v
Elastic Beanstalk Auto Scaling Group
  |
  v
Dockerized GovScale application
  |
  v
Amazon RDS PostgreSQL
```

Terraform creates a multi-AZ VPC, public and private subnets, an Internet Gateway, a NAT Gateway, security groups, RDS PostgreSQL, Elastic Beanstalk, IAM roles, and Secrets Manager credentials. [file:18][file:14][file:13]

## Prerequisites

You need:

- An AWS account
- AWS CLI configured locally
- Terraform 1.10 or newer
- Docker
- An existing Amazon ECR repository named `govscale`, or another name configured through `ecr_repository_name`
- A GitHub repository if you want CI/CD deployment

Configure AWS credentials:

```bash
aws configure
```

Verify access:

```bash
aws sts get-caller-identity
```

## GitHub Actions OIDC Role

GitHub Actions uses an AWS IAM role through OIDC to deploy GovScale. This role was created manually in the AWS Console and is required for CI/CD deployment.

GitHub does not use long-lived AWS access keys. Instead, the GitHub Actions workflow assumes the IAM role using the role ARN stored in the GitHub secret `AWS_DEPLOY_ROLE_ARN`.

### Role purpose

The IAM role allows GitHub Actions to:

- Authenticate to Amazon ECR
- Push the GovScale Docker image
- Create an Elastic Beanstalk application version
- Deploy the application version to the `govscale-prod` Elastic Beanstalk environment
- Access S3 resources required by Elastic Beanstalk deployments
- Read CloudWatch Logs for deployment verification
- Manage related AWS resources used by the deployment workflow

### Policies attached

The following AWS managed policies are attached to the GitHub Actions OIDC role:

| AWS managed policy | Purpose |
|---|---|
| `AdministratorAccess-AWSElasticBeanstalk` | Create and deploy Elastic Beanstalk application versions and manage the Elastic Beanstalk environment |
| `AmazonDynamoDBFullAccess` | Supports DynamoDB-based tooling or locking if used by the workflow |
| `AmazonEC2ContainerRegistryFullAccess` | Authenticate to ECR and push GovScale Docker images |
| `AmazonEC2FullAccess` | Supports EC2 resources involved in Elastic Beanstalk deployments |
| `AmazonRDSDataFullAccess` | Allows RDS Data API operations if used |
| `AmazonRDSFullAccess` | Allows RDS visibility and management operations from CI/CD |
| `AmazonRoute53FullAccess` | Allows Route 53 DNS operations when domain resources are managed |
| `AmazonS3FilesFullAccess` | Allows S3 object operations required by deployment tooling |
| `AmazonS3FullAccess` | Allows access to Terraform state and Elastic Beanstalk deployment artifacts |
| `AutoScalingFullAccess` | Supports Auto Scaling operations during Elastic Beanstalk deployments |
| `AWSCertificateManagerFullAccess` | Allows ACM certificate operations for HTTPS |
| `CloudWatchLogsFullAccess` | Allows CI/CD to read deployment and application logs |
| `ElasticLoadBalancingFullAccess` | Supports Application Load Balancer operations associated with Elastic Beanstalk |
| `IAMFullAccess` | Allows IAM operations performed by the deployment workflow |
| `SecretsManagerReadWrite` | Allows reading or updating GovScale secrets in AWS Secrets Manager |

These policies are broad because GovScale is a hackathon demonstration project. For a production deployment, replace them with a custom least-privilege policy limited to the specific ECR repository, Elastic Beanstalk application and environment, S3 state bucket, and Secrets Manager secret.

### GitHub configuration

Store the manually created role ARN in GitHub as a repository secret:

```text
AWS_DEPLOY_ROLE_ARN
```

Example:

```text
arn:aws:iam::123456789012:role/github-actions-govscale-deploy
```

The GitHub Actions workflow uses this secret to assume the role through OIDC before building, pushing, and deploying the application.

## Step 1: Create the Terraform state bucket

Terraform uses a remote S3 backend so that your laptop and GitHub Actions share the same infrastructure state. The backend is configured in `infra/versions.tf`. [file:26]

Create the state bucket:

```bash
aws s3api create-bucket \
  --bucket govscale-tfstate \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
```

Enable versioning:

```bash
aws s3api put-bucket-versioning \
  --bucket govscale-tfstate \
  --versioning-configuration Status=Enabled
```

Enable default encryption:

```bash
aws s3api put-bucket-encryption \
  --bucket govscale-tfstate \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
```

Block public access:

```bash
aws s3api put-public-access-block \
  --bucket govscale-tfstate \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### Buckets used by this project

| Bucket | Purpose |
|---|---|
| `govscale-tfstate` | Terraform remote state storage |
| ECR repository | Stores built GovScale Docker images; this is a repository, not an S3 bucket |
| Elastic Beanstalk internal storage | EB uses AWS-managed storage for application versions; you do not need to create this manually |

This project uses S3 lockfile-based state locking through `use_lockfile = true`, so a separate DynamoDB lock table is not required. [file:26]

## Step 2: Configure Terraform variables

Go to the infrastructure directory:

```bash
cd infra
```

Copy the example variables file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region            = "ap-south-1"
name                  = "govscale"
environment           = "prod"
ecr_repository_name   = "govscale"
vpc_cidr              = "10.0.0.0/16"
instance_type         = "t3.medium"
min_instances         = 1
max_instances         = 4
deployment_policy     = "Rolling"
db_instance_class     = "db.t4g.micro"
db_engine_version     = "16"
db_multi_az           = false
admin_email           = "admin@example.com"

# Leave empty for Elastic Beanstalk URL only.
domain_name           = ""

# Set to true only when using a custom domain.
create_www_record     = true
```

### Domain behavior

| `domain_name` value | Result |
|---|---|
| `""` | Deploys using the Elastic Beanstalk HTTP URL; no Route 53, ACM, or HTTPS resources are created. |
| `"example.com"` | Creates Route 53 records, requests and validates an ACM certificate, adds an HTTPS listener, and maps the domain to the ALB. |

The empty-domain option is intentionally safe: Terraform uses conditional resources and only creates domain-related infrastructure when a domain is supplied. [file:16][file:13]

## Step 3: Initialize Terraform

```bash
terraform init
```

This downloads providers and connects to the S3 remote state backend.

## Step 4: Review the plan

```bash
terraform plan
```

Check that the plan includes:

- One VPC
- Two public subnets
- Two private application subnets
- Two private database subnets
- One Internet Gateway
- One NAT Gateway and Elastic IP
- Security groups
- RDS PostgreSQL instance
- Elastic Beanstalk application and environment
- IAM roles and instance profile
- Secrets Manager secret
- Optional Route 53, ACM, and HTTPS resources

## Step 5: Apply the infrastructure

```bash
terraform apply
```

Type `yes` when prompted.

The first apply can take 15–30 minutes because Elastic Beanstalk creates an environment, launch configuration, Auto Scaling Group, and load balancer.

## Step 6: Get deployment outputs

```bash
terraform output
```

Important outputs:

| Output | Meaning |
|---|---|
| `environment_url` | Elastic Beanstalk HTTP URL |
| `app_https_url` | Custom HTTPS URL; empty when no domain is configured |
| `rds_endpoint` | Private RDS endpoint |
| `secrets_manager_secret_name` | Secrets Manager secret containing generated credentials |

## Step 7: Retrieve generated credentials

Terraform generates the Flask secret key, administrator password, and database password. They are stored in AWS Secrets Manager. [file:14]

Retrieve the secret:

```bash
aws secretsmanager get-secret-value \
  --secret-name govscale-prod-credentials \
  --query SecretString \
  --output text
```

The secret contains:

```json
{
  "secret_key": "...",
  "admin_password": "...",
  "database_password": "...",
  "rds_endpoint": "..."
}
```

Use the `admin_password` value to log in as the administrator. Store it in a password manager; do not commit it to Git.

## Step 8: Deploy the application image

Terraform creates the Elastic Beanstalk environment, but your CI/CD pipeline deploys the actual GovScale Docker image from ECR.

The expected flow is:

1. GitHub Actions builds the Docker image.
2. GitHub Actions pushes the image to ECR.
3. GitHub Actions creates an Elastic Beanstalk application version.
4. GitHub Actions deploys that version to the Elastic Beanstalk environment.

Terraform intentionally ignores changes to `version_label` and `solution_stack_name` after the first apply, so CI/CD can update the running application version without Terraform reverting it. [file:13]

If deploying manually, use the Elastic Beanstalk Console or EB CLI to create and deploy an application version from the ECR image.

## Step 9: Verify deployment

Check Elastic Beanstalk health:

```bash
aws elasticbeanstalk describe-environment-health \
  --environment-name govscale-prod \
  --attribute-names All
```

Test the health endpoint:

```bash
curl http://<your-eb-url>/health
```

If you configured a domain:

```bash
curl https://example.com/health
```

Then open the application URL in a browser and log in using the administrator email and generated password.

## Scaling configuration

The Elastic Beanstalk environment is configured with:

- Load-balanced environment
- Application Load Balancer
- Health check path: `/health`
- Health check interval: 15 seconds
- Minimum instances: `min_instances`
- Maximum instances: `max_instances`
- CPU-based scaling: scale up above 55% average CPU and down below 20%
- Rolling deployment with 50% batch size
- Enhanced health reporting
- CloudWatch Logs streaming with 7-day retention [file:13]

For a stronger availability demo, set:

```hcl
min_instances = 2
db_multi_az   = true
```

Two application instances place one instance in each Availability Zone. Multi-AZ RDS adds database failover capability.

## Updating the application

After changing application code:

1. Push to the branch that triggers your GitHub Actions workflow.
2. Wait for the workflow to build and push the new image.
3. Confirm the new EB application version is deployed.
4. Check EB health and application logs.

## Destroying the environment

Warning: this deletes AWS resources created by Terraform, including RDS.

From the `infra/` directory:

```bash
terraform destroy
```

The repository also includes:

```bash
./destroy.sh
```

Before destroying resources you want to retain, enable deletion protection and final snapshots in `infra/database.tf`. The current hackathon configuration uses `skip_final_snapshot = true` and `deletion_protection = false`, which makes cleanup easier but is not appropriate for real citizen data. [file:14]
