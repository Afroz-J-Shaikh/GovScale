# GovScale GitHub Actions Guide

This guide explains the CI/CD workflow for GovScale: how code changes are built, pushed to Amazon ECR, and deployed to AWS Elastic Beanstalk.

## CI/CD goal

The pipeline should ensure that every application change is:

- Built consistently as a Docker image
- Pushed to a private Amazon ECR repository
- Deployed to Elastic Beanstalk
- Verified through health checks and logs

This removes manual deployment steps and makes releases repeatable.

## Required

## AWS authentication through OIDC

GovScale uses GitHub OIDC for AWS authentication. A GitHub Actions workflow assumes a manually created AWS IAM role using the role ARN stored in the GitHub secret `AWS_DEPLOY_ROLE_ARN`.

This avoids storing long-lived AWS access keys in GitHub.

### Manually created IAM role

The IAM role was created manually in the AWS Console. It is not managed by Terraform.

### Role purpose

The IAM role allows GitHub Actions to:

- Authenticate to Amazon ECR
- Push the GovScale Docker image
- Create an Elastic Beanstalk application version
- Deploy the application version to the `govscale-prod` Elastic Beanstalk environment
- Access S3 resources required by Elastic Beanstalk deployments
- Read CloudWatch Logs for deployment verification
- Manage related AWS resources used by the deployment workflow

### Policies attached to the role

The following AWS managed policies are attached to the GitHub Actions OIDC role:

| AWS managed policy | Purpose |
|---|---|
| `AdministratorAccess-AWSElasticBeanstalk` | Create and deploy Elastic Beanstalk application versions and manage the environment |
| `AmazonDynamoDBFullAccess` | Supports DynamoDB-based tooling or locking if used |
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

These permissions are intentionally broad for this hackathon project. For production, replace them with a custom least-privilege policy scoped to the exact ECR repository, Elastic Beanstalk application and environment, S3 state bucket, and Secrets Manager secret.

## Required GitHub secrets

| Secret | Example | Purpose |
|---|---|---|
| `AWS_REGION` | `ap-south-1` | AWS deployment region |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/github-actions-govscale-deploy` | IAM role assumed through OIDC for CI/CD deployment |
| `ECR_REPOSITORY` | `govscale` | ECR repository name |
| `ECR_REGISTRY` | Optional; can be derived from ECR login | ECR registry URI |

The `AWS_DEPLOY_ROLE_ARN` role was created manually in AWS. It is required for CI/CD and allows GitHub Actions to deploy GovScale to Elastic Beanstalk without storing long-lived AWS access keys.

Do not store AWS access keys in GitHub Secrets if you can use OIDC.

## Recommended workflow

```text
Push or pull request
        |
        v
GitHub Actions
        |
        +--> Lint / test
        |
        +--> Build Docker image
        |
        +--> Push image to Amazon ECR
        |
        +--> Create EB application version
        |
        +--> Deploy to Elastic Beanstalk
        |
        v
GovScale application updated
```

## Recommended triggers

Use separate behavior for pull requests and main-branch pushes.

```yaml
on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  workflow_dispatch:
```

| Trigger | Purpose |
|---|---|
| `pull_request` | Validate code and build the image without deploying |
| `push` to `main` | Build, publish, and deploy |
| `workflow_dispatch` | Allow a manual deployment from the GitHub Actions tab |

## Recommended jobs

### 1. Test job

Run application checks before building or deploying.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run checks
        run: |
          python -m compileall app.py scripts
```

Add unit or integration tests here as the project grows.

### 2. Build and push job

This job builds the Docker image and pushes it to ECR.

```yaml
  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Login to Amazon ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push image
        env:
          ECR_REGISTRY: ${{ steps.ecr.outputs.registry }}
          ECR_REPOSITORY: ${{ secrets.ECR_REPOSITORY }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" .
          docker push "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG"
```

The image tag should use the Git commit SHA so every deployment is traceable to an exact commit.

### 3. Deploy job

This job deploys the newly pushed image to Elastic Beanstalk.

```yaml
  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Deploy to Elastic Beanstalk
        env:
          ECR_REGISTRY: ${{ secrets.ECR_REGISTRY }}
          ECR_REPOSITORY: ${{ secrets.ECR_REPOSITORY }}
          IMAGE_TAG: ${{ github.sha }}
          EB_APPLICATION: govscale
          EB_ENVIRONMENT: govscale-prod
        run: |
          pip install awsebcli

          eb init "$EB_APPLICATION" \
            --region "$AWS_REGION" \
            --platform "64bit Amazon Linux 2023 running Docker"

          eb deploy "$EB_ENVIRONMENT" \
            --label "govscale-${IMAGE_TAG}" \
            --message "Deploy commit ${GITHUB_SHA}"
```

Your Elastic Beanstalk environment is expected to be named `govscale-prod`, based on the Terraform naming pattern `${var.name}-${var.environment}`. [file:13]

## Branch protection

Protect the `main` branch:

- Require pull requests before merging.
- Require at least one approval.
- Require status checks to pass.
- Do not allow force pushes.
- Do not allow direct deployment from unreviewed branches.

This ensures that only reviewed code reaches AWS.

## Deployment safety

Use GitHub Environments for production protection:

1. In GitHub, create an environment named `production`.
2. Add required reviewers.
3. Restrict the environment to the `main` branch.
4. Reference it in the deploy job:

```yaml
deploy:
  environment: production
```

This adds a manual approval gate before AWS deployment.

## Reading workflow failures

| Failure | Likely cause | What to check |
|---|---|---|
| AWS credential error | OIDC role, region, or trust policy issue | Role ARN, GitHub repository condition, AWS region |
| ECR login failure | Missing ECR permissions | IAM policy and repository name |
| Docker build failure | Code, dependency, or Dockerfile issue | Build logs and `requirements.txt` |
| EB deploy timeout | Environment unhealthy or database unreachable | EB health, RDS security groups, application logs |
| Health check failure | App did not start or `/health` failed | EB logs and CloudWatch Logs |
| Terraform state lock | Another apply is running or a stale lock exists | S3 lockfile and recent Terraform runs |

## Dependabot

The repository includes `.github/dependabot.yml`, which helps keep dependencies current. Review Dependabot pull requests regularly, especially updates to Flask, SQLAlchemy, Gunicorn, and other runtime dependencies. [file:4]

## What not to put in GitHub

Never commit:

- `.env`
- AWS access keys
- Database passwords
- Flask secret keys
- Administrator passwords
- Terraform state files
- Terraform plan files containing sensitive values

The AWS deployment generates its own secret values and stores them in AWS Secrets Manager. [file:14]
