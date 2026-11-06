<#
LivePresenceAI - Menu dos experimentos do TCC (E1, E2, E3 e E5) no computador da sala.

Uso (no computador onde o LivePresenceAI esta instalado, com o servidor ligado pelo painel e o
reconhecimento da sala DESLIGADO no painel, para nao haver dois programas na mesma camera):
  powershell -ExecutionPolicy Bypass -File C:\LivePresenceAI\ia\experimentos.ps1

Le o endereco, a chave do modulo de IA e o certificado de config\livepresenceai.json; os resultados ficam
em ia\resultados (so numeros, nenhuma imagem). A opcao 7 junta tudo num .zip para enviar a equipe.
#>
$ErrorActionPreference = "Stop"
$Ia = $PSScriptRoot
$Raiz = Split-Path -Parent $Ia
$Resultados = Join-Path $Ia "resultados"
$Estado = Join-Path $Resultados "experimentos_menu.json"
$Python = @("$Ia\.venv\Scripts\python.exe", "$Ia\venv\Scripts\python.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) { throw "Ambiente do modulo de IA nao encontrado em $Ia (.venv)." }
$ArquivoConfig = Join-Path $Raiz "config\livepresenceai.json"
if (Test-Path $ArquivoConfig) {
    $Config = Get-Content $ArquivoConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $esquema = if ($Config.servidor.https) { "https" } else { "http" }
    $env:LIVEPRESENCEAI_BACKEND = "${esquema}://localhost:$($Config.servidor.porta)"
    $env:CHAVE_MODULO_IA = if ($Config.sala.chave_modulo_ia) { $Config.sala.chave_modulo_ia } else { $Config.servidor.chave_modulo_ia }
} else {
    # Pasta do projeto (desenvolvimento): backend em HTTPS na 8443 e chave padrao do modulo de IA
    $Config = [pscustomobject]@{ sala = [pscustomobject]@{ camera = 0 } }
    if (-not $env:LIVEPRESENCEAI_BACKEND) { $env:LIVEPRESENCEAI_BACKEND = "https://localhost:8443" }
}
$ca = Join-Path $Raiz "config\certificados\ca.crt"
if (Test-Path $ca) { $env:LIVEPRESENCEAI_CA = $ca }
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force $Resultados | Out-Null
Set-Location $Ia

function Ler-Estado {
    if (Test-Path $Estado) { return Get-Content $Estado -Raw -Encoding UTF8 | ConvertFrom-Json }
    return [pscustomobject]@{ email = ""; camera = $Config.sala.camera; todos = ""; rodizio = ""; pessoas = ""; sessao = "" }
}
function Gravar-Estado($e) { $e | ConvertTo-Json | Set-Content $Estado -Encoding UTF8 }
function Pedir($e, $campo, $texto) {
    $atual = $e.$campo
    $valor = Read-Host "$texto$(if ($atual) { " [$atual]" })"
    if ($valor) { $e.$campo = $valor }
    Gravar-Estado $e
    return $e.$campo
}
function Py { & $Python @args; if ($LASTEXITCODE -ne 0) { Write-Host "(o comando terminou com erro $LASTEXITCODE)" -ForegroundColor Yellow } }

$e = Ler-Estado
Write-Host "LivePresenceAI - experimentos | servidor $($env:LIVEPRESENCEAI_BACKEND) | resultados em $Resultados" -ForegroundColor Cyan
while ($true) {
    Write-Host ""
    Write-Host "1  Listar turmas e numeros dos alunos"
    Write-Host "2  Configurar: turmas do E1, camera e e-mail do professor"
    Write-Host "3  E1 - reconhecimento em sala (72 tentativas; pode parar e continuar)"
    Write-Host "4  E2 - ataques com foto e tela (27 tentativas)"
    Write-Host "5  E3 + E5 - aula de 20 min (abra a chamada da turma 'todos' no app ANTES)"
    Write-Host "6  E5 - 2 min com os tres na camera (abra a chamada antes)"
    Write-Host "7  Comparar o E3 com o relatorio e gerar o pacote .zip para enviar"
    Write-Host "0  Sair"
    switch (Read-Host "Opcao") {
        "1" { $email = Pedir $e "email" "E-mail do professor"; Py experimentos.py turmas --email $email --filtro E1 }
        "2" {
            Pedir $e "email" "E-mail do professor" | Out-Null
            Pedir $e "camera" "Numero da camera (0 = a primeira)" | Out-Null
            Pedir $e "todos" "Numero da turma 'E1 Todos'" | Out-Null
            Write-Host "Rodizio: para cada autor, 'numero do aluno na turma E1 Todos:numero da turma em que ele esta SEM rosto'"
            Write-Host "Exemplo: 281:72,282:73,283:74"
            Pedir $e "rodizio" "Rodizio" | Out-Null
            Write-Host "Pessoas do cronometro do E3: 'numero=Nome', exemplo: 281=Joao,282=Lucas,283=Filipe"
            Pedir $e "pessoas" "Pessoas" | Out-Null
        }
        "3" {
            # PowerShell 5.1 descarta argumento vazio: so passa o rodizio quando ha um (teste com um autor nao tem)
            $extra = @(); if ($e.rodizio) { $extra = @("--rodizio", $e.rodizio) }
            Py experimentos.py roteiro e1 --todos $e.todos --camera $e.camera @extra
        }
        "4" { Py experimentos.py roteiro e2 --todos $e.todos --camera $e.camera }
        "5" {
            Write-Host "Abrindo o modulo da sala (medindo por 20 min) em outra janela..."
            $argumentos = "modulo_reconhecimento.py --turma $($e.todos) --camera $($e.camera) --medir resultados\e5_aula.csv --duracao 1200"
            Start-Process -FilePath $Python -ArgumentList $argumentos -WorkingDirectory $Ia
            Write-Host "Cronometro do E3: quando alguem cruzar a porta, digite o numero e Enter (alterna entrou/saiu); 'v' mostra quem esta dentro; 'q' encerra." -ForegroundColor Cyan
            Py experimentos.py cronometro --pessoas $e.pessoas --saida resultados\e3_eventos.csv
            Write-Host "Agora ENCERRE a chamada no app e anote o numero da sessao (aparece no relatorio/historico)."
        }
        "6" {
            Py modulo_reconhecimento.py --turma $e.todos --camera $e.camera --medir resultados\e5_tres.csv --duracao 120
            Write-Host "Pronto. Pode encerrar a chamada no app."
        }
        "7" {
            $sessao = Pedir $e "sessao" "Numero da sessao (chamada) da aula do E3"
            # Avisos do Python no stderr nao podem interromper o menu (PowerShell 5.1 os trata como erro com 2>&1)
            $ErrorActionPreference = "Continue"
            $log = Join-Path $Resultados "analises.txt"
            "LivePresenceAI - analises geradas em $(Get-Date -Format s) no computador $env:COMPUTERNAME" | Set-Content $log -Encoding UTF8
            if (Test-Path resultados\e3_eventos.csv) {
                & $Python experimentos.py permanencia --sessao $sessao --eventos resultados\e3_eventos.csv --email $e.email 2>&1 | Tee-Object -FilePath $log -Append
            }
            foreach ($csv in @("resultados\e5_aula.csv", "resultados\e5_tres.csv")) {
                if (Test-Path $csv) { & $Python experimentos.py desempenho $csv 2>&1 | Tee-Object -FilePath $log -Append }
            }
            $zip = Join-Path ([Environment]::GetFolderPath("Desktop")) "resultados_experimentos_$(Get-Date -Format yyyyMMdd_HHmm).zip"
            $arquivos = Get-ChildItem $Resultados -File | Where-Object { $_.Extension -in ".jsonl", ".csv", ".txt", ".json" }
            Compress-Archive -Path $arquivos.FullName -DestinationPath $zip -Force
            Write-Host "Pacote gerado: $zip  (envie este arquivo)" -ForegroundColor Green
        }
        "0" { return }
    }
}
