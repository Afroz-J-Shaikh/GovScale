# GovScale

GovScale is a scalable student scholarship and examination portal built for a hackathon to demonstrate how DevOps and AWS cloud infrastructure can keep citizen-facing applications available during sudden traffic spikes.

Government portals often face heavy load during scholarship deadlines, examination registrations, and result announcements. GovScale demonstrates how containerization, infrastructure as code, automated deployment, managed databases, load balancing and autoscaling can help such applications remain reliable at scale.

## Features

- Student registration, login, and profile management
- Scholarship discovery and eligibility-based applications
- Exam registration, timed examination, scoring, and results
- Scholarship reward tracking and simulated payout workflow
- Admin dashboard for scholarships, applications, exams, and rewards
- Notifications for important student and application events
- PostgreSQL-backed production configuration
- Dockerized application with Gunicorn
- Terraform-based AWS infrastructure
- Elastic Beanstalk deployment with load balancing and autoscaling
- HTTPS using AWS Certificate Manager and Route 53

## Technology Stack

| Area | Technology |
|---|---|
| Backend | Python, Flask, SQLAlchemy |
| Database | PostgreSQL |
| Application server | Gunicorn |
| Containerization | Docker, Docker Compose |
| Cloud | AWS Elastic Beanstalk, RDS, ALB, Route 53, ACM, Secrets Manager |
| Infrastructure as Code | Terraform |
| CI/CD | GitHub Actions |
| Domain and HTTPS | Route 53, AWS Certificate Manager |

## Quick Local Start

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd govscale
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set:

```env
GOVSCALE_SECRET_KEY=<long-random-secret>
GOVSCALE_ADMIN_EMAIL=<your-admin-email>
GOVSCALE_ADMIN_PASSWORD=<strong-admin-password>
POSTGRES_PASSWORD=<strong-database-password>
```

Generate a secure Flask secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Never commit the real `.env` file to Git.

### 3. Run locally with Docker

```bash
docker compose up --build
```

Then open:

```text
http://localhost:5000
```

Docker Compose starts PostgreSQL, prepares the database, seeds institutions, creates the initial administrator, and launches the GovScale application.

### 4. Stop the application

```bash
docker compose down
```

To remove database data as well:

```bash
docker compose down -v
```

## Default Administrator

The administrator account is created from the values in `.env`:

- Email: value of `GOVSCALE_ADMIN_EMAIL`
- Password: value of `GOVSCALE_ADMIN_PASSWORD`

Change these values before deploying publicly. Do not use default or example credentials in production.

## Documentation

| Document | Purpose |
|---|---|
| [Project Guide](docs/PROJECT_GUIDE.md) | What GovScale is, the problem it solves, features, and user flows |
| [Local Setup](docs/LOCAL_SETUP.md) | Complete local development and Docker setup |
| [AWS Elastic Beanstalk Deployment](docs/AWS_ELASTIC_BEANSTALK_DEPLOYMENT.md) | Full AWS deployment guide, including Terraform state buckets and Elastic Beanstalk |
| [Infrastructure Guide](docs/INFRASTRUCTURE_GUIDE.md) | Explanation of every Terraform file and AWS resource |
| [GitHub Actions Guide](docs/GITHUB_ACTIONS_GUIDE.md) | CI/CD workflows, secrets, and deployment process |
| [Domain and HTTPS Guide](docs/DOMAIN_HTTPS_GUIDE.md) | Route 53 hosted zone, GoDaddy nameservers, ACM certificate, and HTTPS setup |
| [Security Guide](docs/SECURITY_GUIDE.md) | Application, container, AWS, database, and secret security |
| [Operations Guide](docs/OPERATIONS_GUIDE.md) | Monitoring, logs, scaling, backups, recovery, and cleanup |

## Project Goal

GovScale is not intended to replace a production government platform. It is a demonstration project showing how modern DevOps practices can make public-service applications more scalable, available, secure, and maintainable.