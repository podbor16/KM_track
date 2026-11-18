# Run as administrator on the backup host.
param(
    [Parameter(Mandatory)] [string]$Python,
    [Parameter(Mandatory)] [string]$Config,
    [Parameter(Mandatory)] [pscredential]$Credential
)

$ErrorActionPreference = 'Stop'
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$configPath = (Resolve-Path -LiteralPath $Config).Path
$runner = Join-Path $PSScriptRoot 'backup_krasmarafon.py'
if ($runner.Contains('"') -or $configPath.Contains('"')) {
    throw 'Quotes are not supported inside paths.'
}

function Register-BackupTask {
    param([string]$Command, [object[]]$Trigger, [timespan]$Limit, [int]$Retries)
    $action = New-ScheduledTaskAction -Execute $pythonPath -Argument (
        '"{0}" {1} --config "{2}"' -f $runner, $Command, $configPath
    ) -WorkingDirectory $PSScriptRoot
    $settings = @{
        StartWhenAvailable = $true
        MultipleInstances = 'IgnoreNew'
        ExecutionTimeLimit = $Limit
    }
    if ($Retries -gt 0) {
        $settings.RestartCount = $Retries
        $settings.RestartInterval = New-TimeSpan -Minutes 15
    }
    $task = @{
        TaskName = "KM backup - $Command"
        Action = $action
        Trigger = $Trigger
        Settings = New-ScheduledTaskSettingsSet @settings
        User = $Credential.UserName
        Password = $Credential.GetNetworkCredential().Password
        Force = $true
    }
    Register-ScheduledTask @task | Out-Null
}

$today = (Get-Date).Date
$cycle = @(0, 8, 16 | ForEach-Object { New-ScheduledTaskTrigger -Daily -At ($today.AddHours($_)) })
$monitor = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 15)
$dev = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At ($today.AddHours(6))
Register-BackupTask -Command cycle -Trigger $cycle -Limit (New-TimeSpan -Hours 4) -Retries 2
Register-BackupTask -Command monitor -Trigger @($monitor) -Limit (New-TimeSpan -Minutes 5) -Retries 0
Register-BackupTask -Command dev -Trigger @($dev) -Limit (New-TimeSpan -Hours 2) -Retries 2
