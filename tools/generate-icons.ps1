# Generate native icons from the same colors and lettering as public/icon.svg.
param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$menuIconDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) 'frontend\public'
$menuSizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256)
$menuPngEntries = @()
foreach ($menuSize in $menuSizes) {
    $menuBitmap = New-Object System.Drawing.Bitmap 1024, 1024
    $menuGraphics = [System.Drawing.Graphics]::FromImage($menuBitmap)
    $menuPath = New-Object System.Drawing.Drawing2D.GraphicsPath
    $menuBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#172a41'))
    $menuTextBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#75bdff'))
    $menuFont = New-Object System.Drawing.Font 'Segoe UI', 550, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $menuFormat = New-Object System.Drawing.StringFormat
    try {
        $menuGraphics.Clear([System.Drawing.Color]::Transparent)
        $menuGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $menuGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
        $menuRadius = 224
        $menuPath.AddArc(0, 0, $menuRadius*2, $menuRadius*2, 180, 90)
        $menuPath.AddArc(1024-$menuRadius*2, 0, $menuRadius*2, $menuRadius*2, 270, 90)
        $menuPath.AddArc(1024-$menuRadius*2, 1024-$menuRadius*2, $menuRadius*2, $menuRadius*2, 0, 90)
        $menuPath.AddArc(0, 1024-$menuRadius*2, $menuRadius*2, $menuRadius*2, 90, 90)
        $menuPath.CloseFigure()
        $menuGraphics.FillPath($menuBrush, $menuPath)
        $menuFormat.Alignment = [System.Drawing.StringAlignment]::Center
        $menuFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
        $menuGraphics.DrawString('Ps', $menuFont, $menuTextBrush, ([System.Drawing.RectangleF]::new(0, -10, 1024, 1024)), $menuFormat)
        $menuOutput = New-Object System.Drawing.Bitmap $menuSize, $menuSize
        $menuOutputGraphics = [System.Drawing.Graphics]::FromImage($menuOutput)
        $menuStream = New-Object System.IO.MemoryStream
        try {
            $menuOutputGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $menuOutputGraphics.DrawImage($menuBitmap, 0, 0, $menuSize, $menuSize)
            $menuOutput.Save($menuStream, [System.Drawing.Imaging.ImageFormat]::Png)
            $menuPngEntries += ,($menuStream.ToArray())
            if ($menuSize -eq 256) { [System.IO.File]::WriteAllBytes((Join-Path $menuIconDirectory 'icon.png'), $menuStream.ToArray()) }
        } finally {
            $menuStream.Dispose(); $menuOutputGraphics.Dispose(); $menuOutput.Dispose()
        }
    } finally {
        $menuFormat.Dispose(); $menuFont.Dispose(); $menuTextBrush.Dispose(); $menuBrush.Dispose()
        $menuPath.Dispose(); $menuGraphics.Dispose(); $menuBitmap.Dispose()
    }
}
$menuIcoStream = New-Object System.IO.MemoryStream
$menuWriter = New-Object System.IO.BinaryWriter $menuIcoStream
try {
    $menuWriter.Write([uint16]0); $menuWriter.Write([uint16]1); $menuWriter.Write([uint16]$menuSizes.Count)
    $menuOffset = 6 + 16*$menuSizes.Count
    for ($menuIndex = 0; $menuIndex -lt $menuSizes.Count; $menuIndex++) {
        $menuDimension = $menuSizes[$menuIndex] % 256
        $menuWriter.Write([byte]$menuDimension); $menuWriter.Write([byte]$menuDimension)
        $menuWriter.Write([byte]0); $menuWriter.Write([byte]0)
        $menuWriter.Write([uint16]1); $menuWriter.Write([uint16]32)
        $menuWriter.Write([uint32]$menuPngEntries[$menuIndex].Length); $menuWriter.Write([uint32]$menuOffset)
        $menuOffset += $menuPngEntries[$menuIndex].Length
    }
    foreach ($menuPng in $menuPngEntries) { $menuWriter.Write([byte[]]$menuPng) }
    $menuWriter.Flush()
    [System.IO.File]::WriteAllBytes((Join-Path $menuIconDirectory 'icon.ico'), $menuIcoStream.ToArray())
} finally {
    $menuWriter.Dispose(); $menuIcoStream.Dispose()
}
Write-Output 'Generated icon.ico (9 sizes) and icon.png.'
