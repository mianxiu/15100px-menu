$ErrorActionPreference = 'Stop'
$menuRoot = Split-Path -Parent $PSScriptRoot
$menuCompiler = (Get-Command g++.exe -ErrorAction Stop).Source
$menuOutput = Join-Path $menuRoot '.runtime/test-input-context.exe'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $menuOutput) | Out-Null
& $menuCompiler -std=c++17 -O2 -Wall -Wextra -static "$menuRoot/tools/test-input-context.cpp" -o $menuOutput -luser32 -limm32 -lole32 -loleaut32 -luuid
if ($LASTEXITCODE -ne 0) { throw 'Input context fixture build failed.' }
& $menuOutput
if ($LASTEXITCODE -ne 0) { throw 'Input context fixture failed.' }
