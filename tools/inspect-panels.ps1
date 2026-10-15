# Read-only, standalone diagnostics for PCs without Python. No input, UXP
# requests, document reads, credentials, clipboard writes or settings changes.
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
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder b, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder b, int n);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    public static string Class(IntPtr h) { var b = new StringBuilder(256); GetClassName(h,b,b.Capacity); return b.ToString(); }
    public static string Text(IntPtr h) { var b = new StringBuilder(128); GetWindowText(h,b,b.Capacity); return b.ToString(); }
    public static uint Process(IntPtr h) { uint pid; GetWindowThreadProcessId(h,out pid); return pid; }
    public static bool OwnedDock(IntPtr h) {
        var owner = GetAncestor(h,3);
        return Class(owner)=="Photoshop" && Process(owner)==Process(h);
    }
}
'@
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
if (-not $panelRoots.Count) { throw 'No visible Photoshop workspace found.' }
$panels = New-Object 'System.Collections.Generic.List[object]'
$seen = New-Object 'System.Collections.Generic.HashSet[long]'
foreach ($panelRoot in $panelRoots) {
    $visit = [PhotoshopPanelReadOnly+Callback]{ param($h, $p)
        if (-not [PhotoshopPanelReadOnly]::IsWindowVisible($h) -or
            [PhotoshopPanelReadOnly]::Class($h) -ne 'OWL.Palette' -or
            -not $seen.Add($h.ToInt64())) { return $true }
        $labels = New-Object 'System.Collections.Generic.List[string]'
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
        $panels.Add([pscustomobject]@{ classes = $classes; labels = @($labels.ToArray()); floating = ([PhotoshopPanelReadOnly]::Class($panelRoot) -eq 'OWL.Dock') })
        return $true
    }
    [void][PhotoshopPanelReadOnly]::EnumChildWindows($panelRoot, $visit, [IntPtr]::Zero)
}
$result = [ordered]@{ read_only = $true; panels = @($panels.ToArray()) }
try {
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:15151/api/status' -TimeoutSec 5
    $result.backend = $status.version
    $result.bundled_uxp = $status.uxp.bundled_version
    $result.installed_uxp = $status.uxp.version
    $result.loaded_uxp = $status.photoshop.uxp_version
    $result.uxp_ready = $status.photoshop.uxp_ready
    $result.photoshop_version = $status.photoshop.photoshop_version
    $result.panel_context = $status.menu.panel_context.kind
} catch { $result.backend = 'unavailable' }
$result | ConvertTo-Json -Depth 6
