resource "random_password" "db" {
  length  = 24
  special = false # keeps the connection URI free of characters that need escaping
}

resource "random_password" "secret_key" {
  length  = 48
  special = false
}

resource "random_password" "admin" {
  length  = 20
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name}-${var.environment}"
  subnet_ids = aws_subnet.db[*].id
}

resource "aws_db_instance" "main" {
  identifier = "${var.name}-${var.environment}"

  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  # RDS creates this database for you,
  db_name  = "govscale"
  username = "govscale"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  apply_immediately          = true

  # Hackathon settings. For real data: deletion_protection = true, skip_final_snapshot = false.
  skip_final_snapshot = true
  deletion_protection = false
}

resource "aws_secretsmanager_secret" "govscale" {
  name                    = "${var.name}-${var.environment}-credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "govscale" {
  secret_id = aws_secretsmanager_secret.govscale.id
  secret_string = jsonencode({
    secret_key        = random_password.secret_key.result
    admin_password   = random_password.admin.result
    database_password = random_password.db.result
    rds_endpoint     = aws_db_instance.main.address
  })
}