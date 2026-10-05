<#
LivePresenceAI - Janela do instalador (para o usuario final).

Vai dentro do "Instalar-LivePresenceAI.exe" (gerado por empacotar.ps1), junto com livepresenceai.zip. Pede a
permissao de administrador, copia o sistema para a pasta escolhida (padrao C:\LivePresenceAI, sem acentos no
caminho) e roda o instalar.ps1 de la sem perguntas no console, mostrando o andamento numa janela.

Teste sem instalar nada:  powershell -ExecutionPolicy Bypass -File instalador.ps1 -Simular
#>
param([switch]$Simular)

$ErrorActionPreference = "Stop"
$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$PowerShell64 = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

function Mensagem($texto, $icone = "Information") {
    [void][System.Windows.Forms.MessageBox]::Show($texto, "LivePresenceAI", "OK", $icone)
}

# ---------------------------------------------------------------- administrador
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $Simular) {
    try {
        $argumentos = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
        Start-Process -FilePath $PowerShell64 -ArgumentList $argumentos -Verb RunAs -Wait
    } catch {
        Mensagem ("O instalador precisa da permissão de administrador para instalar o banco de dados, " +
                  "liberar o acesso dos celulares no firewall e criar os atalhos.`n`nAbra o instalador de novo " +
                  "e clique em ""Sim"" quando o Windows perguntar.") "Warning"
    }
    exit
}

# ---------------------------------------------------------------- execucao do instalar.ps1 com saida em fila
# (eventos de saida chegam em outra thread; o C# guarda as linhas e a janela as le num Timer)
Add-Type -TypeDefinition @"
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
public class ExecucaoInstalador {
    public ConcurrentQueue<string> Linhas = new ConcurrentQueue<string>();
    public Process Processo;
    public void Iniciar(string arquivo, string argumentos, string pasta, string[] ambiente) {
        var info = new ProcessStartInfo(arquivo, argumentos);
        info.WorkingDirectory = pasta;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        var oem = Encoding.GetEncoding(System.Globalization.CultureInfo.CurrentCulture.TextInfo.OEMCodePage);
        info.StandardOutputEncoding = oem;
        info.StandardErrorEncoding = oem;
        for (int i = 0; i + 1 < ambiente.Length; i += 2) info.EnvironmentVariables[ambiente[i]] = ambiente[i + 1];
        Processo = new Process();
        Processo.StartInfo = info;
        Processo.OutputDataReceived += (s, e) => { if (e.Data != null) Linhas.Enqueue(e.Data); };
        Processo.ErrorDataReceived += (s, e) => { if (e.Data != null) Linhas.Enqueue(e.Data); };
        Processo.Start();
        Processo.BeginOutputReadLine();
        Processo.BeginErrorReadLine();
    }
}
"@

# ---------------------------------------------------------------- janela
$AZUL = [System.Drawing.Color]::FromArgb(8, 102, 255)
$ROXO = [System.Drawing.Color]::FromArgb(123, 97, 255)
$CINZA = [System.Drawing.Color]::FromArgb(101, 103, 107)
$FONTE = New-Object System.Drawing.Font("Segoe UI", 10)
$psqlExistente = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

$form = New-Object System.Windows.Forms.Form
$form.Text = "Instalar o LivePresenceAI"
$form.ClientSize = New-Object System.Drawing.Size(600, 600)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::White
$form.Font = $FONTE

function Rotulo($texto, $x, $y, $largura, $altura, $cor = $null, $fonte = $null) {
    $r = New-Object System.Windows.Forms.Label
    $r.Text = $texto; $r.Location = New-Object System.Drawing.Point($x, $y)
    $r.Size = New-Object System.Drawing.Size($largura, $altura)
    if ($cor) { $r.ForeColor = $cor }
    if ($fonte) { $r.Font = $fonte }
    $form.Controls.Add($r); return $r
}

$marca = New-Object System.Drawing.Font("Segoe UI", 22, [System.Drawing.FontStyle]::Bold)
$r = Rotulo "livepresence" 24 16 178 44 $AZUL $marca
$r = Rotulo "AI" 198 16 60 44 $ROXO $marca
$r = Rotulo "Sistema de chamada por reconhecimento facial. Escolha como este computador vai ser usado:" 26 64 550 40 $CINZA

$opcoes = @(
    @{ Papel = "Completo"; Texto = "Este computador faz tudo (recomendado)"; Ajuda = "Servidor, app do professor e a câmera desta sala." },
    @{ Papel = "Servidor"; Texto = "Só o servidor"; Ajuda = "As câmeras ficam em outros computadores." },
    @{ Papel = "Sala"; Texto = "Só a câmera de uma sala"; Ajuda = "O servidor já está instalado em outro computador da rede." }
)
$radios = @{}
$y = 108
foreach ($o in $opcoes) {
    $rb = New-Object System.Windows.Forms.RadioButton
    $rb.Text = $o.Texto; $rb.Tag = $o.Papel
    $rb.Location = New-Object System.Drawing.Point(28, $y); $rb.Size = New-Object System.Drawing.Size(540, 24)
    $rb.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($rb); $radios[$o.Papel] = $rb
    $r = Rotulo $o.Ajuda 46 ($y + 24) 520 20 $CINZA
    $y += 52
}
$radios["Completo"].Checked = $true

# Campos que aparecem conforme a escolha
$lblChave = Rotulo "Chave do módulo de IA (no servidor: painel > ""Celulares e outras salas"" > Copiar chave):" 28 262 550 36
$txtChave = New-Object System.Windows.Forms.TextBox
$txtChave.Location = New-Object System.Drawing.Point(30, 300); $txtChave.Size = New-Object System.Drawing.Size(536, 26)
$form.Controls.Add($txtChave)

$lblSenha = Rotulo "Este computador já tem PostgreSQL. Senha do usuário ""postgres"" (deixe em branco se for uma reinstalação do LivePresenceAI):" 28 262 550 36
$txtSenha = New-Object System.Windows.Forms.TextBox
$txtSenha.UseSystemPasswordChar = $true
$txtSenha.Location = New-Object System.Drawing.Point(30, 300); $txtSenha.Size = New-Object System.Drawing.Size(536, 26)
$form.Controls.Add($txtSenha)

$r = Rotulo "Pasta:" 28 342 50 22
$txtPasta = New-Object System.Windows.Forms.TextBox
$txtPasta.Text = "C:\LivePresenceAI"
$txtPasta.Location = New-Object System.Drawing.Point(80, 339); $txtPasta.Size = New-Object System.Drawing.Size(486, 26)
$form.Controls.Add($txtPasta)

$progresso = New-Object System.Windows.Forms.ProgressBar
$progresso.Location = New-Object System.Drawing.Point(30, 378); $progresso.Size = New-Object System.Drawing.Size(536, 10)
$progresso.Visible = $false
$form.Controls.Add($progresso)
$lblEtapa = Rotulo "Leva de 10 a 30 minutos (baixa o Python, o banco de dados e os modelos de IA). Precisa de internet." 28 394 550 36 $CINZA

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true; $log.ReadOnly = $true; $log.ScrollBars = "Vertical"
$log.Font = New-Object System.Drawing.Font("Consolas", 8.5)
$log.BackColor = [System.Drawing.Color]::FromArgb(240, 242, 245)
$log.Location = New-Object System.Drawing.Point(30, 434); $log.Size = New-Object System.Drawing.Size(536, 104)
$form.Controls.Add($log)

$botao = New-Object System.Windows.Forms.Button
$botao.Text = "Instalar"
$botao.Location = New-Object System.Drawing.Point(366, 550); $botao.Size = New-Object System.Drawing.Size(200, 36)
$botao.BackColor = $AZUL; $botao.ForeColor = [System.Drawing.Color]::White; $botao.FlatStyle = "Flat"
$botao.FlatAppearance.BorderSize = 0
$botao.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($botao)
$form.AcceptButton = $botao

$botaoFechar = New-Object System.Windows.Forms.Button
$botaoFechar.Text = "Fechar"
$botaoFechar.Location = New-Object System.Drawing.Point(226, 550); $botaoFechar.Size = New-Object System.Drawing.Size(130, 36)
$botaoFechar.FlatStyle = "Flat"
$botaoFechar.Add_Click({ $form.Close() })
$form.Controls.Add($botaoFechar)

function PapelEscolhido { ($radios.Values | Where-Object { $_.Checked } | Select-Object -First 1).Tag }
function AtualizarCampos {
    $papel = PapelEscolhido
    $sala = $papel -eq "Sala"
    $lblChave.Visible = $sala; $txtChave.Visible = $sala
    $pedirSenha = (-not $sala) -and $psqlExistente
    $lblSenha.Visible = $pedirSenha; $txtSenha.Visible = $pedirSenha
}
foreach ($rb in $radios.Values) { $rb.Add_CheckedChanged({ AtualizarCampos }) }
AtualizarCampos

# ---------------------------------------------------------------- instalacao
$script:execucao = $null
$script:etapas = 0
$script:totalEtapas = 9
$script:arquivoLog = $null
$script:pasta = $null

function Escrever($linha) {
    $log.AppendText($linha + [Environment]::NewLine)
    if ($script:arquivoLog) { Add-Content -Path $script:arquivoLog -Value $linha -Encoding UTF8 }
}

function Concluir($sucesso) {
    $progresso.Style = "Continuous"
    if ($sucesso) {
        $progresso.Value = $progresso.Maximum
        $lblEtapa.Text = "Pronto! Abra o LivePresenceAI e clique em ""Ligar tudo""."
        $lblEtapa.ForeColor = [System.Drawing.Color]::FromArgb(49, 162, 76)
        $botao.Text = "Abrir o LivePresenceAI"
        $botao.Enabled = $true
        $botao.Tag = "abrir"
    } else {
        $lblEtapa.Text = "A instalação não terminou. Veja as mensagens abaixo (salvas em $script:arquivoLog) e tente de novo."
        $lblEtapa.ForeColor = [System.Drawing.Color]::FromArgb(228, 30, 63)
        $botao.Text = "Tentar de novo"
        $botao.Enabled = $true
        $botao.Tag = $null
        foreach ($c in @($txtChave, $txtSenha, $txtPasta) + @($radios.Values)) { $c.Enabled = $true }
    }
    $botaoFechar.Enabled = $true
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$timer.Add_Tick({
    if (-not $script:execucao) { return }
    $linha = $null
    while ($script:execucao.Linhas.TryDequeue([ref]$linha)) {
        Escrever $linha
        if ($linha -like "==> *") {
            $script:etapas++
            $lblEtapa.Text = $linha.Substring(4) + "..."
            $lblEtapa.ForeColor = $CINZA
            $progresso.Style = "Continuous"
            $progresso.Value = [Math]::Min(95, [int](100 * $script:etapas / $script:totalEtapas))
        }
    }
    if ($script:execucao.Processo.HasExited) {
        $codigo = $script:execucao.Processo.ExitCode
        $script:execucao = $null
        $timer.Stop()
        Concluir ($codigo -eq 0)
    }
})

function AbrirPainel {
    # Pelo atalho, via Explorer: o painel abre com o usuario comum, nao como administrador
    $atalho = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "LivePresenceAI.lnk"
    if (-not (Test-Path $atalho)) { $atalho = Join-Path ([Environment]::GetFolderPath("Desktop")) "LivePresenceAI.lnk" }
    if (Test-Path $atalho) { Start-Process explorer.exe "`"$atalho`"" } else { Mensagem "Atalho não encontrado: abra a pasta $script:pasta\painel." }
    $form.Close()
}

function Instalar {
    $papel = PapelEscolhido
    $pasta = $txtPasta.Text.Trim().TrimEnd("\")
    if ($pasta -notmatch "^[A-Za-z]:\\[A-Za-z0-9_\-\\ ]+$") {
        Mensagem "Use uma pasta sem acentos nem símbolos, por exemplo C:\LivePresenceAI." "Warning"; return
    }
    if ($papel -eq "Sala" -and -not $txtChave.Text.Trim()) {
        Mensagem "Informe a chave do módulo de IA (está no painel do computador servidor)." "Warning"; return
    }
    $script:pasta = $pasta
    foreach ($c in @($txtChave, $txtSenha, $txtPasta, $botao, $botaoFechar) + @($radios.Values)) { $c.Enabled = $false }
    $progresso.Visible = $true
    $progresso.Style = "Marquee"
    $log.Clear()
    $script:etapas = 0
    $script:totalEtapas = if ($papel -eq "Sala") { 6 } elseif ($papel -eq "Servidor") { 8 } else { 9 }

    try {
        $lblEtapa.Text = "Copiando os arquivos para $pasta..."
        $form.Refresh()
        if ($Simular) {
            $origem = Split-Path -Parent $Aqui  # pasta do projeto (teste a partir do repositorio)
            $destino = $origem
        } else {
            New-Item -ItemType Directory -Force -Path $pasta | Out-Null
            Expand-Archive -Path (Join-Path $Aqui "livepresenceai.zip") -DestinationPath $pasta -Force
            # O painel roda com o usuario comum: ele precisa gravar a configuracao e os registros nesta pasta
            & icacls $pasta /grant "*S-1-5-32-545:(OI)(CI)M" /T /Q | Out-Null
            $destino = $pasta
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $destino "config\logs") | Out-Null
        $script:arquivoLog = Join-Path $destino "config\logs\instalacao.log"
        Set-Content -Path $script:arquivoLog -Value "LivePresenceAI - instalacao ($papel) $(Get-Date -Format s)" -Encoding UTF8

        $argumentos = "-NoProfile -ExecutionPolicy Bypass -File `"$destino\instalar.ps1`" -Papel $papel"
        if ($Simular) { $argumentos += " -Simular" }
        $ambiente = @("LIVEPRESENCEAI_SEM_PERGUNTAS", "1")
        if ($txtChave.Visible -and $txtChave.Text.Trim()) { $ambiente += @("LIVEPRESENCEAI_CHAVE_SALA", $txtChave.Text.Trim()) }
        if ($txtSenha.Visible -and $txtSenha.Text) { $ambiente += @("LIVEPRESENCEAI_SENHA_POSTGRES", $txtSenha.Text) }

        $script:execucao = New-Object ExecucaoInstalador
        $script:execucao.Iniciar($PowerShell64, $argumentos, $destino, [string[]]$ambiente)
        $timer.Start()
    } catch {
        Escrever "ERRO: $($_.Exception.Message)"
        Concluir $false
    }
}

$botao.Add_Click({ if ($botao.Tag -eq "abrir") { AbrirPainel } else { Instalar } })
$form.Add_FormClosing({
    param($origem, $evento)
    if ($script:execucao -and -not $script:execucao.Processo.HasExited) {
        $resposta = [System.Windows.Forms.MessageBox]::Show("A instalação ainda está em andamento. Interromper?",
            "LivePresenceAI", "YesNo", "Warning")
        if ($resposta -ne "Yes") { $evento.Cancel = $true; return }
        # Encerra tambem o que o instalador abriu (pip, winget)
        & taskkill.exe /T /F /PID $script:execucao.Processo.Id | Out-Null
    }
})

[void]$form.ShowDialog()
