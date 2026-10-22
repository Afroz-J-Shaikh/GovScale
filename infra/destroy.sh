#!/usr/bin/env bash
# Tears down everything Terraform manages, then removes what Terraform does not own:
#   - app-version zips that deploy-eb.yml uploaded to the shared Beanstalk bucket
#   - CloudWatch log groups that Beanstalk created itself
# The Terraform state bucket is NOT touched; delete it manually (all versions) afterwards.
set -euo pipefail
cd "$(dirname "$0")"

REGION="${AWS_REGION:-ap-south-1}"
APP="${EB_APP:-govscale}"
ENV_NAME="${EB_ENV:-govscale-prod}"

read -r -p "Destroy ALL GovScale infrastructure in $REGION? Type 'destroy' to continue: " answer
[ "$answer" = "destroy" ] || { echo "Aborted."; exit 1; }

terraform init -input=false
terraform destroy -input=false -auto-approve

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="elasticbeanstalk-$REGION-$ACCOUNT"

# Shared bucket: only remove this app's prefix, never the bucket itself.
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
  echo "Removing s3://$BUCKET/$APP/ ..."
  aws s3 rm "s3://$BUCKET/$APP/" --recursive --region "$REGION"
fi

echo "Removing leftover CloudWatch log groups ..."
for lg in $(aws logs describe-log-groups --region "$REGION" \
    --log-group-name-prefix "/aws/elasticbeanstalk/$ENV_NAME/" \
    --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --region "$REGION" --log-group-name "$lg"
  echo "  deleted $lg"
done

echo "Done. Remember to empty and delete the Terraform state bucket manually."
