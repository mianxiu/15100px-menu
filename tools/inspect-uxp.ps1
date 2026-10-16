# Read-only UXP startup diagnostics. No plugin configuration, document reads,
# registry changes, Photoshop activation, input or installation. Only writes
# a new report; never overwrites an existing file. Windows PowerShell 5.1.
[CmdletBinding()]
param([string]$OutputPath, [ValidateRange(1,65535)][int]$BackendPort=15151)
$ErrorActionPreference='Stop'
function Protect-Text([string]$Text) {
    if ($env:USERPROFILE) { $Text=$Text.Replace($env:USERPROFILE, '<USER>') }
    if ($env:USERNAME) { $Text=$Text -replace ('(?i)(?<=\\)'+[regex]::Escape($env:USERNAME)+'(?=\\)'), '<USER>' }
    return $Text
}
$plugin=Join-Path $env:APPDATA 'Adobe\UXP\Plugins\External\com.15100px.menu.offline-probe_PS'
$report=[ordered]@{schema=1;read_only=$true;at=(Get-Date).ToString('o');windows=[Environment]::OSVersion.Version.ToString();plugin_path=(Protect-Text $plugin);plugin_exists=(Test-Path -LiteralPath $plugin -PathType Container)}
$files=@()
foreach($name in @('manifest.json','main.js','labels.js')) {
    $path=Join-Path $plugin $name
    if(Test-Path -LiteralPath $path -PathType Leaf) {
        $file=Get-Item -LiteralPath $path
        $files+= [ordered]@{name=$name;size=$file.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
}
$report.files=$files
try {
    $manifest=Get-Content -LiteralPath (Join-Path $plugin 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $report.manifest=[ordered]@{id=$manifest.id;version=$manifest.version;main=$manifest.main;manifestVersion=$manifest.manifestVersion;host=$manifest.host;entrypoints=@($manifest.entrypoints | ForEach-Object { [ordered]@{id=$_.id;type=$_.type} })}
} catch {$report.manifest_error='Cannot read or parse manifest'}
$hosts=@()
foreach($process in @(Get-Process -Name Photoshop -ErrorAction SilentlyContinue)) {
    try {
        $exe=$process.MainModule.FileName
        $core=Join-Path (Split-Path -Parent $exe) 'Required\UXP'
        $hosts+=[ordered]@{pid=$process.Id;version=$process.MainModule.FileVersionInfo.FileVersion;executable=(Protect-Text $exe);uxp_core_present=(Test-Path -LiteralPath $core -PathType Container);plugin_manager_present=(Test-Path -LiteralPath (Join-Path $core 'com.adobe.pluginspanel') -PathType Container)}
    } catch {$hosts+=[ordered]@{pid=$process.Id;error='Cannot inspect Photoshop process path'}}
}
$report.photoshop=$hosts
try {
    $s=Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/status" -TimeoutSec 5
    $report.backend=[ordered]@{version=$s.version;installed=$s.uxp.installed;installed_version=$s.uxp.version;bundled_version=$s.uxp.bundled_version;installation=$s.uxp.installation;install_error=(Protect-Text ([string]$s.uxp.error));plugin_path=(Protect-Text ([string]$s.uxp.plugin_dir));same_user_plugin_path=([string]$s.uxp.plugin_dir -ieq $plugin);loaded_version=$s.photoshop.uxp_version;ready=$s.photoshop.uxp_ready;busy=$s.photoshop.busy}
} catch {$report.backend=[ordered]@{error='Backend unavailable'}}
$logs=@()
$adobe=Join-Path $env:APPDATA 'Adobe'
foreach($hostDir in @(Get-ChildItem -LiteralPath $adobe -Directory -ErrorAction SilentlyContinue | Where-Object {$_.Name -match '^Adobe Photoshop 20\d\d$'})) {
    $logDir=Join-Path $hostDir.FullName 'Logs'
    foreach($file in @(Get-ChildItem -LiteralPath $logDir -Filter 'UXPLogs_*.log' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 2)) {
        # Only loader diagnostics, never console output or arbitrary log tails.
        $lines=@(Get-Content -LiteralPath $file.FullName -Tail 4000 -Encoding UTF8 | Where-Object {
            $_ -notmatch '\[console\]' -and $_ -match '(?i)(upic::.*(fallback|plugin|manifest|error|fail|disabled)|\b(loader|pluginmanager|plugin manager)\b.*(15100px|error|fail|disabled)|15100px.*(manifest|load|register|error|fail|disabled))'
        } | Select-Object -Last 80 | ForEach-Object {Protect-Text $_})
        $logs+=[ordered]@{host=$hostDir.Name;file=$file.Name;modified=$file.LastWriteTime.ToString('o');size=$file.Length;loader_lines=$lines}
    }
}
$report.logs=$logs
if(-not $OutputPath) {$OutputPath=Join-Path ([Environment]::GetFolderPath('Desktop')) ('ps-menu-uxp-startup-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,6)+'.json')}
$OutputPath=[IO.Path]::GetFullPath($OutputPath)
$json=$report | ConvertTo-Json -Depth 12
$bytes=(New-Object Text.UTF8Encoding($false)).GetBytes($json)
$stream=[IO.File]::Open($OutputPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
Write-Output ('Saved read-only UXP startup report: '+$OutputPath)
