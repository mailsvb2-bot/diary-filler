param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,

    [Parameter(Mandatory = $true)]
    [string]$RegistrationToken,

    [Parameter(Mandatory = $true)]
    [string]$RunnerVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$ExpectedSha256,

    [string]$RunnerName = "",
    [string]$InstallRoot = "$env:LOCALAPPDATA\GitHubActionsRunner\diary-filler",
    [string]$Labels = ""
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "install_windows_live_runner.ps1") `
    -RepositoryUrl $RepositoryUrl `
    -RegistrationToken $RegistrationToken `
    -RunnerVersion $RunnerVersion `
    -ExpectedSha256 $ExpectedSha256 `
    -TargetOs windows11 `
    -RunnerName $RunnerName `
    -InstallRoot $InstallRoot `
    -Labels $Labels
