# Deploying the Courses API on AWS

## 1. Services and architecture

```
Users -> Route 53 -> ALB (HTTPS, ACM cert, public subnets, 2 AZs)
                      |
                      v
              ECS Fargate service (private subnets, 2+ tasks across 2 AZs)
                      |
                      v
              RDS PostgreSQL (Multi-AZ, private subnets)

GitHub Actions --OIDC--> ECR (images tagged by commit SHA) --> ECS
Logs and metrics: CloudWatch.  DB credentials: Secrets Manager.
```

| Service | Why |
|---|---|
| **ECS on Fargate** | We already ship a container. Fargate runs it with no servers to patch, and ECS gives rolling deploys, health checks and rollback out of the box. EKS is more than one small API needs; Lambda would mean reworking the app. |
| **ALB** | TLS termination, health checks on `/health`, spreads traffic across tasks, and drains connections during deploys. |
| **ECR** | Private image registry next to ECS, with image scanning. Tags are immutable so a SHA always means the same image. |
| **RDS PostgreSQL** | Durable, shared data store (see section 5). |
| **Secrets Manager** | DB password injected into the task at start, never in the image or the repo. |
| **CloudWatch** | Container logs, ALB and ECS metrics, alarms. |

Tasks sit in private subnets; only the ALB is public. The task security group accepts
traffic only from the ALB, and the DB security group only from the tasks.

## 2. From a commit on `main` to production

1. A PR is merged to `main`. CI runs lint and tests.
2. CI builds the image with `APP_VERSION=<commit SHA>`, starts it, and checks `/health`.
3. CI pushes that same image to ECR tagged with the SHA (GitHub OIDC role, no stored keys).
4. A deploy job (run after the push, gated by a GitHub `production` environment so it can
   require an approval) registers a new ECS task definition revision pointing at the new
   SHA and updates the service.
5. ECS does a rolling deploy (minimum healthy 100%, maximum 200%): it starts new tasks,
   waits until the ALB health check passes, moves traffic to them, then drains and stops
   the old tasks. The container handles SIGTERM, so in-flight requests finish.
6. The job waits for the service to become stable and fails loudly if it does not.

Every deploy is a specific SHA, so we always know exactly what is running, and
`/health` reports it.

## 3. How do we know a deploy is healthy?

- **During the deploy:** new tasks must pass the ALB health check on `/health` before they
  get traffic. If they crash or fail the check, old tasks keep serving.
- **Right version:** `/health` returns the commit SHA, so the deploy job can confirm the
  new version is the one answering.
- **After the deploy:** CloudWatch alarms on ALB target 5xx rate, p95 latency, unhealthy
  host count and ECS task restarts. I would watch these for about 10 to 15 minutes after
  each release.
- **Logs:** container logs in CloudWatch for stack traces behind any 5xx.

A limit worth stating: `/health` only proves the process is up. Once there is a database,
I would add a readiness check that also verifies the DB connection.

## 4. Rollback

**Manual:** point the service back at the previous task definition revision, which still
references the previous image in ECR. Nothing is rebuilt.

```bash
aws ecs update-service --cluster prod --service courses-api \
  --task-definition courses-api:<previous revision>
```

**How long:** the command takes seconds; ECS then needs to start old-version tasks, pass
health checks and drain the bad ones. Realistically about 2 to 5 minutes, mostly governed
by the health check interval and the deregistration delay. These are estimates from how
the settings work, not something I measured here.

**Automatic:**

- Turn on the **ECS deployment circuit breaker with rollback**. If new tasks fail to start
  or fail health checks, ECS reverts to the last working deployment by itself.
- That does not catch a version that starts fine but returns 500s on real requests. For
  that, attach **CloudWatch alarms to the deployment** (5xx rate, latency) so a firing
  alarm triggers rollback.
- For more safety, use **blue/green with CodeDeploy**: send 10% of traffic to the new
  version first, and shift back instantly if the alarms fire. Old tasks stay running
  until the release is confirmed, so rollback is a traffic switch, not a restart.

**Caveat:** rolling back code does not roll back data. Database migrations must be
backward compatible (add columns first, remove them in a later release) so the previous
version still works against the new schema.

## 5. The in-memory store

Problems once this runs on AWS:

- **Data loss.** Every deploy, crash, scale-in or Fargate host replacement wipes all
  courses and enrollments. A rollback would also erase everything.
- **Inconsistent data across tasks.** With two or more tasks behind the ALB, each has its
  own copy. A course created on one task is a 404 on the other, and IDs collide.
- **Business rules break.** The capacity and duplicate-email checks use an in-process
  lock, which only protects one process. Two tasks can both accept the "last" seat.
- **No scaling or high availability.** The only way to stay correct is a single task,
  which is a single point of failure.
- **No backups or audit trail**, and memory grows without bound.

What I would change:

- Move the data to **RDS PostgreSQL** (SQLAlchemy plus Alembic migrations), Multi-AZ with
  automated backups.
- Push the rules into the database so they hold across any number of tasks: a unique
  constraint on `(course_id, lower(email))` for duplicates, a foreign key so courses with
  enrollments cannot be deleted, and a transaction with `SELECT ... FOR UPDATE` on the
  course row for the capacity check.
- IDs come from database sequences, which also keeps "never reused" true.
- With state out of the process, the app is stateless and can run several tasks with
  auto scaling on CPU or request count.
