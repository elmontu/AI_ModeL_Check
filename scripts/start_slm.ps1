# Start the bounded local language demo using the existing Ollama installation.
[CmdletBinding()]
param(
    [string]$ModelRoot = '',
    [ValidateSet('qwen2.5:1.5b')]
    [string]$Model = 'qwen2.5:1.5b',
    [switch]$SetupOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-SafeDDirectory {
    param([Parameter(Mandatory)][string]$Path)
    if (-not [IO.Path]::IsPathRooted($Path) -or $Path -match '^[/\\]{2}') {
        throw 'Use an absolute local directory on D:, outside OneDrive.'
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if ($full -notmatch '^D:\\.+$' -or $full -match '(?i)(^|[\\/])OneDrive(?: - [^\\/]*)?([\\/]|$)') {
        throw 'Model and service directories must be local folders on D:, outside OneDrive.'
    }
    if ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($full)).DriveType -ne [IO.DriveType]::Fixed) {
        throw 'D: must be a local fixed drive; mapped or network storage is not supported.'
    }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or -not $item.PSIsContainer) {
                throw "Refusing a file, junction or symbolic link in directory path: $cursor"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $full
}

function Assert-OrdinaryCacheTree {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing a junction or symbolic link in the local model cache: $($item.FullName)"
            }
            if ($item.PSIsContainer) {
                $null = Get-SafeDDirectory $item.FullName
                $pending.Push($item.FullName)
            }
        }
    }
}

function Get-ServiceReceipt {
    param([string]$Path, [string]$Executable)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Length -gt 16384) {
        throw 'Refusing an invalid service receipt. Inspect .local/slm-service/service.json yourself.'
    }
    $bytes = [IO.File]::ReadAllBytes($Path)
    $json = [Text.Encoding]::UTF8.GetString($bytes)
    try { $receipt = $json | ConvertFrom-Json } catch {
        throw 'The local Ollama service receipt is malformed; it will not be overwritten.'
    }
    $required = @('format_version', 'pid', 'start_time_utc', 'executable', 'models_root', 'host')
    $keys = @($receipt.PSObject.Properties.Name)
    if ($keys.Count -ne $required.Count -or @($required | Where-Object { $_ -notin $keys }).Count -ne 0) {
        throw 'The local Ollama service receipt has unsupported fields; it will not be overwritten.'
    }
    foreach ($field in $required) {
        if ([regex]::Matches($json, '"' + [regex]::Escape($field) + '"\s*:').Count -ne 1) {
            throw 'The service receipt must contain each supported field exactly once.'
        }
    }
    # Preserve the ISO text: newer PowerShell versions automatically parse JSON dates.
    $times = [regex]::Matches($json, '"start_time_utc"\s*:\s*"([^"\\]+)"')
    if ($times.Count -ne 1) { throw 'The receipt must have one literal UTC process start time.' }
    $receipt.start_time_utc = $times[0].Groups[1].Value
    if ($receipt.format_version -cne 'local-ollama-service/1' -or $receipt.host -cne '127.0.0.1:11434' -or
        ($receipt.pid -isnot [int] -and $receipt.pid -isnot [long]) -or $receipt.pid -le 0 -or $receipt.pid -gt [int]::MaxValue -or $receipt.executable -isnot [string] -or
        $receipt.models_root -isnot [string] -or $receipt.start_time_utc -isnot [string]) {
        throw 'The local Ollama service receipt does not describe this supported service.'
    }
    $start = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParseExact($receipt.start_time_utc, 'o', [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None, [ref]$start) -or $start.Offset -ne [TimeSpan]::Zero) {
        throw 'The service receipt must contain an exact UTC process start time.'
    }
    if ([IO.Path]::GetFullPath($receipt.executable) -ine $Executable) {
        throw 'The service receipt names a different Ollama executable; it will not be reused or overwritten.'
    }
    $cache = Get-SafeDDirectory $receipt.models_root
    return [pscustomobject]@{ Receipt = $receipt; Start = $start; Cache = $cache; Bytes = $bytes }
}

function Get-ListenerOwners {
    # Inspection failure must not be mistaken for a free port.
    return @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq 11434 })
}

function Assert-ListenerOwner {
    param([object[]]$Listeners, [int]$ProcessId)
    if (@($Listeners | Where-Object { $_.OwningProcess -ne $ProcessId -or $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -gt 0) {
        throw 'Port 11434 is owned by an unknown or differently bound service. Quit that Ollama instance yourself, then restart this helper. No other process was stopped.'
    }
}

function Write-ServiceReceipt {
    param([string]$Path, [object]$Receipt, [byte[]]$PreviousBytes)
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Receipt | ConvertTo-Json) + "`n")
    if ($null -eq $PreviousBytes) {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush() } finally { $stream.Dispose() }
        return
    }
    # service.lock serializes cooperating setups; recheck the validated stale bytes.
    $temporary = Join-Path ([IO.Path]::GetDirectoryName($Path)) ('service-' + [Guid]::NewGuid().ToString('N') + '.json')
    $backup = $temporary + '.bak'
    try {
        [IO.File]::WriteAllBytes($temporary, $bytes)
        $current = [IO.File]::ReadAllBytes($Path)
        if ([Convert]::ToBase64String($current) -cne [Convert]::ToBase64String($PreviousBytes)) {
            throw 'The service receipt changed during setup; refusing to replace it.'
        }
        [IO.File]::Replace($temporary, $Path, $backup)
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup }
    }
}

function Get-InstalledLocalModels {
    $response = $null
    $memory = [IO.MemoryStream]::new()
    try {
        $request = [Net.HttpWebRequest]::Create('http://127.0.0.1:11434/api/tags')
        $request.Proxy = $null
        $request.AllowAutoRedirect = $false
        $request.Timeout = 5000
        $request.ReadWriteTimeout = 5000
        $response = $request.GetResponse()
        $stream = $response.GetResponseStream()
        $buffer = [byte[]]::new(4096)
        while (($length = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($memory.Length + $length -gt 2000000) { throw 'The local model inventory is too large.' }
            $memory.Write($buffer, 0, $length)
        }
        $inventory = [Text.Encoding]::UTF8.GetString($memory.ToArray()) | ConvertFrom-Json
        if ('models' -notin @($inventory.PSObject.Properties.Name) -or $inventory.models -isnot [array]) {
            throw 'The owned local runtime returned an invalid model inventory.'
        }
        return @($inventory.models)
    } finally {
        $memory.Dispose()
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Wait-LocalService {
    param([Diagnostics.Process]$Process)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 20) {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Ollama exited during startup. Read .local/slm-service logs, then retry.' }
        $listeners = @(Get-ListenerOwners)
        Assert-ListenerOwner $listeners $Process.Id
        if ($listeners.Count -gt 0) {
            $response = $null
            try {
                $request = [Net.HttpWebRequest]::Create('http://127.0.0.1:11434/api/tags')
                $request.Proxy = $null
                $request.AllowAutoRedirect = $false
                $request.Timeout = 1000
                $request.ReadWriteTimeout = 1000
                $response = $request.GetResponse()
                if ([int]$response.StatusCode -eq 200) { return }
            } catch [Net.WebException] {
                # Keep waiting only for this owned loopback process.
            } finally { if ($null -ne $response) { $response.Dispose() } }
        }
        Start-Sleep -Milliseconds 200
    }
    throw 'Ollama was not ready within 20 seconds. Read .local/slm-service logs; the owned process and receipt are retained for retry.'
}

$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $ModelRoot) { $ModelRoot = Join-Path $repository '.local/slm-models' }
$cacheRoot = Get-SafeDDirectory $ModelRoot
$serviceRoot = Get-SafeDDirectory (Join-Path $repository '.local/slm-service')
Assert-OrdinaryCacheTree $cacheRoot
Assert-OrdinaryCacheTree $serviceRoot
$command = Get-Command -Name ollama.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1
$executable = [IO.Path]::GetFullPath($command.Source)
if ([IO.Path]::GetFileName($executable) -ine 'ollama.exe') { throw 'Select the installed official ollama.exe on PATH.' }
$receiptPath = Join-Path $serviceRoot 'service.json'
$owned = Get-ServiceReceipt $receiptPath $executable
$process = $null
if ($null -ne $owned) {
    $candidate = Get-Process -Id $owned.Receipt.pid -ErrorAction SilentlyContinue
    if ($null -ne $candidate) {
        if ($candidate.StartTime.ToUniversalTime().Ticks -eq $owned.Start.UtcDateTime.Ticks -and $candidate.Path -ieq $executable) {
            if ($owned.Cache -ine $cacheRoot) { throw 'The owned Ollama service uses a different model cache. Quit it yourself before changing ModelRoot.' }
            $process = $candidate
        }
    }
}
$listeners = @(Get-ListenerOwners)
if ($null -eq $process -and $listeners.Count -gt 0) {
    throw 'Port 11434 has an existing service without matching helper ownership. Quit that Ollama instance yourself, then restart this helper. No other process was stopped.'
}
if ($null -ne $process) { Assert-ListenerOwner $listeners $process.Id }
[IO.Directory]::CreateDirectory($cacheRoot) | Out-Null
[IO.Directory]::CreateDirectory($serviceRoot) | Out-Null
$lockPath = Join-Path $serviceRoot 'service.lock'
$serviceLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$environmentNames = @('OLLAMA_MODELS', 'OLLAMA_HOST', 'OLLAMA_NO_CLOUD')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    [Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $cacheRoot, 'Process')
    [Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'Process')
    [Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'Process')
    if ($null -eq $process) {
        # Recheck under the setup lock before creating a server or receipt.
        if (@(Get-ListenerOwners).Count -gt 0) { throw 'Port 11434 became occupied. Quit the other Ollama instance yourself and retry.' }
        $current = Get-ServiceReceipt $receiptPath $executable
        if ($null -ne $current -and $null -eq $owned) { throw 'Another setup created a service receipt; retry to inspect its ownership.' }
        if ($null -ne $owned -and ($null -eq $current -or [Convert]::ToBase64String($current.Bytes) -cne [Convert]::ToBase64String($owned.Bytes))) {
            throw 'The stale service receipt changed during setup; retry to inspect its ownership.'
        }
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
        $process = Start-Process -FilePath $executable -ArgumentList @('serve') -WindowStyle Hidden -PassThru -WorkingDirectory $repository `
            -RedirectStandardOutput (Join-Path $serviceRoot "$stamp.stdout.log") -RedirectStandardError (Join-Path $serviceRoot "$stamp.stderr.log")
        $receipt = [ordered]@{ format_version = 'local-ollama-service/1'; pid = $process.Id
            start_time_utc = $process.StartTime.ToUniversalTime().ToString('o'); executable = $executable
            models_root = $cacheRoot; host = '127.0.0.1:11434' }
        $oldBytes = if ($null -eq $owned) { $null } else { $owned.Bytes }
        Write-ServiceReceipt $receiptPath $receipt $oldBytes
    }
    Wait-LocalService $process
    $serviceLock.Dispose()
    $serviceLock = $null
    Write-Host "Local Ollama ready on 127.0.0.1:11434; model files: $cacheRoot"
    $installed = @(Get-InstalledLocalModels)
    if (@($installed | Where-Object { $_.name -ceq $Model }).Count -eq 0) {
        & $executable pull $Model
        if ($LASTEXITCODE -ne 0) { throw "Ollama could not pull $Model. The owned service and its logs are retained." }
        $installed = @(Get-InstalledLocalModels)
    } else { Write-Host "Reusing installed $Model without another download." }
    if (@($installed | Where-Object { $_.name -ceq $Model }).Count -eq 0) { throw "The exact local tag $Model is not installed." }
    $manifest = Join-Path $cacheRoot 'manifests/registry.ollama.ai/library/qwen2.5/1.5b'
    $null = Get-SafeDDirectory ([IO.Path]::GetDirectoryName($manifest))
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'The selected model has no local manifest in the configured D: cache.' }
    $manifestInfo = Get-Item -LiteralPath $manifest -Force
    if (($manifestInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $manifestInfo.Length -eq 0) { throw 'The local model manifest is empty or a link.' }
    if (-not $SetupOnly) {
        & $executable run $Model
        if ($LASTEXITCODE -ne 0) { throw "Ollama exited with code $LASTEXITCODE." }
    }
} finally {
    if ($null -ne $serviceLock) { $serviceLock.Dispose() }
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
}
