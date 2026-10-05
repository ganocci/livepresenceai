<#
LivePresenceAI - Instalador para Windows

Prepara este computador como SERVIDOR (banco + API + app web), como computador de SALA (camera + reconhecimento)
ou os dois (padrao, para um unico computador). Ao final cria o atalho "LivePresenceAI" na area de trabalho, que
abre o painel para ligar e desligar tudo.

Para o usuario final, o caminho normal e o "Instalar-LivePresenceAI.exe" (gerado por instalador\empacotar.ps1),
que abre uma janela e chama este script sem perguntas. Ele tambem pode ser usado direto:

  powershell -ExecutionPolicy Bypass -File instalar.ps1                  # servidor + sala neste computador
  powershell -ExecutionPolicy Bypass -File instalar.ps1 -Papel Servidor  # so o servidor
  powershell -ExecutionPolicy Bypass -File instalar.ps1 -Papel Sala      # so a sala (procura o servidor na rede)
  ... -Simular                                                           # mostra o que faria, sem alterar nada

Opcoes: -PortaBanco 5432  -Porta 8443  -SemAtalho  -PularBanco (usa um banco ja configurado: informe -DatabaseUrl)

Sem perguntas (usado pela janela do instalador), por variaveis de ambiente:
  LIVEPRESENCEAI_SENHA_POSTGRES  senha do usuario 'postgres' quando o PostgreSQL ja existia neste computador
  LIVEPRESENCEAI_CHAVE_SALA      chave do modulo de IA (computador so de sala)
  LIVEPRESENCEAI_SERVIDOR_URL    endereco do servidor, se a busca na rede nao o encontrar (computador so de sala)
  LIVEPRESENCEAI_SEM_PERGUNTAS=1 falha com mensagem clara em vez de perguntar no console
#>
param(
    [ValidateSet("Completo", "Servidor", "Sala")] [string]$Papel = "Completo",
    [int]$PortaBanco = 5432,
    [int]$Porta = 8443,
    [string]$DatabaseUrl = "",
    [switch]$PularBanco,
    [switch]$SemAtalho,
    [switch]$Simular
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$Servidor = $Papel -ne "Sala"
$Sala = $Papel -ne "Servidor"
$SemPerguntas = $env:LIVEPRESENCEAI_SEM_PERGUNTAS -eq "1"
$PortaDescoberta = 47800

function Passo($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    ok: $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "    atencao: $texto" -ForegroundColor Yellow }
function Executar($descricao, [scriptblock]$acao) {
    if ($Simular) { Write-Host "    [simulacao] $descricao" -ForegroundColor DarkGray; return }
    & $acao
}
function SenhaAleatoria { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ }) }
function Perguntar($texto, $variavel, [switch]$Secreta) {
    $valor = [Environment]::GetEnvironmentVariable($variavel)
    if ($valor) { return $valor }
    if ($SemPerguntas) { throw "Informacao necessaria nao fornecida: $texto" }
    if ($Secreta) {
        $segura = Read-Host $texto -AsSecureString
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))
    }
    return Read-Host $texto
}
$Admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host "LivePresenceAI - instalacao ($Papel) em $Raiz" -ForegroundColor White
if ($Simular) { Aviso "modo simulacao: nada sera alterado" }

# ---------------------------------------------------------------- Python
# Procura pelo caminho (e nao so pelo PATH) para funcionar logo apos o winget, sem reabrir o PowerShell
function Silencioso([scriptblock]$acao) {
    # No Windows PowerShell 5.1, stderr de programa externo vira erro fatal com ErrorActionPreference=Stop
    $anterior = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $acao } catch { $null } finally { $ErrorActionPreference = $anterior }
}
function VersaoPython($exe, [string[]]$pre) {
    $v = Silencioso { & $exe @pre -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null }
    $numero = 0
    [void][int]::TryParse("$($v | Select-Object -Last 1)".Trim(), [ref]$numero)
    return $numero
}
function EncontrarPython {
    $candidatos = New-Object System.Collections.ArrayList
    foreach ($padrao in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe")) {
        foreach ($f in (Get-ChildItem $padrao -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) {
            [void]$candidatos.Add([pscustomobject]@{ Exe = $f.FullName; Pre = [string[]]@() })
        }
    }
    foreach ($exe in @("py.exe", "$env:SystemRoot\py.exe", "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe")) {
        $c = Get-Command $exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { [void]$candidatos.Add([pscustomobject]@{ Exe = $c.Source; Pre = [string[]]@("-3") }) }
    }
    $c = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c -and $c.Source -notlike "*WindowsApps*") { [void]$candidatos.Add([pscustomobject]@{ Exe = $c.Source; Pre = [string[]]@() }) }
    foreach ($candidato in $candidatos) {
        if ((VersaoPython $candidato.Exe $candidato.Pre) -ge 312) { return $candidato }
    }
    return $null
}

Passo "Python 3.12 ou mais novo"
$py = EncontrarPython
if (-not $py) {
    Aviso "Python nao encontrado; instalando (pode levar alguns minutos)."
    Executar "winget install Python.Python.3.14" {
        winget install --id Python.Python.3.14 -e --silent --accept-source-agreements --accept-package-agreements
        $script:py = EncontrarPython
        if (-not $script:py) { throw "O Python foi instalado mas nao foi encontrado. Reinicie o computador e rode o instalador de novo." }
    }
}
if ($py) { $PythonExe = $py.Exe; $PythonPre = $py.Pre; Ok "usando $PythonExe $PythonPre" }

# ---------------------------------------------------------------- PostgreSQL e banco
function EncontrarPsql {
    Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name -replace "\D", "") } -Descending | Select-Object -First 1
}
function ConfigAtual {
    $arquivo = Join-Path $Raiz "config\livepresenceai.json"
    if (Test-Path $arquivo) { return Get-Content $arquivo -Raw -Encoding UTF8 | ConvertFrom-Json }
    return $null
}

if ($Servidor -and -not $PularBanco) {
    Passo "PostgreSQL"
    $psql = EncontrarPsql
    $senhaPostgres = $null
    if (-not $psql) {
        # Instalacao silenciosa: a senha do administrador do PostgreSQL e gerada aqui e usada so nesta etapa
        Aviso "PostgreSQL nao encontrado; instalando sem perguntas (pode levar alguns minutos)."
        $senhaPostgres = SenhaAleatoria
        Executar "winget install PostgreSQL.PostgreSQL.17 (modo silencioso, porta $PortaBanco)" {
            $opcoes = "--mode unattended --unattendedmodeui none --superpassword $senhaPostgres --serverport $PortaBanco --disable-components stackbuilder"
            winget install --id PostgreSQL.PostgreSQL.17 -e --silent --accept-source-agreements --accept-package-agreements --override $opcoes
            $script:psql = EncontrarPsql
            if (-not $script:psql) { throw "A instalacao do PostgreSQL nao terminou. Verifique a conexao com a internet e tente de novo." }
            Ok $script:psql.FullName
        }
    } else { Ok $psql.FullName }

    Passo "Banco de dados 'livepresenceai' (porta $PortaBanco)"
    # Reinstalacao: se o banco da configuracao atual ja conecta, mantem (nao pede senha nem troca nada)
    $atual = ConfigAtual
    $reaproveitar = $false
    if ($atual -and $psql -and -not $Simular) {
        $url = $atual.servidor.database_url -replace "^postgresql\+psycopg2://", "postgresql://"
        $teste = Silencioso { & $psql.FullName -w -d $url -tAc "SELECT 1" 2>$null }
        $reaproveitar = ("$teste".Trim() -eq "1")
    }
    if ($reaproveitar) {
        $DatabaseUrl = $atual.servidor.database_url
        Ok "banco da instalacao anterior encontrado e mantido"
    } else {
        $senhaBanco = SenhaAleatoria
        $DatabaseUrl = "postgresql+psycopg2://livepresenceai:$senhaBanco@localhost:$PortaBanco/livepresenceai"
        Executar "criar/atualizar o usuario livepresenceai e o banco livepresenceai" {
            if (-not $senhaPostgres) {
                $senhaPostgres = Perguntar "Senha do usuario 'postgres' (administrador do PostgreSQL ja instalado)" "LIVEPRESENCEAI_SENHA_POSTGRES" -Secreta
            }
            $env:PGPASSWORD = $senhaPostgres
            try {
                $sql = "DO `$`$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='livepresenceai') THEN " +
                       "CREATE ROLE livepresenceai LOGIN PASSWORD '$senhaBanco'; ELSE ALTER ROLE livepresenceai PASSWORD '$senhaBanco'; END IF; END`$`$;"
                & $psql.FullName -w -U postgres -h localhost -p $PortaBanco -v ON_ERROR_STOP=1 -c $sql | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel entrar no PostgreSQL (senha do usuario 'postgres' ou porta $PortaBanco incorreta)." }
                $existe = & $psql.FullName -w -U postgres -h localhost -p $PortaBanco -tAc "SELECT 1 FROM pg_database WHERE datname='livepresenceai'"
                if ("$existe".Trim() -ne "1") {
                    & $psql.FullName -w -U postgres -h localhost -p $PortaBanco -v ON_ERROR_STOP=1 -c "CREATE DATABASE livepresenceai OWNER livepresenceai" | Out-Null
                    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel criar o banco livepresenceai." }
                }
            } finally { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
            Ok "usuario e banco prontos (senha aleatoria guardada em config\livepresenceai.json)"
        }
    }
} elseif ($Servidor) {
    if (-not $DatabaseUrl) { throw "Com -PularBanco, informe -DatabaseUrl" }
    Ok "usando o banco informado"
}

# ---------------------------------------------------------------- ambientes Python
function PrepararAmbiente($pasta, $descricao) {
    Passo "Ambiente do $descricao ($pasta)"
    Executar "criar $pasta\.venv e instalar $pasta\requirements.txt" {
        $venv = Join-Path $Raiz "$pasta\.venv"
        if (-not (Test-Path "$venv\Scripts\python.exe")) {
            & $PythonExe @PythonPre -m venv $venv
            if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente Python de $pasta" }
        }
        & "$venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
        & "$venv\Scripts\python.exe" -m pip install -r (Join-Path $Raiz "$pasta\requirements.txt") --quiet --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependencias de $pasta (confira a conexao com a internet)" }
        Ok "pronto"
    }
}
# O painel roda com o Python do servidor; no computador so de sala, o backend tambem e preparado (leve)
PrepararAmbiente "backend" "servidor e do painel"
if ($Sala) { PrepararAmbiente "ia" "modulo de IA (inclui PyTorch; pode demorar)" }
$pyBackend = if (Test-Path "$Raiz\backend\.venv\Scripts\python.exe") { "$Raiz\backend\.venv\Scripts\python.exe" } else { "$Raiz\backend\venv\Scripts\python.exe" }

# ---------------------------------------------------------------- servidor (computador so de sala)
$servidorUrl = "https://localhost:$Porta"
$certificadoServidor = ""
$chaveSala = ""
if (-not $Servidor) {
    Passo "Procurando o servidor do LivePresenceAI na rede"
    Executar "procurar o servidor (UDP $PortaDescoberta)" {
        $achados = @(& $pyBackend (Join-Path $Raiz "backend\descoberta.py") | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
        if ($achados.Count -ge 1) {
            $script:servidorUrl = $achados[0].url
            $script:certificadoServidor = "$($achados[0].certificado_sha256)"
            if ($achados.Count -gt 1) { Aviso "mais de um servidor na rede; usando $($achados[0].nome). Troque no painel se preciso." }
            Ok "encontrado: $($achados[0].nome) ($($achados[0].url))"
        } else {
            Aviso "nenhum servidor respondeu (o servidor esta ligado? este computador esta na mesma rede?)"
            $script:servidorUrl = Perguntar "Endereco do servidor (ex.: https://192.168.0.10:$Porta)" "LIVEPRESENCEAI_SERVIDOR_URL"
        }
    }
    $chaveSala = Perguntar "Chave do modulo de IA (aparece no painel do servidor)" "LIVEPRESENCEAI_CHAVE_SALA"
}

# ---------------------------------------------------------------- configuracao e certificado
Passo "Configuracao (config\livepresenceai.json)"
# Valores por variaveis de ambiente: o pipe do PowerShell 5.1 para programas externos estraga acentos no caminho
$script = @"
import os, sys
sys.path.insert(0, os.path.join(os.environ['LPAI_RAIZ'], 'painel'))
import configuracao as cfg
c = cfg.carregar()
c['servidor']['ativo'] = os.environ['LPAI_SERVIDOR'] == '1'
c['servidor']['porta'] = int(os.environ['LPAI_PORTA'])
if os.environ.get('LPAI_BANCO'): c['servidor']['database_url'] = os.environ['LPAI_BANCO']
c['sala']['ativo'] = os.environ['LPAI_SALA'] == '1'
c['sala']['servidor_url'] = os.environ['LPAI_SERVIDOR_URL']
c['sala']['certificado_sha256'] = os.environ.get('LPAI_CERTIFICADO') or None
if os.environ.get('LPAI_CHAVE'): c['sala']['chave_modulo_ia'] = os.environ['LPAI_CHAVE']
cfg.salvar(c)
print('configuracao salva em', cfg.ARQUIVO)
"@
Executar "gravar a configuracao (segredos aleatorios na primeira vez; mantidos nas reinstalacoes)" {
    $env:LPAI_RAIZ = $Raiz; $env:LPAI_SERVIDOR = $(if ($Servidor) { "1" } else { "0" }); $env:LPAI_PORTA = "$Porta"
    $env:LPAI_BANCO = $DatabaseUrl; $env:LPAI_SALA = $(if ($Sala) { "1" } else { "0" }); $env:LPAI_SERVIDOR_URL = $servidorUrl
    $env:LPAI_CERTIFICADO = $certificadoServidor; $env:LPAI_CHAVE = $chaveSala
    $script | & $pyBackend -
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gravar a configuracao" }
    foreach ($nome in "RAIZ", "SERVIDOR", "PORTA", "BANCO", "SALA", "SERVIDOR_URL", "CERTIFICADO", "CHAVE") {
        Remove-Item "Env:\LPAI_$nome" -ErrorAction SilentlyContinue
    }
}
if ($Servidor) {
    Executar "gerar o certificado HTTPS local (config\certificados)" {
        & $pyBackend (Join-Path $Raiz "backend\certificado_local.py") (Join-Path $Raiz "config\certificados")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o certificado HTTPS" }
    }
}

# ---------------------------------------------------------------- app web
if ($Servidor) {
    Passo "App web do professor"
    if (Test-Path "$Raiz\app\build\web\index.html") { Ok "ja compilado (app\build\web)" }
    elseif (Get-Command flutter -ErrorAction SilentlyContinue) {
        Executar "flutter build web --base-href /app/" {
            Push-Location "$Raiz\app"; flutter build web --base-href /app/ --no-wasm-dry-run; Pop-Location
        }
    } else { Aviso "app\build\web nao encontrado e Flutter nao instalado: use o pacote de instalacao que ja traz o app compilado." }
}

# ---------------------------------------------------------------- firewall
if ($Servidor) {
    Passo "Firewall (porta $Porta e busca na rede para os celulares)"
    if ($Admin) {
        Executar "liberar a porta TCP $Porta e a porta UDP $PortaDescoberta na rede" {
            Get-NetFirewallRule -DisplayName "LivePresenceAI" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
            Get-NetFirewallRule -DisplayName "LivePresenceAI (busca na rede)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
            New-NetFirewallRule -DisplayName "LivePresenceAI" -Direction Inbound -Protocol TCP -LocalPort $Porta -Action Allow | Out-Null
            New-NetFirewallRule -DisplayName "LivePresenceAI (busca na rede)" -Direction Inbound -Protocol UDP -LocalPort $PortaDescoberta -Action Allow | Out-Null
            Ok "portas liberadas"
        }
    } else { Aviso "rode o instalador como administrador para liberar as portas $Porta (TCP) e $PortaDescoberta (UDP) no firewall (necessario para os celulares)." }
}

# ---------------------------------------------------------------- atalho
if (-not $SemAtalho) {
    Passo "Atalho na area de trabalho e no menu Iniciar"
    $pythonw = $pyBackend -replace "python.exe$", "pythonw.exe"
    Executar "criar 'LivePresenceAI' na area de trabalho e no menu Iniciar" {
        # Como administrador, o atalho vai para todos os usuarios (a conta que aprovou pode ser outra)
        $pastas = if ($Admin) { @([Environment]::GetFolderPath("CommonDesktopDirectory"), [Environment]::GetFolderPath("CommonPrograms")) }
                  else { @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs")) }
        $shell = New-Object -ComObject WScript.Shell
        foreach ($pasta in $pastas) {
            $atalho = $shell.CreateShortcut((Join-Path $pasta "LivePresenceAI.lnk"))
            $atalho.TargetPath = $pythonw
            $atalho.Arguments = """$Raiz\painel\painel.py"""
            $atalho.WorkingDirectory = "$Raiz\painel"
            $atalho.Description = "Painel do LivePresenceAI"
            $icone = Join-Path $Raiz "painel\livepresenceai.ico"
            if (Test-Path $icone) { $atalho.IconLocation = $icone }
            $atalho.Save()
        }
        Ok "atalhos criados"
    }
}

Write-Host "`nInstalacao concluida." -ForegroundColor Green
Write-Host "Abra o atalho 'LivePresenceAI' na area de trabalho e clique em 'Ligar tudo'."
if ($Servidor) { Write-Host "No primeiro acesso ao app, crie a conta do administrador." }
