# One-Command VPS Deploy Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `deploy-vps.ps1` so one command can commit safe local changes, push `main` to GitHub, and deploy the pushed code on the VPS.

**Architecture:** Keep deployment logic in the existing PowerShell script. Add local git safety checks and a `-DryRun` mode, then run the existing VPS deployment sequence through SSH with fail-fast shell error handling.

**Tech Stack:** PowerShell 5.1, Git, OpenSSH, Bash on VPS, Django management commands, systemd.

---

## File Structure

- Modify: `deploy-vps.ps1` - one-command deployment script with local commit/push flow, path exclusions, dry-run reporting, and remote VPS deployment commands.
- Verify: PowerShell parser and `deploy-vps.ps1 -DryRun` - non-destructive checks for the ignored local deployment helper.
- Reference: `docs/superpowers/specs/2026-06-06-one-command-vps-deploy-script-design.md` - approved design source.

Do not commit these changes unless the user explicitly asks for a commit. The script itself will be capable of creating future deployment commits when the operator runs it. Because `.gitignore` intentionally ignores `deploy-vps.ps1`, do not add tracked tests that depend on this local-only script unless the user explicitly asks to track the deployment helper in Git.

### Task 1: Confirm Local-Only Deploy Script State

**Files:**
- Read: `.gitignore`
- Verify: `deploy-vps.ps1`

- [ ] **Step 1: Confirm whether the deploy script is ignored**

Run:

```powershell
git check-ignore -v deploy-vps.ps1
```

Expected: output shows `.gitignore` ignores `deploy-vps.ps1`. This means implementation verification should use parser and dry-run checks instead of adding a tracked pytest file that would fail in Git without the ignored script.

- [ ] **Step 2: Confirm the existing script lacks the requested behavior before implementation**

Run:

```powershell
Select-String -LiteralPath .\deploy-vps.ps1 -Pattern 'Invoke-Expression|git push|DryRun|git pull --ff-only'
```

Expected: output includes `Invoke-Expression` and does not include `git push`, `DryRun`, or `git pull --ff-only` before implementation.

### Task 2: Replace `deploy-vps.ps1` With One-Command Deploy Flow

**Files:**
- Modify: `deploy-vps.ps1`
- Verify: `deploy-vps.ps1`

- [ ] **Step 1: Replace the existing script**

Replace all content in `deploy-vps.ps1` with this exact PowerShell script:

```powershell
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$sshKey = Join-Path $env:USERPROFILE '.ssh\hetzner_key'
$sshTarget = 'root@178.105.83.211'
$remoteAppDir = '/opt/kliniassist'
$serviceName = 'kliniassist'
$commitMessage = 'chore: deploy latest changes'

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }

    return @($output)
}

function Test-ExcludedFromDeployCommit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path -replace '\\', '/'

    if ($normalized -match '(^|/)\.env$') { return $true }
    if (($normalized -match '(^|/)\.env\.') -and ($normalized -notmatch '(^|/)\.env\.example$')) { return $true }
    if ($normalized -match '(^|/)db\.sqlite3$') { return $true }
    if ($normalized -match '(^|/)(env|venv|\.venv|node_modules|__pycache__)(/|$)') { return $true }
    if ($normalized -match '(^|/)(\.superpowers|\.playwright-mcp|tmp_visual_checks)(/|$)') { return $true }
    if ($normalized -match '(^|/)test_output\.txt$') { return $true }
    if ($normalized -match '(^|/)(debug|screenshot|page|visual|tmp)[^/]*\.(png|jpg|jpeg|gif|webp)$') { return $true }

    return $false
}

function Get-ChangedGitPaths {
    $lines = Get-GitOutput -Arguments @('status', '--porcelain=v1', '-uall') -Description 'Read git status'

    foreach ($line in $lines) {
        if ($line.Length -lt 4) { continue }

        $path = $line.Substring(3)
        if ($path -match ' -> ') {
            $path = ($path -split ' -> ')[-1]
        }

        $path.Trim('"')
    }
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repoRoot

$currentBranch = (Get-GitOutput -Arguments @('branch', '--show-current') -Description 'Read current git branch') -join ''
if ($currentBranch.Trim() -ne 'main') {
    throw "Deployment must run from the main branch. Current branch: $currentBranch"
}

Write-Host 'Current local git status:'
Invoke-NativeCommand -FilePath 'git' -Arguments @('status', '--short') -Description 'Show git status'

$changedPaths = @(Get-ChangedGitPaths)
$includedPaths = @($changedPaths | Where-Object { -not (Test-ExcludedFromDeployCommit -Path $_) })
$excludedPaths = @($changedPaths | Where-Object { Test-ExcludedFromDeployCommit -Path $_ })

if ($includedPaths.Count -gt 0) {
    Write-Host 'Paths eligible for deployment commit:'
    $includedPaths | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host 'No changed paths are eligible for a deployment commit.'
}

if ($excludedPaths.Count -gt 0) {
    Write-Host 'Paths excluded from deployment commit:'
    $excludedPaths | ForEach-Object { Write-Host "  $_" }
}

if ($DryRun) {
    Write-Host 'Dry run complete. No files were staged, committed, pushed, or deployed.'
    exit 0
}

Write-Host 'Staging repository changes...'
Invoke-NativeCommand -FilePath 'git' -Arguments @('add', '--all') -Description 'Stage repository changes'

$stagedPaths = @(Get-GitOutput -Arguments @('diff', '--cached', '--name-only') -Description 'Read staged paths')
$stagedExcludedPaths = @($stagedPaths | Where-Object { Test-ExcludedFromDeployCommit -Path $_ })

foreach ($path in $stagedExcludedPaths) {
    Write-Host "Unstaging excluded path: $path"
    Invoke-NativeCommand -FilePath 'git' -Arguments @('restore', '--staged', '--', $path) -Description "Unstage excluded path $path"
}

& git diff --cached --quiet
$diffExitCode = $LASTEXITCODE

if ($diffExitCode -eq 1) {
    Write-Host 'Staged changes that will be committed:'
    Invoke-NativeCommand -FilePath 'git' -Arguments @('diff', '--cached', '--name-status') -Description 'Show staged changes'
    Invoke-NativeCommand -FilePath 'git' -Arguments @('commit', '-m', $commitMessage) -Description 'Create deployment commit'
} elseif ($diffExitCode -eq 0) {
    Write-Host 'No staged changes to commit. Continuing with push/deploy for existing commits.'
} else {
    throw "Check staged changes failed with exit code $diffExitCode."
}

Write-Host 'Pushing main to GitHub...'
Invoke-NativeCommand -FilePath 'git' -Arguments @('push', 'origin', 'main') -Description 'Push main to GitHub'

if (-not (Test-Path -LiteralPath $sshKey)) {
    throw "SSH key not found: $sshKey"
}

$remoteScript = @'
set -euo pipefail

APP_DIR="__REMOTE_APP_DIR__"
SERVICE_NAME="__SERVICE_NAME__"
ENV_BACKUP=".env.backup.deploy"
RESTORE_ENV=0

cd "$APP_DIR"

restore_env() {
  if [ "$RESTORE_ENV" = "1" ] && [ -f "$ENV_BACKUP" ]; then
    mv "$ENV_BACKUP" .env
  fi
}

trap restore_env EXIT

echo 'Backing up .env if present...'
if [ -f .env ]; then
  cp .env "$ENV_BACKUP"
  RESTORE_ENV=1
else
  echo '.env is missing on the VPS; continuing without backup.'
fi

echo 'Checking out .env to prevent merge conflicts if it is tracked...'
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  git checkout -- .env
else
  echo '.env is not tracked by Git; skipping checkout.'
fi

echo 'Pulling latest from GitHub...'
git pull --ff-only origin main

restore_env
RESTORE_ENV=0
trap - EXIT

echo 'Activating environment and installing dependencies...'
source venv/bin/activate
pip install -r requirements.txt

echo 'Running migrations...'
python manage.py migrate

echo 'Collecting static files...'
python manage.py collectstatic --noinput

echo 'Restarting KliniAssist service...'
systemctl restart "$SERVICE_NAME"

echo 'Deployment complete!'
'@

$remoteScript = $remoteScript.Replace('__REMOTE_APP_DIR__', $remoteAppDir).Replace('__SERVICE_NAME__', $serviceName)

Write-Host 'Connecting to VPS to pull and deploy latest code...'
$remoteScript | & ssh -i $sshKey $sshTarget 'bash -s'
if ($LASTEXITCODE -ne 0) {
    throw "VPS deployment failed with exit code $LASTEXITCODE."
}
```

- [ ] **Step 2: Confirm requested behavior appears in the updated script**

Run:

```powershell
Select-String -LiteralPath .\deploy-vps.ps1 -Pattern 'DryRun|git pull --ff-only origin main|push'', ''origin'', ''main|Invoke-Expression'
```

Expected: output includes `DryRun`, `git pull --ff-only origin main`, and the `push`, `origin`, `main` argument array. Output must not include `Invoke-Expression`.

### Task 3: Verify Script Syntax And Non-Destructive Dry Run

**Files:**
- Verify: `deploy-vps.ps1`
- Verify: `git status --short`

- [ ] **Step 1: Parse the PowerShell script without executing deployment**

Run:

```powershell
$tokens = $null; $errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('deploy-vps.ps1', [ref]$tokens, [ref]$errors) | Out-Null; if ($errors.Count -gt 0) { $errors | Format-List *; exit 1 }
```

Expected: exit code `0` and no parser errors.

- [ ] **Step 2: Run dry-run mode without staging, pushing, or deploying**

Run:

```powershell
.\deploy-vps.ps1 -DryRun
```

Expected: output includes `Dry run complete. No files were staged, committed, pushed, or deployed.` It also lists eligible and excluded changed paths based on current `git status`.

- [ ] **Step 3: Confirm no deploy command was executed during verification**

Run:

```powershell
git status --short
```

Expected: only expected local implementation files are changed, and there is no new deployment commit unless the user explicitly ran the full script outside this plan.

- [ ] **Step 4: Report results**

Report the exact results of:

```powershell
$tokens = $null; $errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('deploy-vps.ps1', [ref]$tokens, [ref]$errors) | Out-Null; if ($errors.Count -gt 0) { $errors | Format-List *; exit 1 }
.\deploy-vps.ps1 -DryRun
git status --short
```

Do not run `deploy-vps.ps1` without `-DryRun` unless the user explicitly asks to push and deploy.
