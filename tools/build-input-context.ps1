$ErrorActionPreference = 'Stop'
$menuRoot = Split-Path -Parent $PSScriptRoot
$menuCompiler = (Get-Command g++.exe -ErrorAction Stop).Source
& $menuCompiler -std=c++17 -O2 -Wall -Wextra -shared -static "$menuRoot\native\InputContext.cpp" -o "$menuRoot\native\InputContext.dll" -luser32 -limm32 -lole32 -loleaut32 -luuid
if ($LASTEXITCODE -ne 0) { throw 'Native input context build failed.' }
