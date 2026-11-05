$ErrorActionPreference = 'Stop'
$menuRoot = Split-Path -Parent $PSScriptRoot
$menuCompiler = (Get-Command g++.exe -ErrorAction Stop).Source
& $menuCompiler -std=c++17 -O2 -Wall -Wextra -shared -static "$menuRoot\native\InputService.cpp" -o "$menuRoot\native\InputService.dll" -lole32 -luuid
if ($LASTEXITCODE -ne 0) { throw 'Input service build failed.' }
