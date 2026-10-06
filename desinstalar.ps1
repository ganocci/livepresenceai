<#
LivePresenceAI - Desinstalador (Configuracoes do Windows > Aplicativos > LivePresenceAI > Desinstalar).

Remove atalhos, regras do firewall, o registro em "Aplicativos instalados" e os arquivos do sistema.
Por padrao MANTEM os dados: o banco de dados (turmas, alunos e historico de chamadas) e a pasta config\ (com
as copias de seguranca e a senha do banco), para uma reinstalacao continuar de onde parou. Apagar o banco
exige confirmacao explicita. Python e PostgreSQL ficam instalados (podem servir a outros programas).

Teste sem alterar nada:  powershell -ExecutionPolicy Bypass -File desinstalar.ps1 -Simular
#>
param([string]$Pasta = "", [switch]$Simular, [switch]$Copia, [switch]$SimularApagandoDados)

$ErrorActionPreference = "Stop"
if (-not $Pasta) { $Pasta = Split-Path -Parent $MyInvocation.MyCommand.Path }
$Pasta = $Pasta.TrimEnd("\")
$PowerShell64 = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
Add-Type -AssemblyName System.Windows.Forms

function Mensagem($texto, $botoes = "OK", $icone = "Information", $padrao = "Button1") {
    [System.Windows.Forms.MessageBox]::Show($texto, "Desinstalar o LivePresenceAI", $botoes, $icone, $padrao)
}
function Acao($descricao, [scriptblock]$bloco) {
    if ($Simular) { Write-Host "[simulacao] $descricao"; return }
    try { & $bloco } catch { Write-Host "aviso ($descricao): $($_.Exception.Message)" }
}

# Administrador (atalhos de todos os usuarios, firewall e registro do Windows)
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $Simular) {
    try {
        Start-Process $PowerShell64 -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Pasta `"$Pasta`""
    } catch { [void](Mensagem "A desinstalação precisa da permissão de administrador." "OK" "Warning") }
    exit
}
# Roda de uma copia fora da pasta, para poder apagar a pasta inteira
if (-not $Copia -and -not $Simular) {
    $temporario = Join-Path $env:TEMP "desinstalar_livepresenceai.ps1"
    Copy-Item $PSCommandPath $temporario -Force
    Start-Process $PowerShell64 -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$temporario`" -Pasta `"$Pasta`" -Copia"
    exit
}

if ($Simular) {
    # Simulacao: sem janelas de confirmacao; -SimularApagandoDados simula a escolha de apagar os dados
    $apagarDados = [bool]$SimularApagandoDados
} else {
if ((Mensagem "Desinstalar o LivePresenceAI deste computador?`n`nPasta: $Pasta" "YesNo" "Question" "Button2") -ne "Yes") { exit }
$apagarDados = (Mensagem ("Apagar também os DADOS (turmas, alunos, cadastros faciais e todo o histórico de chamadas)?`n`n" +
    "Escolha Não para manter os dados e as cópias de segurança: uma reinstalação continua de onde parou.`n`n" +
    "Esta ação não pode ser desfeita.") "YesNo" "Warning" "Button2") -eq "Yes"
if ($apagarDados) {
    $apagarDados = (Mensagem "Confirma apagar DEFINITIVAMENTE todos os dados do LivePresenceAI?" "YesNo" "Warning" "Button2") -eq "Yes"
}
}

# 1. Encerra o painel, o servidor e o modulo da sala desta instalacao
Acao "encerrar os processos da pasta" {
    Get-CimInstance Win32_Process | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith("$Pasta\", [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine.IndexOf($Pasta, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
         $_.ProcessId -ne $PID -and $_.Name -match "python")
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# 2. Banco de dados (somente com a confirmacao dupla acima)
if ($apagarDados) {
    Acao "apagar o banco de dados livepresenceai" {
        $config = Get-Content (Join-Path $Pasta "config\livepresenceai.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        $url = [Uri]($config.servidor.database_url -replace "^postgresql\+psycopg2://", "postgresql://")
        $usuario, $senha = $url.UserInfo.Split(":", 2)
        $banco = $url.AbsolutePath.TrimStart("/")
        $psql = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" | Sort-Object FullName -Descending | Select-Object -First 1
        $env:PGPASSWORD = [Uri]::UnescapeDataString($senha)
        & $psql.FullName -w -h $url.Host -p $url.Port -U $usuario -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $banco" | Out-Null
        Remove-Item Env:\PGPASSWORD
        if ($LASTEXITCODE -ne 0) { throw "o PostgreSQL recusou apagar o banco $banco" }
    }
}

# 3. Atalhos, inicio automatico, firewall e registro em "Aplicativos instalados"
Acao "remover atalhos" {
    foreach ($local in @("CommonDesktopDirectory", "CommonPrograms", "Desktop", "Programs", "Startup")) {
        $atalho = Join-Path ([Environment]::GetFolderPath($local)) "LivePresenceAI.lnk"
        if (Test-Path $atalho) { Remove-Item $atalho -Force }
    }
}
Acao "remover as regras do firewall" {
    Get-NetFirewallRule -DisplayName "LivePresenceAI*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
Acao "remover de Aplicativos instalados" {
    Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\LivePresenceAI" -Recurse -ErrorAction SilentlyContinue
}

# 4. Arquivos (a pasta config\ fica quando os dados sao mantidos)
Acao "apagar os arquivos" {
    Get-ChildItem $Pasta -Force | Where-Object { $apagarDados -or $_.Name -ne "config" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    if ($apagarDados) { Remove-Item $Pasta -Recurse -Force -ErrorAction SilentlyContinue }
}

if ($Simular) { Write-Host "Simulacao concluida (apagar dados: $apagarDados)."; exit }
$restou = @(Get-ChildItem $Pasta -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $apagarDados -or $_.FullName -notlike "$Pasta\config*" })
$final = if ($apagarDados) { "O LivePresenceAI e todos os seus dados foram removidos." }
         else { "O LivePresenceAI foi removido. Os dados e as cópias de segurança continuam em $Pasta\config." }
if ($restou.Count) { $final += "`n`nAlguns arquivos estavam em uso e não foram apagados; apague a pasta $Pasta depois de reiniciar o computador." }
[void](Mensagem ($final + "`n`nO Python e o PostgreSQL continuam instalados; podem ser removidos em Configurações > Aplicativos, se nenhum outro programa os usar."))
Remove-Item $PSCommandPath -Force -ErrorAction SilentlyContinue
