# Gera o build do frontend e copia para backend/frontend_dist, de onde o Django o serve
# em produção (mesma origem da API). Rode na raiz do repositório antes de publicar.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

npm --prefix "$raiz\frontend" ci
if ($LASTEXITCODE -ne 0) { throw "npm ci falhou" }
npm --prefix "$raiz\frontend" run build
if ($LASTEXITCODE -ne 0) { throw "build do frontend falhou" }

$destino = "$raiz\backend\frontend_dist"
if (Test-Path $destino) { Remove-Item -Recurse -Force $destino }
Copy-Item -Recurse "$raiz\frontend\dist" $destino
Write-Host "Frontend copiado para $destino"
