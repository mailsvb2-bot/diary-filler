param(
    [switch]$RequireWord = $true,
    [switch]$RequirePrinter = $true,
    [switch]$RequireInno = $true,
    [string]$JsonOut = "live-e2e-artifacts\preflight.json"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "windows_live_e2e_preflight.ps1") `
    -TargetOs windows11 `
    -RequireWord:$RequireWord `
    -RequirePrinter:$RequirePrinter `
    -RequireInno:$RequireInno `
    -JsonOut $JsonOut
