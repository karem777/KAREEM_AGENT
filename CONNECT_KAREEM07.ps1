Write-Host ""
Write-Host "=== KAREEM AGENT - CONNECT TO KAREEM07 ===" -ForegroundColor Cyan
Write-Host ""

$localState = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data\Local State"

if (-not (Test-Path $localState)) {
    Write-Host "Chrome Local State not found:" $localState -ForegroundColor Red
    exit 1
}

try {
    $state = Get-Content -Raw -Encoding UTF8 $localState | ConvertFrom-Json
    $profiles = $state.profile.info_cache

    $match = $null

    foreach ($property in $profiles.PSObject.Properties) {
        $info = $property.Value

        if (
            $info.name -eq "karem07" -or
            $info.shortcut_name -eq "karem07"
        ) {
            $match = $property
            break
        }
    }

    if (-not $match) {
        Write-Host "Profile karem07 was not found." -ForegroundColor Red
        exit 1
    }

    $profileDirectory = $match.Name

    $chrome = $null
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $chrome = $candidate
            break
        }
    }

    if (-not $chrome) {
        $cmd = Get-Command chrome.exe -ErrorAction SilentlyContinue
        if ($cmd) {
            $chrome = $cmd.Source
        }
    }

    if (-not $chrome) {
        Write-Host "Chrome executable not found." -ForegroundColor Red
        exit 1
    }

    Write-Host "karem07 profile directory:" $profileDirectory -ForegroundColor Green
    Write-Host ""

    # Open the selected profile without touching other profile data.
    # This does NOT use a custom user-data-dir and does NOT close Chrome.
    Start-Process `
        -FilePath $chrome `
        -ArgumentList @(
            "--profile-directory=$profileDirectory",
            "--new-window",
            "chrome://inspect/#remote-debugging"
        )

    Write-Host "Opened Remote Debugging inside karem07." -ForegroundColor Green
    Write-Host ""
    Write-Host "In that karem07 window:" -ForegroundColor Yellow
    Write-Host "1) Enable Remote Debugging."
    Write-Host "2) If Chrome asks 'Allow remote debugging?', click Allow."
    Write-Host "3) Keep this Chrome window OPEN."
    Write-Host ""

    Write-Host "Waiting for http://127.0.0.1:9222/json/version ..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds(60)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:9222/json/version" `
                -TimeoutSec 2

            if ($response.StatusCode -eq 200) {
                Write-Host ""
                Write-Host "SUCCESS: Chrome DevTools endpoint is READY." -ForegroundColor Green
                Write-Host ""
                Write-Host "Now start KAREEM_AGENT:" -ForegroundColor Cyan
                Write-Host ".\.venv\Scripts\python.exe app.py"
                exit 0
            }
        }
        catch {
            # Keep waiting.
        }

        Start-Sleep -Seconds 1
    }

    Write-Host ""
    Write-Host "Chrome did not expose port 9222 yet." -ForegroundColor Red
    Write-Host "Make sure Remote Debugging was enabled in the karem07 window." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Manual test:" -ForegroundColor Cyan
    Write-Host "Invoke-WebRequest http://127.0.0.1:9222/json/version"
}
catch {
    Write-Host "Failed:" $_.Exception.Message -ForegroundColor Red
    exit 1
}
