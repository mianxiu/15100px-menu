# Read-only, standalone diagnostics for PCs without Python. No input, UXP
# requests, document reads, credentials, clipboard writes or settings changes.
# The only write is the requested JSON diagnostic report (CreateNew).
[CmdletBinding()]
param(
    [ValidateRange(0,60)][int]$DelaySeconds = 5,
    [ValidateRange(1,30)][int]$Samples = 10,
    [ValidateRange(100,5000)][int]$IntervalMs = 1000,
    [string]$OutputPath,
    [ValidateRange(1,65535)][int]$BackendPort = 15151
)
$ErrorActionPreference = 'Stop'
if (-not ('PhotoshopPanelReadOnly' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class PhotoshopPanelReadOnly {
    public delegate bool Callback(IntPtr hwnd, IntPtr param);
    [DllImport("user32.dll")] public static extern bool EnumWindows(Callback cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr root, Callback cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int x,y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int left,top,right,bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct GuiInfo {
        public int size; public uint flags;
        public IntPtr active,focus,capture,menuOwner,moveSize,caret; public Rect caretRect;
    }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point p);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] public static extern bool GetGUIThreadInfo(uint thread, ref GuiInfo info);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr token);
    [DllImport("advapi32.dll")] static extern bool GetTokenInformation(IntPtr t,int kind,out int value,int size,out int needed);
    public static int Elevated(uint pid) {
        IntPtr p=OpenProcess(0x1000,false,pid),t=IntPtr.Zero;
        if(p==IntPtr.Zero)return -1;
        try { if(!OpenProcessToken(p,8,out t))return -1;
            int v,n;return GetTokenInformation(t,20,out v,4,out n)?v:-1;
        } finally {if(t!=IntPtr.Zero)CloseHandle(t);CloseHandle(p);}
    }
    public static GuiInfo Focus(IntPtr h) {
        uint pid; uint thread=GetWindowThreadProcessId(h,out pid);
        var info=new GuiInfo(); info.size=Marshal.SizeOf(typeof(GuiInfo));
        if(thread!=0)GetGUIThreadInfo(thread,ref info);return info;
    }
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder b, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder b, int n);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public static string Class(IntPtr h) { var b = new StringBuilder(256); GetClassName(h,b,b.Capacity); return b.ToString(); }
    public static string Text(IntPtr h) { var b = new StringBuilder(128); GetWindowText(h,b,b.Capacity); return b.ToString(); }
    // Box this return explicitly for Windows PowerShell 5's dynamic call sites.
    public static object Process(IntPtr h) { uint pid; GetWindowThreadProcessId(h,out pid); return (int)pid; }
    public static bool OwnedDock(IntPtr h) {
        var owner = GetAncestor(h,3);
        return Class(owner)=="Photoshop" && (int)Process(owner)==(int)Process(h);
    }
}
'@
}
function Window-Info([IntPtr]$Handle) {
    if ($Handle -eq [IntPtr]::Zero) { return $null }
    $processNumber = [PhotoshopPanelReadOnly]::Process($Handle)
    $processName = 'unavailable'
    try { $processName = (Get-Process -Id $processNumber -ErrorAction Stop).ProcessName } catch {}
    return [pscustomobject]@{
        hwnd=$Handle.ToInt64(); class=[PhotoshopPanelReadOnly]::Class($Handle)
        id=[PhotoshopPanelReadOnly]::GetDlgCtrlID($Handle)
        pid=$processNumber; process=$processName
        visible=[PhotoshopPanelReadOnly]::IsWindowVisible($Handle)
        enabled=[PhotoshopPanelReadOnly]::IsWindowEnabled($Handle)
        minimized=[PhotoshopPanelReadOnly]::IsIconic($Handle)
    }
}
function Window-Chain([IntPtr]$Handle) {
    $list = New-Object 'System.Collections.Generic.List[object]'
    $visited = New-Object 'System.Collections.Generic.HashSet[long]'
    for ($depth=0; $Handle -ne [IntPtr]::Zero -and $depth -lt 32 -and $visited.Add($Handle.ToInt64()); $depth++) {
        $list.Add((Window-Info $Handle))
        # Stop at the top-level window, excluding the desktop and shell owners.
        if ([PhotoshopPanelReadOnly]::GetAncestor($Handle,2) -eq $Handle) { break }
        $Handle = [PhotoshopPanelReadOnly]::GetParent($Handle)
    }
    return $list.ToArray()
}
Write-Host "Read-only diagnostics. In $DelaySeconds seconds, click Photoshop's taskbar button, hover Layers, then press the configured menu shortcut shown in the backend. Keep Photoshop foreground until sampling ends."
if ($DelaySeconds) { Start-Sleep -Seconds $DelaySeconds }
$captures = New-Object 'System.Collections.Generic.List[object]'
for ($sample=0; $sample -lt $Samples; $sample++) {
    $foreground = [PhotoshopPanelReadOnly]::GetForegroundWindow()
    $point = New-Object PhotoshopPanelReadOnly+Point
    [void][PhotoshopPanelReadOnly]::GetCursorPos([ref]$point)
    $hover = [PhotoshopPanelReadOnly]::WindowFromPoint($point)
    $focus = [PhotoshopPanelReadOnly]::Focus($foreground)
    $foregroundInfo = Window-Info $foreground
    $captures.Add([pscustomobject]@{
        at=[DateTimeOffset]::Now.ToString('o')
        foreground=$foregroundInfo
        foreground_elevated=$(if($foregroundInfo){[PhotoshopPanelReadOnly]::Elevated($foregroundInfo.pid)}else{-1})
        foreground_root= (Window-Info ([PhotoshopPanelReadOnly]::GetAncestor($foreground,2)))
        foreground_root_owner= (Window-Info ([PhotoshopPanelReadOnly]::GetAncestor($foreground,3)))
        hover_chain=@(Window-Chain $hover)
        hover_root_owner=(Window-Info ([PhotoshopPanelReadOnly]::GetAncestor($hover,3)))
        focus_chain=@(Window-Chain $focus.focus)
        caret_present=($focus.caret -ne [IntPtr]::Zero)
        menu_active=($focus.menuOwner -ne [IntPtr]::Zero)
        caps_down=(([int][PhotoshopPanelReadOnly]::GetAsyncKeyState(20) -band 0x8000) -ne 0)
    })
    if ($sample -lt $Samples-1) { Start-Sleep -Milliseconds $IntervalMs }
}
$panelRoots = New-Object 'System.Collections.Generic.List[System.IntPtr]'
$find = [PhotoshopPanelReadOnly+Callback]{ param($h, $p)
    $class = [PhotoshopPanelReadOnly]::Class($h)
    if ([PhotoshopPanelReadOnly]::IsWindowVisible($h) -and $class -eq 'Photoshop') {
        $panelRoots.Add($h)
    } elseif ([PhotoshopPanelReadOnly]::IsWindowVisible($h) -and $class -eq 'OWL.Dock') {
        if ([PhotoshopPanelReadOnly]::OwnedDock($h)) {
            $panelRoots.Add($h)
        }
    }
    return $true
}
[void][PhotoshopPanelReadOnly]::EnumWindows($find, [IntPtr]::Zero)
# Still export evidence when the class-based workspace gate finds no PS root.
$panels = New-Object 'System.Collections.Generic.List[object]'
$seen = New-Object 'System.Collections.Generic.HashSet[long]'
foreach ($panelRoot in $panelRoots) {
    $visit = [PhotoshopPanelReadOnly+Callback]{ param($h, $p)
        if (-not [PhotoshopPanelReadOnly]::IsWindowVisible($h) -or
            [PhotoshopPanelReadOnly]::Class($h) -ne 'OWL.Palette' -or
            -not $seen.Add($h.ToInt64())) { return $true }
        $labels = New-Object 'System.Collections.Generic.List[string]'
        $controls = New-Object 'System.Collections.Generic.List[object]'
        $classes = @{}
        $children = [PhotoshopPanelReadOnly+Callback]{ param($child, $unused)
            if (-not [PhotoshopPanelReadOnly]::IsWindowVisible($child)) { return $true }
            # Ignore nested sibling palettes instead of mixing their signatures.
            $parent = [PhotoshopPanelReadOnly]::GetParent($child)
            for ($depth = 0; $parent -ne [IntPtr]::Zero -and $parent -ne $h -and $depth -lt 32; $depth++) {
                if ([PhotoshopPanelReadOnly]::Class($parent) -eq 'OWL.Palette') { return $true }
                $parent = [PhotoshopPanelReadOnly]::GetParent($parent)
            }
            $class = [PhotoshopPanelReadOnly]::Class($child)
            $classes[$class] = 1 + [int]$classes[$class]
            if ($class -in @('ComboBox','Edit','ScrollBar','PSViewC') -and $controls.Count -lt 128) {
                $controls.Add([pscustomobject]@{class=$class; id=[PhotoshopPanelReadOnly]::GetDlgCtrlID($child)})
            }
            if ($class -eq 'Static') {
                $text = [PhotoshopPanelReadOnly]::Text($child)
                # Emit only exact known labels, including localized access keys.
                # Never read Edit controls or export arbitrary Static text.
                $matchText = $text.Normalize([Text.NormalizationForm]::FormKC) -replace '[\p{Cf}\s&]', ''
                if ($text.Length -le 64 -and $matchText -match '(?i)^(Fill|Lock|Opacity|Layers|Properties|History|\u586b\u5145|\u9501\u5b9a|\u4e0d\u900f\u660e\u5ea6|\u56fe\u5c42|\u5c5e\u6027|\u5386\u53f2\u8bb0\u5f55)(\([A-Za-z]\))?:?$') {
                    $labels.Add($text)
                }
            }
            return $true
        }
        [void][PhotoshopPanelReadOnly]::EnumChildWindows($h, $children, [IntPtr]::Zero)
        $panels.Add([pscustomobject]@{ classes = $classes; labels = @($labels.ToArray()); controls = @($controls.ToArray()); floating = ([PhotoshopPanelReadOnly]::Class($panelRoot) -eq 'OWL.Dock') })
        return $true
    }
    [void][PhotoshopPanelReadOnly]::EnumChildWindows($panelRoot, $visit, [IntPtr]::Zero)
}
$processes = New-Object 'System.Collections.Generic.List[object]'
foreach ($proc in @(Get-Process -Name Photoshop,PhotoshopMenu,HotkeyHost,MenuHost -ErrorAction SilentlyContinue)) {
    $fileVersion = 'unavailable'
    try { $fileVersion = $proc.MainModule.FileVersionInfo.FileVersion } catch {}
    $processes.Add([pscustomobject]@{name=$proc.ProcessName;pid=$proc.Id;version=$fileVersion;elevated=[PhotoshopPanelReadOnly]::Elevated($proc.Id)})
}
$result = [ordered]@{ schema=2; read_only=$true; note='Snapshots are not a keyboard event log. A brief key press may occur between samples.'; processes=@($processes.ToArray()); recognized_workspace_count=$panelRoots.Count; samples=@($captures.ToArray()); panels=@($panels.ToArray()) }
try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/status" -TimeoutSec 5
    $result.backend = $status.version
    $result.bundled_uxp = $status.uxp.bundled_version
    $result.installed_uxp = $status.uxp.version
    $result.loaded_uxp = $status.photoshop.uxp_version
    $result.uxp_ready = $status.photoshop.uxp_ready
    $result.photoshop_version = $status.photoshop.photoshop_version
    $result.panel_context = $status.menu.panel_context.kind
    $result.menu = [ordered]@{ready=$status.menu.ready;visible=$status.menu.visible;native_hotkeys=$status.menu.native_hotkeys;pid=$status.menu.pid;hotkey_pid=$status.menu.hotkey_pid;panel_kind=$status.menu.panel_context.kind;panel_source=$status.menu.panel_context.source;input_focused=$status.menu.panel_context.input_focused}
    $result.trigger = $status.settings.shortcuts.toggle
    $result.busy = $status.photoshop.busy
} catch { $result.backend = 'unavailable' }
$json = $result | ConvertTo-Json -Depth 10
if (-not $OutputPath) {
    $OutputPath = Join-Path ([Environment]::GetFolderPath('Desktop')) ('ps-menu-diagnostic-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json')
}
$resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
# Preserve previous reports instead of silently overwriting them.
$stream = [IO.File]::Open($resolvedOutput,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try {
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($json)
    $stream.Write($bytes,0,$bytes.Length)
} finally { $stream.Dispose() }
Write-Host "Report saved: $resolvedOutput"
$json
