# One-Command VPS Deploy Script Design

## Purpose

Update `deploy-vps.ps1` so one local command can publish current safe changes to GitHub and deploy them on the VPS.

## Current Context

The repository already has `deploy-vps.ps1`. It SSHes to `root@178.105.83.211`, changes to `/opt/kliniassist`, pulls `origin main`, installs requirements, runs migrations, collects static files, and restarts the `kliniassist` service.

The local repository is expected to work on the `main` branch and push to `origin main`. The project instructions exclude secrets, local databases, debug screenshots, temporary outputs, `.superpowers/`, and ad-hoc debug artifacts from commits.

## Selected Approach

Replace the current VPS-only script behavior with a local-to-VPS deployment flow in the same `deploy-vps.ps1` file.

The script will:

1. Fail fast on command errors.
2. Confirm the local branch is `main`.
3. Stage safe repository changes while excluding common local-only and sensitive paths.
4. Create a generic commit when staged changes exist.
5. Push `main` to GitHub.
6. SSH into the VPS and run the existing pull, dependency, migration, static collection, and service restart steps.

The default commit message will be `chore: deploy latest changes`.

## Safety Rules

The script must not intentionally stage or commit:

1. `.env` or environment files containing secrets.
2. Local databases such as `db.sqlite3`.
3. `.superpowers/`.
4. Temporary visual/debug folders such as `tmp_visual_checks/`.
5. Debug images, screenshots, `test_output.txt`, and similar ad-hoc output files.
6. Git internals or dependency/vendor folders.

The script should display the local git status before committing so the operator can see what will be included. It should stage via `git add --all` followed by explicit unstaging of excluded paths, because this is simple and compatible with the existing PowerShell workflow.

## VPS Deployment Flow

The remote script will preserve the existing deployment behavior:

1. `cd /opt/kliniassist`.
2. Back up `.env` if it exists.
3. Pull `origin main`.
4. Restore `.env` after pull.
5. Activate the Python virtual environment.
6. `pip install -r requirements.txt`.
7. `python manage.py migrate`.
8. `python manage.py collectstatic --noinput`.
9. `systemctl restart kliniassist`.

The remote script will use shell error handling so a failed pull, dependency install, migration, static collection, or restart stops deployment instead of printing success.

## Non-Goals

This script will not add CI/CD, GitHub Actions, blue-green deployment, automatic rollback, database backups, secret rotation, or VPS provisioning. It is a pragmatic one-command deployment helper for the existing VPS.

## Verification

Before implementation is considered complete:

1. Run a PowerShell syntax parse for `deploy-vps.ps1`.
2. Run a non-destructive git status check to confirm excluded files are not staged by the script logic during review.
3. Do not execute the full deploy unless explicitly requested, because it would push and modify production/VPS state.
