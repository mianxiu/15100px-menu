# Editable hand-stroke PS + MENU identity, based on the user supplied EXE icon.
param()
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$menuRoot=Split-Path -Parent $PSScriptRoot
$menuIconDirectory=Join-Path $menuRoot 'frontend/public'
$menuDesign=Get-Content -LiteralPath (Join-Path $menuRoot 'native/app-icon-design.json') -Raw -Encoding utf8 | ConvertFrom-Json
$menuSizes=@(16,20,24,32,40,48,64,128,256)
$menuPngEntries=@()
function New-MenuPath([string]$data){
 $path=[System.Drawing.Drawing2D.GraphicsPath]::new([System.Drawing.Drawing2D.FillMode]::Alternate)
 $tokens=[regex]::Matches($data,'[MLCZ]|-?\d+(?:\.\d+)?') | ForEach-Object {$_.Value}
 $i=0;$x=0.0;$y=0.0
 while($i -lt $tokens.Count){
  $command=$tokens[$i++];$count=if($command -eq 'C'){6}elseif($command -eq 'Z'){0}else{2}
  $v=@();for($n=0;$n -lt $count;$n++){$v+=[float]::Parse($tokens[$i++],[System.Globalization.CultureInfo]::InvariantCulture)}
  switch($command){
   'M' {$path.StartFigure();$x=$v[0];$y=$v[1]}
   'L' {$path.AddLine([float]$x,[float]$y,$v[0],$v[1]);$x=$v[0];$y=$v[1]}
   'C' {$path.AddBezier([float]$x,[float]$y,$v[0],$v[1],$v[2],$v[3],$v[4],$v[5]);$x=$v[4];$y=$v[5]}
   'Z' {$path.CloseFigure()}
   default {throw 'Unsupported vector command'}
  }
 };return ,$path
}
$menuBitmap=[System.Drawing.Bitmap]::new(1024,1024)
$menuGraphics=[System.Drawing.Graphics]::FromImage($menuBitmap)
$menuBackground=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($menuDesign.background))
$menuInk=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($menuDesign.foreground))
$menuOutline=New-MenuPath $menuDesign.ps_outline
$menuBase=[System.Drawing.Drawing2D.GraphicsPath]::new();$menuRadius=[float]$menuDesign.radius;$menuDiameter=2*$menuRadius
foreach($arc in @(@(0,0,180),@((128-$menuDiameter),0,270),@((128-$menuDiameter),(128-$menuDiameter),0),@(0,(128-$menuDiameter),90))){$menuBase.AddArc([float]$arc[0],[float]$arc[1],$menuDiameter,$menuDiameter,[float]$arc[2],90)}
$menuBase.CloseFigure()
try {
 $menuGraphics.Clear([System.Drawing.Color]::Transparent);$menuGraphics.SmoothingMode=[System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
 $menuGraphics.ScaleTransform(8,8);$menuGraphics.FillPath($menuBackground,$menuBase);$menuGraphics.FillPath($menuInk,$menuOutline)
 $menuSvg='<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128" role="img" aria-label="Photoshop Menu">' + "`n"
 $menuSvg+='<rect width="128" height="128" rx="'+$menuDesign.radius+'" fill="'+$menuDesign.background+'"/>' + "`n"
 $menuSvg+='<path d="'+$menuDesign.ps_outline+'" fill="'+$menuDesign.foreground+'" fill-rule="evenodd"/>' + "`n"
 foreach($stroke in $menuDesign.strokes){
  $path=New-MenuPath $stroke.path;$pen=[System.Drawing.Pen]::new($menuInk,[float]$stroke.width)
  try {$pen.StartCap=$pen.EndCap=[System.Drawing.Drawing2D.LineCap]::Round;$pen.LineJoin=[System.Drawing.Drawing2D.LineJoin]::Round;$menuGraphics.DrawPath($pen,$path)}finally{$path.Dispose();$pen.Dispose()}
  $menuSvg+='<path d="'+$stroke.path+'" fill="none" stroke="'+$menuDesign.foreground+'" stroke-width="'+$stroke.width+'" stroke-linecap="round" stroke-linejoin="round"/>' + "`n"
 }
 $menuSvg+='</svg>' + "`n"
 [System.IO.File]::WriteAllText((Join-Path $menuIconDirectory 'icon.svg'),$menuSvg,[System.Text.UTF8Encoding]::new($false))
 foreach($menuSize in $menuSizes){
  $output=[System.Drawing.Bitmap]::new($menuSize,$menuSize);$graphics=[System.Drawing.Graphics]::FromImage($output);$stream=[System.IO.MemoryStream]::new()
  try {
   $graphics.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic;$graphics.DrawImage($menuBitmap,0,0,$menuSize,$menuSize)
   $output.Save($stream,[System.Drawing.Imaging.ImageFormat]::Png);$menuPngEntries+=,($stream.ToArray())
   if($menuSize -eq 256){[System.IO.File]::WriteAllBytes((Join-Path $menuIconDirectory 'icon.png'),$stream.ToArray())}
  }finally{$stream.Dispose();$graphics.Dispose();$output.Dispose()}
 }
}finally{$menuGraphics.Dispose();$menuBitmap.Dispose();$menuBackground.Dispose();$menuInk.Dispose();$menuBase.Dispose();$menuOutline.Dispose()}
$menuStream=[System.IO.MemoryStream]::new();$menuWriter=[System.IO.BinaryWriter]::new($menuStream)
try {
 $menuWriter.Write([uint16]0);$menuWriter.Write([uint16]1);$menuWriter.Write([uint16]$menuSizes.Count);$offset=6+16*$menuSizes.Count
 for($i=0;$i -lt $menuSizes.Count;$i++){
  $dimension=$menuSizes[$i]%256;$menuWriter.Write([byte]$dimension);$menuWriter.Write([byte]$dimension);$menuWriter.Write([byte]0);$menuWriter.Write([byte]0)
  $menuWriter.Write([uint16]1);$menuWriter.Write([uint16]32);$menuWriter.Write([uint32]$menuPngEntries[$i].Length);$menuWriter.Write([uint32]$offset);$offset+=$menuPngEntries[$i].Length
 }
 foreach($png in $menuPngEntries){$menuWriter.Write([byte[]]$png)};$menuWriter.Flush()
 [System.IO.File]::WriteAllBytes((Join-Path $menuIconDirectory 'icon.ico'),$menuStream.ToArray())
}finally{$menuWriter.Dispose();$menuStream.Dispose()}
Write-Output 'Generated reference-style PS / MENU SVG, PNG and ICO (9 sizes).'
