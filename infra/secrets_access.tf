# Lets the Beanstalk instances read the one secret the postdeploy hook needs.
data "aws_iam_policy_document" "ec2_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.govscale.arn]
  }
}

resource "aws_iam_role_policy" "ec2_secret" {
  name   = "read-govscale-secret"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_secret.json
}