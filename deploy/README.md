# Deploy the jobsearch UI to AWS (minimal MVP)

This puts the web UI on a public, password-protected HTTPS link using **AWS App
Runner** — a single managed service, no servers/load-balancers to run. It builds
a Docker image, pushes it to ECR, and runs it.

> **Heads up:** the UI is unauthenticated by design and shows your resume,
> profile PII, Gmail, and browser controls. The deploy puts an HTTP Basic-auth
> password in front of it (`JOBSEARCH_BASIC_AUTH_PASSWORD`). Only share the link
> *and* password with people you want to see your real data.

## 1. Create the IAM user (one time)

You give the deploy an IAM user's keys — **not** your root account.

1. AWS Console → **IAM** → **Users** → **Create user**. Name it e.g.
   `jobsearch-deployer`. Do **not** give it console access.
2. **Next** → **Attach policies directly** → **Create policy** → **JSON** tab →
   paste the contents of [`iam-policy.json`](./iam-policy.json) → name it
   `jobsearch-deploy` → create it. Back on the user screen, refresh, search for
   `jobsearch-deploy`, tick it, **Next** → **Create user**.
3. Open the new user → **Security credentials** → **Create access key** →
   choose **Application running outside AWS** (CLI) → create. Copy the
   **Access key ID** and **Secret access key**.

## 2. Hand the keys to the deploy

**Recommended (keys never appear in chat):** in the Claude Code web app, open
this environment's settings and add three **environment variables / secrets**:

```
AWS_ACCESS_KEY_ID        = <access key id>
AWS_SECRET_ACCESS_KEY    = <secret access key>
AWS_DEFAULT_REGION       = us-east-1     # or your preferred region
```

They're injected into the container without being logged in the conversation.
(See https://code.claude.com/docs/en/claude-code-on-the-web.)

If you'd rather run it on your own machine, export those same three variables in
your shell.

## 3. Deploy

The script self-bootstraps: it installs the AWS CLI and starts Docker if they're
missing, so it runs as-is both on a laptop and in a fresh Claude Code web
session. Just make sure the session is on this branch and the AWS env vars
(step 2) are set, then:

```bash
JOBSEARCH_BASIC_AUTH_PASSWORD='pick-a-strong-password' ./deploy/aws-apprunner.sh
```

> Running from a **new Claude Code web session**? Start it on this PR's branch
> (`claude/aws-mvp-deploy-p2p1ir`) so these files are present, confirm your AWS
> env secrets are configured, then just say "run the deploy."

Omit the password and the script generates and prints one. When it finishes it
prints a `https://<id>.<region>.awsapprunner.com/` link. Log in with user
`demo` and your password, then open `/resume` to upload your resume — the next
pipeline run scores postings against it.

## Notes & limits (it's an MVP)

- **Storage is ephemeral.** App Runner has no persistent disk, so the uploaded
  resume and the SQLite tracker DB are lost if the service restarts or
  redeploys. Re-upload after a redeploy. (Persisting would mean adding S3/EFS —
  out of scope for a demo.)
- **No live browser scraping.** The Chromium binary isn't in the image, so
  browser-only boards and the auto-fill feature are skipped; the dashboard and
  all API-based boards work normally.
- **Cost:** roughly $5–25/month while running; App Runner bills mostly for the
  running instance.

## Tear it down

```bash
aws apprunner list-services --query "ServiceSummaryList[?ServiceName=='jobsearch-mvp'].ServiceArn" --output text
aws apprunner delete-service --service-arn <arn-from-above>
aws ecr delete-repository --repository-name jobsearch-mvp --force
```
