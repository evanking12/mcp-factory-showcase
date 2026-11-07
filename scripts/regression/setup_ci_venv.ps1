param(
    [string]$VenvPath = ".venv",
    [int]$MaxAttempts = 3,
    [int]$RetrySleepSeconds = 10
)

$ErrorActionPreference = "Stop"

function Invoke-WithRetry {
    param(
        [scriptblock]$Command,
        [string]$Label
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-Host "ci-venv: $Label attempt $attempt/$MaxAttempts"
            & $Command
            Write-Host "ci-venv: $Label complete"
            return
        } catch {
            Write-Warning "ci-venv: $Label failed on attempt $attempt/${MaxAttempts}: $($_.Exception.Message)"
            if ($attempt -ge $MaxAttempts) {
                throw
            }
            Start-Sleep -Seconds $RetrySleepSeconds
        }
    }
}

python -m venv $VenvPath
$python = Join-Path $VenvPath "Scripts\python.exe"

Invoke-WithRetry -Label "upgrade pip" -Command {
    & $python -m pip install --upgrade pip --retries 5 --timeout 30
}

Invoke-WithRetry -Label "install requirements" -Command {
    & $python -m pip install -r requirements.txt -r api/requirements.txt --retries 5 --timeout 30
}
