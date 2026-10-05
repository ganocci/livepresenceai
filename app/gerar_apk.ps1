<#
LivePresenceAI - Gera o APK do app do professor (Android).

Requisitos: Flutter, JDK 17 e Android SDK (plataforma 36, build-tools 36, NDK 28.2) em C:\Android\Sdk.
Ferramentas do Android (Gradle, CMake/ninja do NDK) falham com acentos no caminho (ex.: C:\Users\Joao com
til); por isso este script usa, so durante a compilacao, pastas sem acento em C:\Android para o cache do
Gradle, o cache de pacotes do Flutter e os arquivos temporarios do Java. Nada e alterado de forma permanente.

Uso (na pasta app):  powershell -ExecutionPolicy Bypass -File gerar_apk.ps1
Saida: build\app\outputs\flutter-apk\app-release.apk
#>
param([string]$Base = "C:\Android", [string]$JavaHome = $env:JAVA_HOME)

$ErrorActionPreference = "Stop"
if (-not $JavaHome) { $JavaHome = "C:\Java\jdk-17" }
foreach ($pasta in @("tmp", "gradle", "pub-cache")) { New-Item -ItemType Directory -Force (Join-Path $Base $pasta) | Out-Null }

$env:JAVA_HOME = $JavaHome
$env:ANDROID_HOME = Join-Path $Base "Sdk"
$env:GRADLE_USER_HOME = Join-Path $Base "gradle"
$env:PUB_CACHE = Join-Path $Base "pub-cache"
$env:TEMP = Join-Path $Base "tmp"
$env:TMP = $env:TEMP
# O Java cria um socket interno na pasta temporaria; com acento no caminho, falha ("loopback connection")
$env:JAVA_TOOL_OPTIONS = "-Djdk.net.unixdomain.tmpdir=$($env:TEMP) -Djava.io.tmpdir=$($env:TEMP)"

Set-Location $PSScriptRoot
flutter pub get
flutter build apk --release
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o APK" }
$apk = Join-Path $PSScriptRoot "build\app\outputs\flutter-apk\app-release.apk"
Write-Host "`nAPK gerado: $apk ($([math]::Round((Get-Item $apk).Length / 1MB, 1)) MB)" -ForegroundColor Green
