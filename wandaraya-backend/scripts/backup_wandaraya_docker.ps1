param(
    [string]$DestinationRoot = ""
)

$ErrorActionPreference = "Stop"
$backendRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $backendRoot -Parent
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    $DestinationRoot = Join-Path $workspaceRoot "backups"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $DestinationRoot "wandaraya_docker_backup_$timestamp"
$databaseDir = Join-Path $backupRoot "databases"
$volumeDir = Join-Path $backupRoot "docker_volumes"
$bindDir = Join-Path $backupRoot "bind_mounts"
$inventoryDir = Join-Path $backupRoot "inventory"
$configDir = Join-Path $backupRoot "configuration"
$snapshotDir = Join-Path $backupRoot "qdrant_logical_snapshots"

@($backupRoot, $databaseDir, $volumeDir, $bindDir, $inventoryDir, $configDir, $snapshotDir) |
    ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

function Invoke-Docker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($Arguments -join ' ')"
    }
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start Docker Desktop and retry."
}

$wandarayaContainers = @(
    docker ps -a --format "{{.Names}}" | Where-Object { $_ -like "wandaraya*" }
)
$runningContainers = @(
    docker ps --format "{{.Names}}" | Where-Object { $_ -like "wandaraya*" }
)

docker ps -a --no-trunc | Out-File (Join-Path $inventoryDir "docker_ps_all.txt") -Encoding utf8
docker image ls --digests --no-trunc | Out-File (Join-Path $inventoryDir "docker_images.txt") -Encoding utf8
docker volume ls | Out-File (Join-Path $inventoryDir "docker_volumes.txt") -Encoding utf8
docker network ls | Out-File (Join-Path $inventoryDir "docker_networks.txt") -Encoding utf8
docker version | Out-File (Join-Path $inventoryDir "docker_version.txt") -Encoding utf8
docker system df -v | Out-File (Join-Path $inventoryDir "docker_disk_usage.txt") -Encoding utf8

foreach ($container in $wandarayaContainers) {
    docker inspect $container | Out-File (Join-Path $inventoryDir "container_$container.json") -Encoding utf8
}

$composeFiles = @(
    Get-ChildItem -Path $backendRoot -File |
        Where-Object { $_.Name -match "^(docker-compose|compose).*\.ya?ml$" }
)
foreach ($file in $composeFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $configDir $file.Name) -Force
}
if (Test-Path (Join-Path $backendRoot ".env")) {
    Copy-Item -LiteralPath (Join-Path $backendRoot ".env") -Destination (Join-Path $configDir ".env") -Force
}
if (Test-Path (Join-Path $backendRoot ".env.example")) {
    Copy-Item -LiteralPath (Join-Path $backendRoot ".env.example") -Destination (Join-Path $configDir ".env.example") -Force
}
@"
WARNING: This backup contains environment credentials and API keys in plaintext.
Store it only on an encrypted external drive or another access-controlled location.
Do not commit this backup to Git or share it publicly.
"@ | Set-Content (Join-Path $backupRoot "SENSITIVE_BACKUP_NOTICE.txt") -Encoding utf8

# Native database dumps are the safest and most portable restoration source.
Invoke-Docker @("exec", "wandaraya-postgres", "sh", "-lc", "pg_dump -U postgres -d wandaraya -Fc -f /tmp/wandaraya.dump && pg_dump -U postgres -d wandaraya --no-owner --no-privileges -f /tmp/wandaraya.sql && pg_dumpall -U postgres --globals-only -f /tmp/wandaraya_globals.sql")
Invoke-Docker @("cp", "wandaraya-postgres:/tmp/wandaraya.dump", (Join-Path $databaseDir "wandaraya.dump"))
Invoke-Docker @("cp", "wandaraya-postgres:/tmp/wandaraya.sql", (Join-Path $databaseDir "wandaraya.sql"))
Invoke-Docker @("cp", "wandaraya-postgres:/tmp/wandaraya_globals.sql", (Join-Path $databaseDir "wandaraya_globals.sql"))

Invoke-Docker @("exec", "wandaraya-airflow-metadata", "sh", "-lc", "pg_dump -U airflow -d airflow -Fc -f /tmp/airflow.dump && pg_dump -U airflow -d airflow --no-owner --no-privileges -f /tmp/airflow.sql")
Invoke-Docker @("cp", "wandaraya-airflow-metadata:/tmp/airflow.dump", (Join-Path $databaseDir "airflow.dump"))
Invoke-Docker @("cp", "wandaraya-airflow-metadata:/tmp/airflow.sql", (Join-Path $databaseDir "airflow.sql"))

if ($runningContainers -contains "wandaraya-redis") {
    Invoke-Docker @("exec", "wandaraya-redis", "redis-cli", "SAVE")
}

# Create portable Qdrant collection snapshots in addition to the raw volume copy.
try {
    $collectionsResponse = Invoke-RestMethod -Uri "http://localhost:6333/collections" -Method Get -TimeoutSec 30
    foreach ($collection in $collectionsResponse.result.collections) {
        $name = [string]$collection.name
        $snapshotResponse = Invoke-RestMethod -Uri "http://localhost:6333/collections/$name/snapshots" -Method Post -TimeoutSec 120
        $snapshotName = [string]$snapshotResponse.result.name
        if (-not [string]::IsNullOrWhiteSpace($snapshotName)) {
            Invoke-WebRequest -Uri "http://localhost:6333/collections/$name/snapshots/$snapshotName" -OutFile (Join-Path $snapshotDir "$name--$snapshotName") -TimeoutSec 300
        }
    }
} catch {
    "Qdrant logical snapshot warning: $($_.Exception.Message)" |
        Set-Content (Join-Path $snapshotDir "SNAPSHOT_WARNING.txt") -Encoding utf8
}

$volumeNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($container in $wandarayaContainers) {
    $mounts = docker inspect $container --format "{{range .Mounts}}{{if eq .Type `"volume`"}}{{.Name}}{{println}}{{end}}{{end}}"
    foreach ($mount in $mounts) {
        $name = $mount.Trim()
        if ($name) { [void]$volumeNames.Add($name) }
    }
}
foreach ($name in (docker volume ls --format "{{.Name}}" | Where-Object { $_ -like "wandaraya*" })) {
    [void]$volumeNames.Add($name.Trim())
}

$volumeNames | Sort-Object | Set-Content (Join-Path $inventoryDir "backed_up_volume_names.txt") -Encoding utf8
foreach ($volume in ($volumeNames | Sort-Object)) {
    docker volume inspect $volume | Out-File (Join-Path $inventoryDir "volume_$volume.json") -Encoding utf8
}

# Stop only WANDARAYA containers while raw files are archived for consistency.
if ($runningContainers.Count -gt 0) {
    Invoke-Docker (@("stop", "--time", "30") + $runningContainers)
}

try {
    foreach ($volume in ($volumeNames | Sort-Object)) {
        $safeName = $volume -replace "[^A-Za-z0-9_.-]", "_"
        $dockerArguments = @(
            "run", "--rm",
            "--mount", "type=volume,src=$volume,dst=/source,readonly",
            "--mount", "type=bind,src=$volumeDir,dst=/backup",
            "postgis/postgis:17-3.5",
            "sh", "-lc", "cd /source && tar -czf /backup/$safeName.tar.gz ."
        )
        Invoke-Docker $dockerArguments
    }

    $bindMounts = @(
        @{ Name = "postgres-data"; Path = Join-Path $backendRoot "postgres-data" },
        @{ Name = "redis-data"; Path = Join-Path $backendRoot "redis-data" },
        @{ Name = "qdrant-snapshots"; Path = Join-Path $backendRoot "qdrant-snapshots" },
        @{ Name = "qdrant-replacement-snapshots"; Path = Join-Path $backendRoot "qdrant-replacement-snapshots" },
        @{ Name = "qdrant-recovery-verify-snapshots"; Path = Join-Path $backendRoot "qdrant-recovery-verify-snapshots" }
    )
    foreach ($entry in $bindMounts) {
        if (Test-Path -LiteralPath $entry.Path) {
            $parent = Split-Path $entry.Path -Parent
            $leaf = Split-Path $entry.Path -Leaf
            & tar.exe -czf (Join-Path $bindDir "$($entry.Name).tar.gz") -C $parent $leaf
            if ($LASTEXITCODE -ne 0) { throw "Failed to archive bind mount: $($entry.Path)" }
        }
    }

    # Preserve all source, migration, notebook, model, report and configuration files,
    # while excluding runtime stores already archived above and reproducible caches.
    $sourceArchive = Join-Path $backupRoot "wandaraya_project_source.tar.gz"
    $tarArguments = @(
        "-czf", $sourceArchive,
        "--exclude=backups",
        "--exclude=wandaraya-backend/postgres-data",
        "--exclude=wandaraya-backend/redis-data",
        "--exclude=wandaraya-backend/qdrant-snapshots",
        "--exclude=wandaraya-backend/qdrant-replacement-snapshots",
        "--exclude=wandaraya-backend/qdrant-recovery-verify-snapshots",
        "--exclude=wandaraya-backend/logs",
        "--exclude=wandaraya-backend/.venv",
        "--exclude=wandaraya_frontend/.dart_tool",
        "--exclude=wandaraya_frontend/build",
        "-C", $workspaceRoot,
        "README.md", ".git", ".gitattributes", "wandaraya-backend", "wandaraya_frontend", "data", "output", "tools"
    )
    & tar.exe @tarArguments
    if ($LASTEXITCODE -ne 0) { throw "Failed to archive WANDARAYA project source." }
}
finally {
    if ($runningContainers.Count -gt 0) {
        Invoke-Docker (@("start") + $runningContainers)
    }
}

@"
# WANDARAYA Docker backup restoration

Backup created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")

## Recommended restoration order

1. Install Git, Docker Desktop, Flutter and the project's required Python tooling.
2. Extract `wandaraya_project_source.tar.gz` into the desired workspace.
3. Copy `configuration/.env` into `wandaraya-backend/.env` and protect it as a secret.
4. Run `docker compose pull` and `docker compose build` from `wandaraya-backend`.
5. Create the named volumes listed in `inventory/backed_up_volume_names.txt`.
6. Restore each `docker_volumes/<volume>.tar.gz` into the matching empty named volume.
7. Restore `bind_mounts/postgres-data.tar.gz` and `bind_mounts/redis-data.tar.gz` into `wandaraya-backend`.
8. Start Compose. If raw PostgreSQL data is incompatible with a newer engine, initialize an empty database and restore `databases/wandaraya.dump` with `pg_restore` instead.
9. Restore Airflow from `databases/airflow.dump` if its raw volume cannot be reused.
10. Confirm PostgreSQL, Qdrant collection count, MinIO, Redis and API health before using the application.

## PostgreSQL portable restore example

`docker exec -i wandaraya-postgres pg_restore -U postgres -d wandaraya --clean --if-exists < databases/wandaraya.dump`

## Important

- Docker images were not exported because the local custom images require more free space than available. Exact image IDs and versions are recorded in `inventory/docker_images.txt`; custom images are reproducible from the included Dockerfiles.
- This backup contains plaintext credentials and API keys.
- Verify `SHA256SUMS.txt` after copying the folder to external storage.
"@ | Set-Content (Join-Path $backupRoot "RESTORE_INSTRUCTIONS.md") -Encoding utf8

$filesToHash = Get-ChildItem -LiteralPath $backupRoot -Recurse -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object FullName
$hashLines = foreach ($file in $filesToHash) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $relative = $file.FullName.Substring($backupRoot.Length + 1).Replace("\", "/")
    "$hash  $relative"
}
$hashLines | Set-Content (Join-Path $backupRoot "SHA256SUMS.txt") -Encoding ascii

$totalBytes = (Get-ChildItem -LiteralPath $backupRoot -Recurse -File | Measure-Object Length -Sum).Sum
@{
    backup_root = $backupRoot
    created_at = (Get-Date).ToString("o")
    total_bytes = $totalBytes
    total_gib = [math]::Round($totalBytes / 1GB, 3)
    backed_up_volumes = @($volumeNames | Sort-Object)
    running_containers_restarted = $runningContainers
} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $backupRoot "BACKUP_MANIFEST.json") -Encoding utf8

Write-Output "BACKUP_ROOT=$backupRoot"
Write-Output "BACKUP_SIZE_GIB=$([math]::Round($totalBytes / 1GB, 3))"
Write-Output "BACKED_UP_VOLUMES=$($volumeNames.Count)"
