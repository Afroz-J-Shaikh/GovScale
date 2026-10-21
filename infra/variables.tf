variable "aws_region" {
  type    = string
  default = "ap-south-1" # must be the same region as your ECR repository
}

variable "name" {
  type    = string
  default = "govscale"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "ecr_repository_name" {
  description = "Existing ECR repository that CI pushes to (your ECR_REPOSITORY secret)."
  type        = string
  default     = "govscale"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "min_instances" {
  type    = number
  default = 1 # two instances = one per AZ = survives an AZ failure and deploys without downtime
}

variable "max_instances" {
  type    = number
  default = 4
}

variable "deployment_policy" {
  description = "AllAtOnce | Rolling | RollingWithAdditionalBatch | Immutable | TrafficSplitting"
  type        = string
  default     = "Rolling"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_engine_version" {
  type    = string
  default = "16"
}

variable "db_multi_az" {
  type    = bool
  default = false # flip to true for the demo if you want to show DB failover
}

variable "admin_email" {
  type    = string
  default = "admin@gmail.com"
}
