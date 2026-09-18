#!/usr/bin/env pwsh
# Ilija OS Deploy: push -> pull on EliteBook -> restart service
param(
    [string]$Message = "update"
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$ssh_key = "$env:USERPROFILE\.ssh\owlp_homeserver_ed25519"
$host_ip = "192.168.152.46"
$ssh = "ssh -i `"$ssh_key`" -o ConnectTimeout=10 manuel@$host_ip"

Write-Host "==> git add + commit + push" -ForegroundColor Cyan
git -C $repo add -A
$status = git -C $repo status --porcelain
if ($status) {
    git -C $repo commit -m $Message
} else {
    Write-Host "    Keine neuen Aenderungen." -ForegroundColor Yellow
}
git -C $repo push

Write-Host "==> EliteBook: git pull + restart" -ForegroundColor Cyan
Invoke-Expression "$ssh 'sudo -u ilija git -C /opt/ilija-os/ilija pull && sudo systemctl restart ilija.service && echo OK'"

Write-Host "==> Fertig." -ForegroundColor Green
