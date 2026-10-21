# GovScale on Elastic Beanstalk, all through Terraform

Internet -> ALB (public subnets) -> EC2 / Docker (private app subnets, via NAT) -> RDS (private DB subnets, no internet route)

## One-time setup

**0. State bucket** (Terraform's memory; keeps laptop and GitHub Actions in sync)

    aws s3api create-bucket --bucket <unique-name> --region ap-south-1 \
      --create-bucket-configuration LocationConstraint=ap-south-1
    aws s3api put-bucket-versioning --bucket <unique-name> --versioning-configuration Status=Enabled

Put `<unique-name>` (and your region) in `infra/versions.tf`.


**1. Turn on CD**: GitHub repo > Settings > Variables: `ENABLE_ECR_PUSH=true`, `ENABLE_EB_DEPLOY=true`. Push to `main`. CI builds, scans, pushes `:<sha7>` to ECR, then `deploy-eb.yml` deploys exactly that tag.

**2. Use it**

    terraform output app_url
    terraform output -raw admin_password   # login: admin_email output

## Debugging (no SSH needed)

    aws ssm start-session --target <instance-id>
    sudo docker ps -a
    sudo docker logs $(sudo docker ps -aq | head -1)
    sudo tail -n 100 /var/log/eb-engine.log

Or Beanstalk console > Logs > Request full logs. Logs also stream to CloudWatch.

## Rollback

    aws elasticbeanstalk update-environment --environment-name govscale-prod --version-label <older-label>

## Cost

Roughly $3-4 per day (NAT gateway, ALB, 2x t3.small, RDS). `terraform destroy` when you are not demoing.
