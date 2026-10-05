<#
LivePresenceAI - Gera o instalador unico "dist\Instalar-LivePresenceAI.exe" (uso da equipe, nao do usuario final).

O .exe e um pacote do IExpress (ja vem no Windows) com:
  livepresenceai.zip  sistema pronto: backend, ia, painel, database, instalar.ps1, app web compilado e APK Android
  instalador.ps1      janela do instalador
  iniciar.cmd         abre a janela com o PowerShell de 64 bits

Uso (PowerShell, na pasta do projeto):
  powershell -ExecutionPolicy Bypass -File instalador\empacotar.ps1             # usa app\build ja compilado
  powershell -ExecutionPolicy Bypass -File instalador\empacotar.ps1 -CompilarApp  # recompila o app web e o APK antes

Ficam fora do pacote: ambientes Python (.venv/venv), config\ (segredos), .git, documentos do TCC e codigo-fonte do
app Flutter (vai so o app compilado).
#>
param([switch]$CompilarApp)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dist = Join-Path $Raiz "dist"
$Pacote = Join-Path $Dist "pacote"
$Apk = "app\build\app\outputs\flutter-apk\app-release.apk"

function Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }

if ($CompilarApp) {
    Passo "Compilando o app web"
    Push-Location (Join-Path $Raiz "app")
    try {
        $env:MSYS_NO_PATHCONV = "1"
        flutter build web --base-href /app/ --no-wasm-dry-run
        if ($LASTEXITCODE -ne 0) { throw "falha no flutter build web" }
    } finally { Pop-Location }
    Passo "Compilando o APK Android"
    & (Join-Path $Raiz "app\gerar_apk.ps1")
    if ($LASTEXITCODE -ne 0) { throw "falha ao gerar o APK" }
}
foreach ($necessario in @("app\build\web\index.html", $Apk)) {
    if (-not (Test-Path (Join-Path $Raiz $necessario))) { throw "Nao encontrado: $necessario (rode com -CompilarApp)" }
}

Passo "Montando o pacote"
if (Test-Path $Pacote) { Remove-Item $Pacote -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Pacote | Out-Null

# Arquivos do Git (inclui os novos ainda nao commitados), respeitando o .gitignore
Push-Location $Raiz
try {
    $arquivos = git ls-files --cached --others --exclude-standard -- backend ia painel database instalar.ps1 PASSO_A_PASSO.md
    if ($LASTEXITCODE -ne 0) { throw "git ls-files falhou" }
} finally { Pop-Location }
$arquivos = @($arquivos | Where-Object { $_ -and $_ -notmatch "(^|/)(testes|__pycache__)/" -and (Test-Path (Join-Path $Raiz $_)) })
# Pesos do YOLOv8n (fora do Git): evita o download no primeiro uso
if (Test-Path (Join-Path $Raiz "ia\yolov8n.pt")) { $arquivos += "ia/yolov8n.pt" }
foreach ($arquivo in $arquivos) {
    $destino = Join-Path $Pacote $arquivo
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destino) | Out-Null
    Copy-Item (Join-Path $Raiz $arquivo) $destino
}
Copy-Item (Join-Path $Raiz "app\build\web") (Join-Path $Pacote "app\build\web") -Recurse
New-Item -ItemType Directory -Force -Path (Split-Path -Parent (Join-Path $Pacote $Apk)) | Out-Null
Copy-Item (Join-Path $Raiz $Apk) (Join-Path $Pacote $Apk)
Write-Host "    $($arquivos.Count) arquivos do projeto + app web + APK"

Passo "Compactando (livepresenceai.zip)"
# O IExpress falha em unidades sem nomes curtos (8.3), comum fora do C:; trabalha numa pasta temporaria no C:
$trabalho = Join-Path $env:SystemDrive "lpai_empacotar"
if (Test-Path $trabalho) { Remove-Item $trabalho -Recurse -Force }
New-Item -ItemType Directory -Force -Path $trabalho | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($Pacote, (Join-Path $trabalho "livepresenceai.zip"),
    [IO.Compression.CompressionLevel]::Optimal, $false)
Copy-Item (Join-Path $Raiz "instalador\instalador.ps1") $trabalho
Copy-Item (Join-Path $Raiz "instalador\iniciar.cmd") $trabalho

Passo "Gerando o executavel (IExpress)"
$exe = Join-Path $Dist "Instalar-LivePresenceAI.exe"
if (Test-Path $exe) { Remove-Item $exe -Force }
$exeTemporario = Join-Path $trabalho "Instalar-LivePresenceAI.exe"
$sed = Join-Path $trabalho "livepresenceai.sed"
@"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$exeTemporario
FriendlyName=Instalar o LivePresenceAI
AppLaunched=cmd /c iniciar.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="livepresenceai.zip"
FILE1="instalador.ps1"
FILE2="iniciar.cmd"
[SourceFiles]
SourceFiles0=$trabalho\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"@ | Set-Content -Path $sed -Encoding ASCII
# Caminho sem aspas: o IExpress nao as remove (por isso a pasta de trabalho nao tem espacos)
$processo = Start-Process -FilePath (Join-Path $env:SystemRoot "System32\iexpress.exe") -ArgumentList "/N", "/Q", $sed -Wait -PassThru
if ($processo.ExitCode -ne 0 -or -not (Test-Path $exeTemporario)) { throw "O IExpress nao gerou o executavel (codigo $($processo.ExitCode))" }
Move-Item $exeTemporario $exe

Remove-Item $Pacote -Recurse -Force
Remove-Item $trabalho -Recurse -Force
$tamanho = [Math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "`nPronto: $exe ($tamanho MB)" -ForegroundColor Green
Write-Host "Copie esse arquivo para o computador da instituicao e de dois cliques nele."
