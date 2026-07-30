[CmdletBinding()]
param(
    [switch]$AllowDirty,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$productionBranch = "main"
$productionRemote = "origin"
$expectedRepository = "sportscave1/sports-cave-image-factory"
$localHookFile = ".render/deploy-hook.txt"
$productionHealthUrl = "https://sports-cave-image-factory.onrender.com/_stcore/health"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
    return $output
}

function Resolve-DeployHook {
    $hook = [string]$env:SPORTS_CAVE_RENDER_DEPLOY_HOOK_URL
    if ([string]::IsNullOrWhiteSpace($hook) -and (Test-Path -LiteralPath $localHookFile)) {
        $hook = [System.IO.File]::ReadAllText(
            (Resolve-Path -LiteralPath $localHookFile)
        )
    }
    $hook = $hook.Trim()
    if ([string]::IsNullOrWhiteSpace($hook)) {
        throw (
            "Render deployment is not configured. Set " +
            "SPORTS_CAVE_RENDER_DEPLOY_HOOK_URL or place the hook in the ignored " +
            "$localHookFile file."
        )
    }

    $hookUri = $null
    $hookParsed = [System.Uri]::TryCreate(
        $hook,
        [System.UriKind]::Absolute,
        [ref]$hookUri
    )
    if (
        (-not $hookParsed) -or
        ($hookUri.Scheme -ne "https") -or
        ($hookUri.Host -ne "api.render.com") -or
        (-not $hookUri.AbsolutePath.StartsWith(
            "/deploy/",
            [System.StringComparison]::Ordinal
        ))
    ) {
        throw "The configured Render deploy hook is invalid."
    }
    return $hook
}

function Wait-ForRenderDeploy {
    param(
        [string]$DeployId,
        [string]$CommitSha
    )

    $apiKey = [string]$env:SPORTS_CAVE_RENDER_API_KEY
    $serviceId = [string]$env:SPORTS_CAVE_RENDER_SERVICE_ID
    if (
        [string]::IsNullOrWhiteSpace($DeployId) -or
        [string]::IsNullOrWhiteSpace($apiKey) -or
        [string]::IsNullOrWhiteSpace($serviceId)
    ) {
        Write-Output (
            "Render accepted the deploy for $CommitSha. Configure " +
            "SPORTS_CAVE_RENDER_API_KEY and SPORTS_CAVE_RENDER_SERVICE_ID " +
            "to poll deployment status from this script."
        )
        return
    }

    $headers = @{ Authorization = "Bearer $apiKey" }
    $statusUrl = "https://api.render.com/v1/services/$serviceId/deploys/$DeployId"
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(20)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $deploy = Invoke-RestMethod -Method Get -Uri $statusUrl -Headers $headers
        $status = [string]$deploy.status
        if ($status -eq "live") {
            $deployedCommit = [string]$deploy.commit.id
            if (
                (-not [string]::IsNullOrWhiteSpace($deployedCommit)) -and
                (-not $deployedCommit.StartsWith(
                    $CommitSha,
                    [System.StringComparison]::OrdinalIgnoreCase
                ))
            ) {
                throw "Render completed a different commit than the pushed production SHA."
            }
            $health = Invoke-WebRequest -UseBasicParsing -Uri $productionHealthUrl
            if ($health.StatusCode -ne 200) {
                throw "Render is live, but the production health check did not return HTTP 200."
            }
            Write-Output "Render is live and healthy at commit $CommitSha."
            return
        }
        if ($status -in @("build_failed", "update_failed", "canceled", "deactivated")) {
            throw "Render deployment ended with status: $status"
        }
        Start-Sleep -Seconds 10
    }
    throw "Timed out waiting for Render deployment $DeployId."
}

$repositoryRoot = (Invoke-Git rev-parse --show-toplevel | Select-Object -First 1).Trim()
Set-Location -LiteralPath $repositoryRoot

$currentBranch = (Invoke-Git branch --show-current | Select-Object -First 1).Trim()
if ($currentBranch -ne $productionBranch) {
    throw "Refusing to deploy branch '$currentBranch'. Production uses '$productionBranch'."
}

$remoteUrl = (Invoke-Git remote get-url $productionRemote | Select-Object -First 1).Trim()
if ($remoteUrl -notmatch [regex]::Escape($expectedRepository)) {
    throw "Refusing to deploy: origin is not the expected Sports Cave repository."
}

$workingChanges = @(Invoke-Git status --porcelain --untracked-files=all)
if ($workingChanges.Count -gt 0 -and -not $AllowDirty) {
    throw "Refusing to deploy with uncommitted files. Commit or preserve them first."
}
if ($workingChanges.Count -gt 0) {
    Write-Warning "Deploying the committed SHA while unrelated local files remain uncommitted."
}

$deployHook = Resolve-DeployHook
Invoke-Git fetch $productionRemote $productionBranch | Out-Null
$remoteSha = (
    Invoke-Git rev-parse "refs/remotes/$productionRemote/$productionBranch" |
        Select-Object -First 1
).Trim()
$localSha = (Invoke-Git rev-parse HEAD | Select-Object -First 1).Trim()

& git merge-base --is-ancestor $remoteSha $localSha
if ($LASTEXITCODE -ne 0) {
    throw "Production has commits missing locally. Reconcile origin/main before deploying."
}

if ($ValidateOnly) {
    Write-Output "Render deployment checks passed for $localSha."
    exit 0
}

Invoke-Git push $productionRemote "HEAD:refs/heads/$productionBranch" | Out-Null
Invoke-Git fetch $productionRemote $productionBranch | Out-Null
$confirmedRemoteSha = (
    Invoke-Git rev-parse "refs/remotes/$productionRemote/$productionBranch" |
        Select-Object -First 1
).Trim()
if ($confirmedRemoteSha -ne $localSha) {
    throw "The pushed production SHA does not match local HEAD."
}

$response = Invoke-RestMethod -Method Post -Uri $deployHook
$deployId = ""
if ($null -ne $response.deploy -and $null -ne $response.deploy.id) {
    $deployId = [string]$response.deploy.id
} elseif ($null -ne $response.id) {
    $deployId = [string]$response.id
}
Write-Output "Render deploy triggered for commit $localSha."
Wait-ForRenderDeploy -DeployId $deployId -CommitSha $localSha
