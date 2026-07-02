# Deploying the web app to AWS (CLI + IaC, no console)

A complete, copy-pasteable guide to hosting the containerized jobsearch FastAPI
app on AWS **entirely from the command line** — `aws` CLI + **Terraform**
(primary) or **AWS CDK** (alternative). No AWS web console clicking. The one
place a click is unavoidable (root-account / IAM Identity Center bootstrap) is
flagged with its CLI-or-one-time alternative.

This is the AWS-specific deep dive. For the multi-host overview (Render, Cloud
Run, the "managed split") and the cross-cloud cost comparison, see
[`deploy.md`](deploy.md) and [`design-deployment.md`](design-deployment.md). For
the staged plan and the auth/multi-tenancy status, see
[`design-hosting-progress.md`](design-hosting-progress.md).

> ## What AWS hosts here — and what it does NOT
> AWS runs **only the stateless web container** (the [`Dockerfile`](../Dockerfile),
> which runs `python -m jobsearch ui --host 0.0.0.0 --port $PORT --allow-remote`).
> The **database stays on Supabase** (managed Postgres), reached over the
> `JOBSEARCH_DATABASE_URL` env var. **Do not provision RDS, Aurora, or any AWS
> database** — that is the single biggest cost line on AWS (~$14–32/mo) and we
> already have a free managed Postgres. Keeping AWS to "stateless container +
> HTTPS + secrets + logs" is what makes this cheap.

> ## ⚠️ Auth gate (read before going public)
> Hosted mode sits behind a Supabase Auth login wall with **owner-gated
> signups** (Stage 2a in [`design-hosting-progress.md`](design-hosting-progress.md)),
> so deploying for **yourself** is safe. Public multi-user signup waits on
> per-user data isolation (Stage 2b). Set the `SUPABASE_*` vars below and keep
> signups owner-only until then.

---

## 0. TL;DR — the recommended stack

**AWS App Runner**, pulling a private image from **ECR**, secrets in **SSM
Parameter Store**, logs in **CloudWatch**, all defined in **Terraform**.

- **HTTPS is included, free** — every App Runner service gets a
  `https://<id>.<region>.awsapprunner.com` URL with a managed TLS cert. No ALB,
  no ACM dance, no certificate plumbing for the default URL.
- **No VPC, no NAT Gateway, no ALB** — because the app reaches Supabase over the
  *public* internet, App Runner needs no VPC connector, so you dodge the
  **NAT Gateway (~$33/mo)** and **ALB (~$16/mo)** footguns entirely.
- **Simplest IaC** of the realistic options — one main resource plus two IAM
  roles.
- **Cost:** the smallest size (0.25 vCPU / 0.5 GB) is **~$5–6/mo** running 24/7,
  and you can `pause`/`resume` from the CLI to drop the idle cost toward ~$2.50.
  See [§9 Cost](#9-cost-estimate-verified-2026-pricing).

The honest tradeoff: App Runner's autoscaling **minimum is 1 instance, not 0**
— it does **not** scale to zero, so there is a small always-on floor (you pay
for *provisioned memory* even when idle). If a true $0-at-idle floor matters
more than simplicity, the alternative is **Lambda container image + Function
URL** (scales to zero, but needs an ASGI adapter and has real caveats for a
full web app — see [§2](#2-compute-choice--comparison)). For this app
(personal scale, login-walled, a moderately large image) App Runner is the
"cheapest that's still simple," so it's the primary stack below.

---

## 1. Prerequisites

### 1.1 Install the tools

```bash
# --- AWS CLI v2 (Linux x86_64) ---
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install   # macOS: brew install awscli
aws --version                                  # expect aws-cli/2.x

# --- Terraform (HashiCorp apt repo; or `brew install terraform`) ---
wget -O- https://apt.releases.hashicorp.com/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
terraform -version                             # expect >= 1.6

# --- Docker (needed to build/push the image) ---
docker --version

# --- (Optional) AWS CDK, only if you choose the CDK path in §5 ---
# npm i -g aws-cdk            # needs Node 18+
# cdk --version
```

### 1.2 Configure credentials

**Preferred: IAM Identity Center (SSO)** — short-lived creds, nothing long-term
on disk:

```bash
aws configure sso
# Follow the prompts: SSO start URL, region, then pick account + permission set.
# Name the profile, e.g. "jobsearch".
export AWS_PROFILE=jobsearch
aws sso login --profile jobsearch          # re-run when the session expires
aws sts get-caller-identity                 # verify you're authenticated
```

**Or static keys** (simpler, less secure — fine for a personal sandbox):

```bash
aws configure                               # paste Access Key ID + Secret, region, json
aws sts get-caller-identity
```

> **One-time bootstrap (the only unavoidable click):** creating your very first
> AWS account and the first admin user / IAM Identity Center instance requires
> the root login in a browser — AWS gives no API for account creation from
> nothing. After that *one* step, everything below is CLI/IaC. If you already
> have an account, create further programmatic users headless with
> `aws iam create-user` + `aws iam create-access-key`, or add SSO permission
> sets with `aws sso-admin create-permission-set`. Treat the root account as
> break-glass only.

Pin your region and account once so later commands can reuse them:

```bash
export AWS_REGION=us-east-1                                  # cheapest App Runner tier
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "$AWS_ACCOUNT_ID  $AWS_REGION"
```

### 1.3 IAM permissions you need

The identity you run Terraform/CLI as needs to manage these services. For a
personal project, attaching AWS-managed policies is the quick path; for least
privilege, scope a custom policy to these actions:

| Service | Why | Quick managed policy |
|---|---|---|
| ECR | create repo, push image | `AmazonEC2ContainerRegistryFullAccess` |
| App Runner | create/update/pause the service | `AWSAppRunnerFullAccess` |
| IAM | create the two service roles + pass them | `IAMFullAccess` (scope down later) |
| SSM Parameter Store | write/read the secret params | `AmazonSSMFullAccess` |
| CloudWatch Logs | read logs (`logs tail`) | `CloudWatchLogsReadOnlyAccess` |
| ACM + your DNS | custom domain (optional, §8) | `AWSCertificateManagerFullAccess` |

`iam:PassRole` is the easy-to-miss one: Terraform must pass the App Runner
*access role* and *instance role* to the service, so your principal needs
`iam:PassRole` on those role ARNs (covered by `IAMFullAccess`; in a scoped
policy, allow `iam:PassRole` with a `Condition` on
`iam:PassedToService = "tasks.apprunner.amazonaws.com"` and
`"build.apprunner.amazonaws.com"`).

> AWS-managed *role* policies referenced by Terraform below:
> `service-role/AWSAppRunnerServicePolicyForECRAccess` (lets App Runner pull
> from a private ECR repo).

---

## 2. Compute choice — comparison

All options assume: external Supabase Postgres (no AWS DB), one low-traffic
stateless container, personal scale. Costs are **us-east-1, 24/7, on top of the
external DB**, verified against 2026 pricing (see [§9](#9-cost-estimate-verified-2026-pricing)).

| Option | Scale to zero? | Cold start | HTTPS included | IaC simplicity | Rough $/mo (idle→light) | Verdict |
|---|---|---|---|---|---|---|
| **App Runner** (ECR image) | **No** (min 1 instance; `pause` for $0) | None while running; ~secs on resume after pause | **Yes** (managed cert on `*.awsapprunner.com`) | **Simplest** — 1 service + 2 roles, no VPC | **~$5–6** (0.25 vCPU/0.5 GB); ~$2.5 if you pause idle | ✅ **Recommended** |
| **ECS Fargate, NO ALB** (Fargate + public IP) | No (task runs 24/7) | None | **No** by itself — you'd need your own TLS termination; awkward without a LB | Medium — cluster, task def, service, SG, role | **~$9** (0.25/0.5) **+ no clean HTTPS** | ✗ HTTPS gap |
| **ECS Fargate, WITH ALB** | No | None | Yes (ALB + ACM) | Most resources — LB, target group, listener, SG, VPC | **~$9 compute + ~$16 ALB ≈ $25+** | ✗ ALB tax |
| **Lambda container + Function URL** (Mangum / Web Adapter) | **Yes** ($0 at idle) | ~0.2–1s warm path; **container cold starts slower**, big image hurts | **Yes** (Function URL is HTTPS) | Medium — function, URL, role; image must be Lambda-runtime-shaped | **~$0** at idle; pennies at this traffic | ◐ cheapest, most caveats |

### Why App Runner wins here

- **HTTPS for free, zero plumbing.** The biggest hidden cost on AWS for a small
  web app is *getting TLS without an ALB*. App Runner just gives you a managed
  HTTPS URL. Fargate-without-ALB can't terminate TLS cleanly; Fargate-with-ALB
  adds **~$16/mo** for the ALB alone (plus LCU hours) — for a personal app
  that's the dominant line item.
- **No VPC ⇒ no NAT Gateway.** Because Supabase is reached over the public
  internet, the container needs no VPC connector, so there's **no NAT Gateway
  (~$33/mo)** — the classic AWS bill-killer. (You'd only need a VPC connector,
  and possibly NAT, if you forced egress through a private subnet. Don't.)
- **Fewest moving parts in Terraform.**

### The expensive footguns (and how this guide avoids them)

| Footgun | Cost | How we avoid it |
|---|---|---|
| **Application Load Balancer** | **~$16.20/mo** (≈$0.0225/hr) + $0.008/LCU-hr | App Runner includes HTTPS; **no ALB at all**. |
| **NAT Gateway** | **~$32/mo** (≈$0.045/hr) + $0.045/GB + $3.6/mo per public IPv4 | **No VPC connector** → no private subnet → no NAT. App egresses to Supabase over App Runner's managed networking. |
| **Idle Fargate task** | ~$9/mo running 24/7 at the smallest size, **no scale-to-zero** | App Runner's small size is cheaper and `pause`-able; or use Lambda for true $0 idle. |
| **Secrets Manager** vs SSM | $0.40/secret/mo + API calls | Use **SSM Parameter Store** (`Standard` tier = **free**) for these few secrets. |

### When to pick the Lambda alternative instead

Choose **Lambda container + Function URL** if a literal **$0-at-idle** floor
beats simplicity. Real caveats for *this* app:

- **It's a full ASGI server, not a handler.** You must wrap FastAPI with an
  adapter — either [Mangum](https://github.com/jordaneremieff/mangum) as the
  Lambda handler, or the [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter)
  (run the unmodified `python -m jobsearch ui` and let the adapter translate).
  The Web Adapter is the smaller change since the app already serves HTTP.
- **Cold starts + a big image.** The image bundles numpy / scikit-learn /
  playwright, so it's large; container cold starts are slower than zip, and a
  big image makes them worse. Mitigate by **slimming the image** (the web path
  needs no Chromium — see [`deploy.md`](deploy.md) §Leanness) or paying for
  Provisioned Concurrency (defeats the $0 idle point).
- **Function URL response limits.** Buffered responses cap at **6 MB**; only
  *streaming* responses go higher, and Lambda response **streaming is limited to
  Node.js managed runtimes / custom runtimes** — with a Python container you'd
  rely on the Web Adapter's buffered mode, so keep responses small (fine for
  this UI; watch large file downloads).
- **Function URLs don't carry custom domains directly** — you'd front it with
  CloudFront + ACM to use your own domain (more pieces than App Runner's
  built-in custom-domain support).

A minimal Lambda alternative is sketched in
[§5.3](#53-alternative-lambda-container--function-url). The rest of the guide
builds the **App Runner** stack.

---

## 3. Build & push the image to ECR

```bash
# 0) Make sure these are exported (from §1.2)
: "${AWS_REGION:?}"; : "${AWS_ACCOUNT_ID:?}"
REPO=jobsearch-web
REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# 1) Create the private ECR repo (idempotent: ignore "already exists")
aws ecr create-repository \
  --repository-name "$REPO" \
  --region "$AWS_REGION" \
  --image-scanning-configuration scanOnPush=true \
  --image-tag-mutability MUTABLE \
  || echo "repo may already exist, continuing"

# 2) Log Docker in to ECR (token is valid 12h; --password-stdin keeps it off argv)
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

# 3) Build for the platform App Runner runs (linux/amd64).
#    IMPORTANT on Apple Silicon / arm hosts: force the platform or App Runner
#    will fail to start an arm64 image (it runs x86_64).
docker build --platform linux/amd64 -t "$REPO:latest" .

# 4) Tag for ECR — push BOTH an immutable version tag and :latest.
#    Use the git SHA (or a date) so every deploy is uniquely addressable.
TAG=$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)
docker tag "$REPO:latest" "$REGISTRY/$REPO:$TAG"
docker tag "$REPO:latest" "$REGISTRY/$REPO:latest"

# 5) Push
docker push "$REGISTRY/$REPO:$TAG"
docker push "$REGISTRY/$REPO:latest"

echo "Pushed: $REGISTRY/$REPO:$TAG"
```

Sanity-check the image was accepted:

```bash
aws ecr describe-images --repository-name "$REPO" --region "$AWS_REGION" \
  --query 'sort_by(imageDetails,&imagePushedAt)[-1].{tags:imageTags,pushed:imagePushedAt}'
```

> Test the image locally first (catches env/port issues before any AWS spend):
> ```bash
> docker run --rm -p 8484:8484 \
>   -e JOBSEARCH_DATABASE_URL='postgresql://postgres.<ref>:PW@aws-0-us-east-1.pooler.supabase.com:5432/postgres' \
>   -e SUPABASE_URL='https://<ref>.supabase.co' \
>   -e SUPABASE_ANON_KEY='<anon-key>' \
>   -e JOBSEARCH_SESSION_SECRET='dev-only-secret' \
>   "$REPO:latest"     # open http://127.0.0.1:8484
> ```

---

## 4. Store the secrets (CLI) — SSM Parameter Store

Put every secret in SSM **before** `terraform apply`; Terraform references them
by ARN and never sees the plaintext. `Standard`-tier `SecureString` parameters
are **free**.

```bash
: "${AWS_REGION:?}"
APP=jobsearch     # name prefix for the parameter paths

put() {  # put <name> <value>
  aws ssm put-parameter \
    --region "$AWS_REGION" \
    --name "/$APP/$1" \
    --type SecureString \
    --value "$2" \
    --overwrite >/dev/null && echo "  set /$APP/$1"
}

put JOBSEARCH_DATABASE_URL 'postgresql://postgres.<ref>:YOUR-DB-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres'
put SUPABASE_URL           'https://<ref>.supabase.co'
put SUPABASE_ANON_KEY      'YOUR-SUPABASE-ANON-PUBLISHABLE-KEY'
# A long random cookie-signing secret (generate, don't reuse):
put JOBSEARCH_SESSION_SECRET "$(openssl rand -hex 32)"
```

Notes:
- Use the Supabase **Session pooler** URI for `JOBSEARCH_DATABASE_URL` (see
  [`deploy.md`](deploy.md)) — it handles many short-lived connections.
- `JOBSEARCH_HTTPS_ONLY=1` and `PORT` are **not** secrets:
  `JOBSEARCH_HTTPS_ONLY` is passed as a plain runtime env var by Terraform, and
  `PORT` is injected by App Runner — do not set `PORT` yourself.
- Don't paste secrets straight on the shell on a shared box (they land in
  history). Prefer `--value "$(cat secret.txt)"` or read into a var first; or
  use `--cli-input-json file://...`.

Grab the ARNs Terraform will reference (it also re-resolves them via a data
source, so this is just to confirm):

```bash
for n in JOBSEARCH_DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY JOBSEARCH_SESSION_SECRET; do
  aws ssm get-parameter --region "$AWS_REGION" --name "/$APP/$n" \
    --query 'Parameter.ARN' --output text
done
```

> **Rotation gotcha:** App Runner reads secrets **only at deployment time**. If
> you change a parameter value later, you must trigger a new deployment (push a
> new image, or `aws apprunner start-deployment`, see [§6](#6-deploy--redeploy)).

---

## 5. Terraform — the recommended App Runner stack

Create a `deploy/aws/` directory (kept out of the app tree) with these files.

### 5.1 File layout

```
deploy/aws/
├── versions.tf
├── variables.tf
├── main.tf
├── outputs.tf
├── terraform.tfvars.example     # commit this
└── terraform.tfvars             # DO NOT COMMIT (gitignored)
```

> **Gitignore the real tfvars and state.** Add to your root `.gitignore`:
> ```
> # Terraform (AWS deploy)
> deploy/aws/terraform.tfvars
> deploy/aws/.terraform/
> deploy/aws/*.tfstate
> deploy/aws/*.tfstate.*
> deploy/aws/.terraform.lock.hcl   # optional; many teams DO commit the lock file
> ```
> The repo's existing `.gitignore` already blocks `.env*`, `*.pem`, `*.key`. The
> tfvars here hold no secrets (those live in SSM) — but state can capture
> resolved values, so keep `*.tfstate` out of git regardless.

### 5.2 The files

**`versions.tf`**

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.aws_region
  # Credentials come from your environment / AWS_PROFILE (SSO or static).
  default_tags {
    tags = {
      Project   = "jobsearch"
      ManagedBy = "terraform"
    }
  }
}
```

**`variables.tf`**

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "service_name" {
  type    = string
  default = "jobsearch-web"
}

variable "ecr_repo_name" {
  type    = string
  default = "jobsearch-web"
}

variable "image_tag" {
  description = "Image tag to deploy (e.g. the git short SHA pushed in §3)."
  type        = string
}

variable "ssm_prefix" {
  description = "SSM Parameter Store path prefix used in §4."
  type        = string
  default     = "/jobsearch"
}

# Smallest App Runner size. Valid cpu: 0.25/0.5/1/2/4 vCPU (or 256/512/1024/...).
# Valid memory: 0.5/1/2/.../12 GB (or 512/1024/...). 0.25 vCPU pairs with 0.5 or 1 GB.
variable "cpu" {
  type    = string
  default = "0.25 vCPU"
}

variable "memory" {
  type    = string
  default = "0.5 GB"
}
```

**`main.tf`**

```hcl
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  image_uri  = "${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${var.ecr_repo_name}:${var.image_tag}"

  # Names of the SSM params created in §4 (without the prefix).
  secret_names = [
    "JOBSEARCH_DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "JOBSEARCH_SESSION_SECRET",
  ]
}

# Look up the ECR repo (created via CLI in §3). To have Terraform OWN the repo
# instead, replace this data source with a `resource "aws_ecr_repository"`.
data "aws_ecr_repository" "app" {
  name = var.ecr_repo_name
}

# Resolve each secret's ARN from its name (so we never hard-code ARNs).
data "aws_ssm_parameter" "secret" {
  for_each        = toset(local.secret_names)
  name            = "${var.ssm_prefix}/${each.value}"
  with_decryption = false # we only need the ARN, not the value
}

# ---------------------------------------------------------------------------
# IAM: (1) ACCESS role — lets App Runner pull the private image from ECR.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "access_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "access" {
  name               = "${var.service_name}-access"
  assume_role_policy = data.aws_iam_policy_document.access_assume.json
}

resource "aws_iam_role_policy_attachment" "access_ecr" {
  role       = aws_iam_role.access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# ---------------------------------------------------------------------------
# IAM: (2) INSTANCE role — assumed by the running container; lets it read the
# SSM SecureString params (and decrypt them with the default SSM KMS key).
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "instance_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["tasks.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.service_name}-instance"
  assume_role_policy = data.aws_iam_policy_document.instance_assume.json
}

data "aws_iam_policy_document" "instance_secrets" {
  statement {
    sid       = "ReadSsmParams"
    actions   = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = [for p in data.aws_ssm_parameter.secret : p.arn]
  }
  statement {
    sid       = "DecryptSsmParams"
    actions   = ["kms:Decrypt"]
    resources = ["*"] # default aws/ssm key; scope to your CMK ARN if you use one
  }
}

resource "aws_iam_role_policy" "instance_secrets" {
  name   = "${var.service_name}-read-secrets"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_secrets.json
}

# ---------------------------------------------------------------------------
# Autoscaling: keep min_size = 1 (App Runner cannot scale to 0). max_size and
# max_concurrency are generous; personal traffic will never leave 1 instance.
# ---------------------------------------------------------------------------
resource "aws_apprunner_auto_scaling_configuration_version" "this" {
  auto_scaling_configuration_name = var.service_name
  min_size                        = 1
  max_size                        = 2
  max_concurrency                 = 100

  tags = { Project = "jobsearch" }
}

# ---------------------------------------------------------------------------
# The App Runner service.
# ---------------------------------------------------------------------------
resource "aws_apprunner_service" "this" {
  service_name = var.service_name

  source_configuration {
    # Required for a PRIVATE ECR image.
    authentication_configuration {
      access_role_arn = aws_iam_role.access.arn
    }

    # Redeploy automatically when a new image is pushed to this tag.
    auto_deployments_enabled = true

    image_repository {
      image_identifier      = local.image_uri
      image_repository_type = "ECR"

      image_configuration {
        # App Runner injects PORT; the container reads it. Tell App Runner which
        # port the app listens on. The Dockerfile defaults to 8484.
        port = "8484"

        # Plain, non-secret runtime config.
        runtime_environment_variables = {
          JOBSEARCH_HTTPS_ONLY = "1"
        }

        # Secrets by ARN — App Runner injects the resolved VALUES as env vars
        # of the SAME name. The container sees JOBSEARCH_DATABASE_URL, etc.
        runtime_environment_secrets = {
          for name, p in data.aws_ssm_parameter.secret : name => p.arn
        }
      }
    }
  }

  instance_configuration {
    cpu               = var.cpu
    memory            = var.memory
    instance_role_arn = aws_iam_role.instance.arn
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.this.arn

  # App Runner health-checks the app. TCP is the zero-config choice; switch to
  # HTTP against the app's /healthz route for a real readiness signal.
  health_check_configuration {
    protocol            = "HTTP"
    path                = "/healthz"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  tags = { Project = "jobsearch" }
}
```

**`outputs.tf`**

```hcl
output "service_url" {
  description = "Public HTTPS URL (managed TLS)."
  value       = "https://${aws_apprunner_service.this.service_url}"
}

output "service_arn" {
  value = aws_apprunner_service.this.arn
}

output "image_uri" {
  value = local.image_uri
}
```

**`terraform.tfvars.example`** (commit this; copy to `terraform.tfvars` and
fill in):

```hcl
aws_region    = "us-east-1"
service_name  = "jobsearch-web"
ecr_repo_name = "jobsearch-web"

# The tag you pushed in §3 (git short SHA or date). REQUIRED — no default.
image_tag = "REPLACE_WITH_PUSHED_TAG"

ssm_prefix = "/jobsearch"

# Smallest/cheapest size; bump if the app OOMs on cold import of numpy/sklearn.
cpu    = "0.25 vCPU"
memory = "0.5 GB"
```

> **Memory note:** the image imports numpy/scikit-learn; if the service crashes
> on startup with an OOM, raise `memory` to `"1 GB"` (still valid with
> `0.25 vCPU`) before reaching for more vCPU.

> **Remote state (recommended once it works):** for a durable backend, create an
> S3 bucket + DynamoDB lock table via CLI and add a `backend "s3"` block. For a
> solo personal project, local state (the default) is fine — just keep
> `*.tfstate` gitignored (it can contain resolved values).

### 5.3 Alternative: Lambda container + Function URL

For the **$0-at-idle** path. This is a sketch; read the caveats in
[§2](#when-to-pick-the-lambda-alternative-instead) first (ASGI adapter, cold
starts, response-size limits, custom domain needs CloudFront).

The cleanest way to run *this* app on Lambda with the **least code change** is
the **AWS Lambda Web Adapter**: add one line to the Dockerfile so the adapter
sits in front of the existing `python -m jobsearch ui` server (it reads the
adapter's `AWS_LWA_PORT`, which you point at the app's port). Then:

```hcl
# Lambda needs a different assume-role principal than App Runner.
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "jobsearch-web-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "app" {
  function_name = "jobsearch-web"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.image_uri   # the ECR image (Lambda-shaped, see note)
  timeout       = 30
  memory_size   = 2048              # also scales CPU; big image needs headroom

  environment {
    variables = {
      JOBSEARCH_HTTPS_ONLY = "1"
      AWS_LWA_PORT         = "8484"
      # Secrets: either read from SSM at runtime in code, or inline ARNs via
      # the lambda extension. Lambda has no native "secrets as env" like App
      # Runner, so grant ssm:GetParameter to this role and fetch on cold start.
    }
  }
}

resource "aws_lambda_function_url" "app" {
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"   # public; the app's own login wall guards it
}

output "lambda_url" {
  value = aws_lambda_function_url.app.function_url
}
```

> Lambda image note: a Lambda container image must conform to the Lambda runtime
> interface. With the **Web Adapter** the base image stays normal and the
> adapter handles the contract; with **Mangum** you set the image `CMD` to the
> Mangum handler (e.g. `app.main.handler`). Either way, for secrets you grant
> the Lambda role `ssm:GetParameter` and read them on cold start (Lambda has no
> App-Runner-style "inject secret as env var").

A pure-CLI equivalent (no Terraform) for the same thing:

```bash
aws lambda create-function --function-name jobsearch-web \
  --package-type Image \
  --code ImageUri="$REGISTRY/$REPO:$TAG" \
  --role "arn:aws:iam::$AWS_ACCOUNT_ID:role/jobsearch-web-lambda" \
  --timeout 30 --memory-size 2048 --region "$AWS_REGION"

aws lambda create-function-url-config --function-name jobsearch-web \
  --auth-type NONE --region "$AWS_REGION"

# REQUIRED when auth-type=NONE via CLI: add the public-invoke permission yourself.
aws lambda add-permission --function-name jobsearch-web \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl --principal "*" \
  --function-url-auth-type NONE --region "$AWS_REGION"
```

---

## 6. Deploy + redeploy

### First deploy

```bash
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set image_tag to the tag you pushed in §3

terraform init
terraform plan      # review: 1 service, 1 autoscaling cfg, 2 roles, policies
terraform apply     # type "yes"

terraform output service_url    # -> https://xxxx.us-east-1.awsapprunner.com
```

First create takes a few minutes (App Runner provisions + health-checks). Then
open the URL — you should hit the Supabase login wall.

### Redeploy a new image version

Two paths:

**A. Auto-deploy (we set `auto_deployments_enabled = true`).** Just push a new
image to the **`:latest`** tag and App Runner rolls it out automatically:

```bash
docker build --platform linux/amd64 -t "$REPO:latest" .
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker push "$REGISTRY/$REPO:latest"
# App Runner detects the push and deploys. Watch it:
aws apprunner list-operations --service-arn "$(terraform output -raw service_arn)" \
  --region "$AWS_REGION" --max-results 1
```

**B. Pinned-tag deploy (more auditable).** Push a new SHA tag, bump
`image_tag`, and apply — Terraform updates the service to the new immutable tag:

```bash
TAG=$(git rev-parse --short HEAD)
docker build --platform linux/amd64 -t "$REGISTRY/$REPO:$TAG" .
docker push "$REGISTRY/$REPO:$TAG"
terraform apply -var "image_tag=$TAG"
```

**Force a redeploy without an image change** (e.g. after rotating an SSM secret
— remember App Runner only reads secrets at deploy time):

```bash
aws apprunner start-deployment \
  --service-arn "$(terraform output -raw service_arn)" --region "$AWS_REGION"
```

### View logs

App Runner writes two CloudWatch log groups: `service` (lifecycle/deploy) and
`application` (your container's stdout/stderr — uvicorn lines live here).

```bash
SVC=jobsearch-web

# Tail application logs live:
aws logs tail "/aws/apprunner/$SVC"/*/application --follow --region "$AWS_REGION"

# Deploy/lifecycle logs:
aws logs tail "/aws/apprunner/$SVC"/*/service --follow --region "$AWS_REGION"

# If the wildcard path is awkward, list the exact group names first:
aws logs describe-log-groups --region "$AWS_REGION" \
  --log-group-name-prefix "/aws/apprunner/$SVC" \
  --query 'logGroups[].logGroupName' --output table
```

`aws logs tail` also takes `--since 1h`, `--filter-pattern ERROR`, and
`--format short`.

### Pause / resume to cut idle cost

```bash
ARN="$(terraform output -raw service_arn)"
aws apprunner pause-service  --service-arn "$ARN" --region "$AWS_REGION"   # ~stop billing
aws apprunner resume-service --service-arn "$ARN" --region "$AWS_REGION"   # bring back (takes a bit)
```

---

## 7. (Optional) AWS CDK equivalent

For users who prefer CDK over Terraform. App Runner lives in the
`aws-cdk-lib/aws-apprunner` L2/alpha constructs; the pattern below uses the
stable `CfnService` (L1) so it works regardless of alpha-module churn. Same
stack: private ECR image, SSM secrets, two roles.

```typescript
// lib/jobsearch-apprunner-stack.ts
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as apprunner from "aws-cdk-lib/aws-apprunner";

export class JobsearchAppRunnerStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const imageTag = this.node.tryGetContext("imageTag") ?? "latest";
    const repo = ecr.Repository.fromRepositoryName(this, "Repo", "jobsearch-web");

    // SSM params created via CLI in §4.
    const names = [
      "JOBSEARCH_DATABASE_URL",
      "SUPABASE_URL",
      "SUPABASE_ANON_KEY",
      "JOBSEARCH_SESSION_SECRET",
    ];
    const params = names.map((n) =>
      ssm.StringParameter.fromSecureStringParameterAttributes(this, n, {
        parameterName: `/jobsearch/${n}`,
      })
    );

    // Access role: pull from private ECR.
    const accessRole = new iam.Role(this, "AccessRole", {
      assumedBy: new iam.ServicePrincipal("build.apprunner.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSAppRunnerServicePolicyForECRAccess"
        ),
      ],
    });

    // Instance role: read the SSM secrets.
    const instanceRole = new iam.Role(this, "InstanceRole", {
      assumedBy: new iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),
    });
    params.forEach((p) => p.grantRead(instanceRole));

    const service = new apprunner.CfnService(this, "Service", {
      serviceName: "jobsearch-web",
      sourceConfiguration: {
        autoDeploymentsEnabled: true,
        authenticationConfiguration: { accessRoleArn: accessRole.roleArn },
        imageRepository: {
          imageIdentifier: `${repo.repositoryUri}:${imageTag}`,
          imageRepositoryType: "ECR",
          imageConfiguration: {
            port: "8484",
            runtimeEnvironmentVariables: [
              { name: "JOBSEARCH_HTTPS_ONLY", value: "1" },
            ],
            runtimeEnvironmentSecrets: names.map((n, i) => ({
              name: n,
              value: params[i].parameterArn,
            })),
          },
        },
      },
      instanceConfiguration: {
        cpu: "0.25 vCPU",
        memory: "0.5 GB",
        instanceRoleArn: instanceRole.roleArn,
      },
      healthCheckConfiguration: { protocol: "HTTP", path: "/healthz" },
    });

    new cdk.CfnOutput(this, "ServiceUrl", {
      value: `https://${service.attrServiceUrl}`,
    });
  }
}
```

Deploy:

```bash
cdk bootstrap                                   # one-time per account/region
cdk deploy --context imageTag="$(git rev-parse --short HEAD)"
```

(Python CDK mirrors this exactly using `aws_cdk.aws_apprunner.CfnService` with
snake_case props.)

---

## 8. Custom domain + HTTPS

The default `*.awsapprunner.com` URL is already HTTPS. To use your own domain
(e.g. `jobs.example.com`), App Runner **manages its own ACM certificate** — you
do **not** run `acm request-certificate` for the App Runner path; you call
`associate-custom-domain`, then add the DNS records it returns.

```bash
ARN="$(cd deploy/aws && terraform output -raw service_arn)"
DOMAIN=jobs.example.com

# 1) Associate the domain. App Runner creates a managed cert and returns the
#    DNS records you must publish.
aws apprunner associate-custom-domain \
  --service-arn "$ARN" --domain-name "$DOMAIN" --region "$AWS_REGION"

# 2) Read back the records to create (re-run until they appear):
aws apprunner describe-custom-domains \
  --service-arn "$ARN" --region "$AWS_REGION" \
  --query 'CustomDomains[].{domain:DomainName,status:Status,records:CertificateValidationRecords}'
```

You'll get **two kinds** of records to add **at your DNS provider**:

1. **Certificate validation** — one or more CNAME records (name +
   value) proving you control the domain. (If you keep CAA records, ensure at
   least one references `amazon.com`, or ACM validation fails.)
2. **The traffic record** — a CNAME from `jobs.example.com` to the App Runner
   target subdomain. (For an apex/root domain that can't CNAME, use your DNS
   provider's ALIAS/ANAME, or Route 53 alias.)

If your DNS is **Route 53**, do it from the CLI with
`aws route53 change-resource-record-sets` (batch the records into a JSON file).
For any other DNS provider, adding the records is the one step done in their
control panel — there's no AWS CLI for third-party DNS.

Then wait for validation to flip to `active`:

```bash
# Poll status until "active":
aws apprunner describe-custom-domains --service-arn "$ARN" --region "$AWS_REGION" \
  --query 'CustomDomains[].Status'
```

> **ALB-stack note (only if you chose Fargate+ALB):** *there* you'd use ACM
> directly: `aws acm request-certificate --domain-name jobs.example.com
> --validation-method DNS`, read the CNAME with `aws acm describe-certificate
> ... --query 'Certificate.DomainValidationOptions[].ResourceRecord'`, add it to
> DNS, `aws acm wait certificate-validated --certificate-arn <arn>`, then attach
> the cert ARN to the HTTPS listener. App Runner avoids all of this.

---

## 9. Cost estimate (verified 2026 pricing)

us-east-1, on top of the **free** external Supabase Postgres. Pricing verified
2026-06; **re-check before relying on it** — AWS prices move.

**App Runner** (recommended). Active = processing requests (vCPU + memory);
provisioned = idle (memory only). Rates (US East): **$0.064/vCPU-hr active**,
**$0.007/GB-hr** for memory. Smallest size = 0.25 vCPU / 0.5 GB, `min_size=1`
(no scale to zero), ~730 hrs/mo.

| Scenario | Compute math | **~$/mo** |
|---|---|---|
| **Always-on, mostly idle** (1 inst, memory billed 24/7 + a little active vCPU) | 0.5 GB × 730 × $0.007 = **$2.56** memory; + light active vCPU (say 20 hrs × 0.25 × $0.064 ≈ $0.32) | **~$3** |
| **Always-on, treated as active 24/7** (worst case for a tiny app) | $2.56 mem + 0.25 vCPU × 730 × $0.064 = $11.68 | **~$5–6 typical** (real apps aren't "active" 24/7) |
| **Paused when not in use** | provisioned billing stops while paused | **~$0–2.5** |
| Plus: auto-deployments | — | **$1/app/mo** (only if auto-deploy on) |
| Plus: ECR storage | image GBs × $0.10/GB/mo | **~$0.1–0.5** |
| Plus: CloudWatch Logs | first 5 GB ingest free; low-traffic app stays under | **~$0** |

**Realistic monthly bill: ~$5–6** with auto-deploy on, or **~$3** if you turn
auto-deploy off and traffic is genuinely low, or **~$2.5** if you `pause` when
idle. **No ALB, no NAT, no RDS.**

For comparison, the avoided footguns: **ALB ~$16.20/mo**, **NAT Gateway
~$32/mo** (+ $0.045/GB + $3.60/mo per public IPv4), **Fargate 24/7 0.25/0.5
~$9/mo** with no scale-to-zero, **Secrets Manager $0.40/secret/mo** (we used
free SSM Standard instead). The **Lambda** alternative is **~$0 at idle** and
pennies at this traffic (free tier: 1M requests + 400K GB-s/mo), trading cost
for the ASGI-adapter + cold-start + response-limit caveats in
[§2](#2-compute-choice--comparison).

This is consistent with [`design-deployment.md`](design-deployment.md), which
pegs the AWS all-in path at "~$0 year one, ~$15/mo after" — note that figure
**includes AWS RDS Postgres**; by keeping the database on **Supabase**, this
guide removes that line and lands at **~$3–6/mo** for compute alone.

---

## 10. Teardown

```bash
cd deploy/aws

# (If you set a custom domain, dissociate it first.)
ARN="$(terraform output -raw service_arn)"
aws apprunner disassociate-custom-domain \
  --service-arn "$ARN" --domain-name jobs.example.com --region "$AWS_REGION" 2>/dev/null || true

# Destroy the App Runner service + roles + autoscaling config.
terraform destroy        # type "yes"
```

Terraform leaves resources it didn't create. Clean those up by CLI:

```bash
# SSM secrets:
for n in JOBSEARCH_DATABASE_URL SUPABASE_URL SUPABASE_ANON_KEY JOBSEARCH_SESSION_SECRET; do
  aws ssm delete-parameter --name "/jobsearch/$n" --region "$AWS_REGION" 2>/dev/null || true
done

# ECR repo (and all images in it):
aws ecr delete-repository --repository-name jobsearch-web --force --region "$AWS_REGION"

# CloudWatch log groups (optional; they cost ~nothing but tidy up):
for g in $(aws logs describe-log-groups --region "$AWS_REGION" \
            --log-group-name-prefix /aws/apprunner/jobsearch-web \
            --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --log-group-name "$g" --region "$AWS_REGION"
done
```

Verify nothing is still billing:

```bash
aws apprunner list-services --region "$AWS_REGION" --query 'ServiceSummaryList[].ServiceName'
aws ecr describe-repositories --region "$AWS_REGION" --query 'repositories[].repositoryName'
```

---

## Appendix — quick command reference

```bash
# Env
export AWS_PROFILE=jobsearch AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"; REPO=jobsearch-web

# Build & push
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$REGISTRY/$REPO:latest" . && docker push "$REGISTRY/$REPO:latest"

# Deploy
cd deploy/aws && terraform init && terraform apply -var "image_tag=latest"
terraform output service_url

# Logs / redeploy / pause
aws logs tail "/aws/apprunner/$REPO"/*/application --follow --region "$AWS_REGION"
aws apprunner start-deployment --service-arn "$(terraform output -raw service_arn)" --region "$AWS_REGION"
aws apprunner pause-service   --service-arn "$(terraform output -raw service_arn)" --region "$AWS_REGION"

# Teardown
terraform destroy
```

---

### Sources (pricing/syntax verified 2026-06)

- [AWS App Runner pricing](https://aws.amazon.com/apprunner/pricing/) ·
  [App Runner autoscaling (min/max instances)](https://docs.aws.amazon.com/apprunner/latest/dg/manage-autoscaling.html)
- [aws_apprunner_service (Terraform Registry)](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apprunner_service) ·
  [App Runner + SSM/Secrets Manager](https://aws.amazon.com/blogs/containers/aws-app-runner-now-integrates-with-aws-secrets-manager-and-aws-systems-manager-parameter-store/)
- [ECR: push an image](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html) ·
  [ecr get-login-password](https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/) ·
  [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/) ·
  [NAT gateway pricing](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html)
- [Lambda function URLs](https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html) ·
  [Lambda response streaming](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html) ·
  [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) ·
  [Mangum](https://github.com/jordaneremieff/mangum)
- [App Runner associate-custom-domain](https://docs.aws.amazon.com/cli/latest/reference/apprunner/associate-custom-domain.html) ·
  [ACM DNS validation](https://docs.aws.amazon.com/acm/latest/userguide/dns-validation.html)
