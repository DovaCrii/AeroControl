# Sube la rama actual y abre su PR. La salida del push se muestra COMPLETA y se comprueba en
# el remoto: el 2026-10-05 diez commits "empujados" nunca llegaron porque `-q` y un `Select`
# escondieron un "Everything up-to-date".
param(
    [Parameter(Mandatory)][string]$Title,
    [Parameter(Mandatory)][string]$BodyFile,
    [string]$Branch
)
$ErrorActionPreference = "Stop"
Set-Location (git rev-parse --show-toplevel)
if (-not $Branch) { $Branch = (git branch --show-current) }
if (-not $Branch -or $Branch -eq "main") { throw "No se abre un PR desde main ni sin rama (rama actual: '$Branch')." }
if (-not (Test-Path $BodyFile)) { throw "No existe el cuerpo del PR: $BodyFile" }

git push -u origin $Branch
$remote = git ls-remote origin "refs/heads/$Branch"
if (-not $remote) { throw "La rama $Branch NO llegó a origin." }
"Rama en origin: $($remote.Split("`t")[0].Substring(0, 7))  $Branch"

$url = gh pr create -R DovaCrii/AeroControl --base main --head $Branch --title $Title --body-file $BodyFile
$url
$number = ($url | Select-String -Pattern '/pull/(\d+)').Matches.Groups[1].Value
if (-not $number) { throw "gh no devolvio el numero del PR." }
"PR numero: $number"
