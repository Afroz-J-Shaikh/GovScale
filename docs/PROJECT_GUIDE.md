# GovScale Project Guide

GovScale is a student scholarship and examination portal created for a hackathon to demonstrate how DevOps practices and AWS cloud infrastructure can help citizen-facing applications remain available during sudden traffic spikes.

## Problem Statement

Government and public-service websites often experience extreme traffic during high-demand events, such as:

- Scholarship application deadlines
- Entrance or scholarship examination registrations
- Result announcements
- Document submission windows
- Emergency public notifications
- New Policy Rollouts

When many users access these services at the same time, a poorly prepared application can become slow, return errors, or become completely unavailable. For students and citizens, this can mean missed deadlines, failed submissions, or inability to access important information.

GovScale demonstrates how a modern cloud-native architecture can reduce these risks through:

- Horizontal scaling with multiple application instances
- Load balancing across healthy instances
- Managed PostgreSQL database
- Infrastructure defined as code
- Automated build and deployment pipelines
- Health checks and monitoring
- Secure configuration and HTTPS

## What GovScale Does

GovScale provides a simulated scholarship and examination platform where students can:

1. Create an account and complete their academic profile
2. Browse available scholarships
3. Check eligibility and apply for scholarships
4. Register for scholarship-linked examinations
5. Attempt an exam during its scheduled window
6. View exam results and review answers
7. Track scholarship applications and rewards
8. Receive notifications about important updates
9. Add simulated payment details for reward disbursal

Administrators can:

1. Manage scholarships and examination schedules
2. Review student applications
3. Import examination questions
4. View exam submissions and results
5. Approve or reject scholarship applications
6. Manage scholarship rewards and simulated payouts
7. Monitor platform activity from the admin dashboard

## User Roles

### Student

Students are the primary users of GovScale. They can register, complete their profile, discover scholarships, apply for opportunities, participate in exams, and track their applications.

A student must declare Indian citizenship during registration. Some scholarships also require academic information such as education level, institution, grading system, academic score, and annual family income.

### Administrator

Administrators manage the platform. They can create and update scholarships, configure exams, import questions, review applications, and manage reward payouts.

Administrator access is protected through authentication and an admin-role check. Ordinary students cannot access admin routes.

## Core Features

### Scholarship Discovery

Students can browse active scholarships and view details such as:

- Scholarship title and description
- Category
- Award amount
- Eligibility requirements
- Education level
- Application deadline
- Linked examination, if applicable

### Eligibility and Applications

GovScale checks whether a student meets the requirements before allowing an application. Depending on the scholarship, eligibility may depend on:

- Education category
- Study level
- Academic score or CGPA
- Annual family income

A student can apply only once for a particular scholarship. The database enforces this uniqueness constraint.

### Examination Flow

For exam-based scholarships, GovScale supports:

- Exam creation and scheduling
- Student registration
- Question-paper management
- Timed examination access
- Multiple-choice question submission
- Automatic scoring
- Pass/fail result calculation
- Answer review

Exam submissions are stored with the student’s answers, score, total marks, percentage, and pass status.

### Scholarship Rewards

When a student becomes eligible for a reward, GovScale creates a scholarship reward record. Administrators can review the reward and initiate a simulated payout.

The payout workflow records attempts, recipient details, status, timestamps, and failure reasons. This demonstrates an auditable workflow without handling real financial transactions.

### Notifications

GovScale stores notifications in the database so students can see important updates even if they were not online when the event occurred.

Notification dispatch uses an event key to prevent the same notification from being sent repeatedly to the same user.

## How DevOps Helps

GovScale is designed to show how DevOps practices address the reliability problems faced by high-traffic public platforms.

### Scalability

The application runs on AWS Elastic Beanstalk behind a load balancer. During high demand, Elastic Beanstalk can launch additional EC2 instances. When demand falls, it can scale back down.

This means the application can handle more simultaneous users without manually provisioning servers.

### Availability

The Application Load Balancer distributes traffic across healthy instances. If one instance fails its health check, the load balancer stops sending traffic to it while Elastic Beanstalk replaces or repairs it.

The application exposes a `/health` endpoint that can be used for health monitoring.

### Infrastructure as Code

All major AWS resources are defined using Terraform. This makes the infrastructure:

- Repeatable
- Reviewable
- Version controlled
- Easier to recreate
- Easier to destroy safely

Instead of manually clicking through the AWS Console, the team can define the environment in code and apply it consistently.

### Containerization

The application is packaged as a Docker image. Docker ensures that the application runs with the same dependencies and configuration across local development, testing, and AWS.

The container uses Gunicorn as the application server and supports configurable workers and threads.

### CI/CD

GitHub Actions can automate testing, image building, and deployment. This reduces manual deployment mistakes and makes it easier to release updates safely.

### Security

GovScale uses several security practices:

- Password hashing
- CSRF protection
- Flask login sessions
- Admin authorization
- PostgreSQL instead of a file-based database in production
- Environment-based secrets
- HTTPS through AWS Certificate Manager
- Non-root Docker container
- Restricted container capabilities and read-only filesystem settings

## High-Level Architecture

```text
Users
  |
  v
Route 53 DNS
  |
  v
AWS Certificate Manager / HTTPS
  |
  v
Application Load Balancer
  |
  v
Elastic Beanstalk Auto Scaling Group
  |
  v
GovScale Docker containers
  |
  v
Amazon RDS PostgreSQL
```

Supporting components:

- Terraform provisions and manages the AWS infrastructure.
- GitHub Actions builds and deploys application updates.
- AWS Secrets Manager stores sensitive configuration.
- Amazon S3 stores Terraform state and deployment artifacts.
- Amazon CloudWatch provides logs and monitoring.

## Why This Matters

GovScale uses a scholarship and examination portal as its example, but the same architecture applies to many citizen-facing services:

- Exam result portals
- Admission systems
- Tax filing platforms
- Public welfare schemes
- Vaccine or health registration systems
- Disaster-relief application portals

The central idea is simple: public services should remain available when citizens need them most. DevOps makes that possible through automation, scalability, observability, and repeatable infrastructure.