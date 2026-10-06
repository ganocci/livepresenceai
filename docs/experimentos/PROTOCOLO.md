# Protocolo dos experimentos (E1 a E5)

Roteiro prático para executar os experimentos planejados no TCC (seção 4.6). As medidas saem das ferramentas
de `ia/experimentos.py` e de `ia/modulo_reconhecimento.py --medir`. **Nenhuma imagem é gravada**: só números
(similaridades, escores e tempos), em `ia/resultados/` (fora do Git).

Registrar no TCC somente o que for medido aqui, com as condições reais (computador, câmera, iluminação,
número de pessoas e de tentativas).

---

## 0. Antes do dia

- [ ] Confirmar com o orientador se os experimentos com voluntários precisam de aprovação além do termo de
      consentimento (seção 6). Os voluntários são adultos.
- [ ] Imprimir o termo (seção 6), uma cópia por voluntário.
- [ ] Computador do teste: o mesmo que será descrito no TCC. Anotar processador, memória, placa de vídeo,
      sistema e câmera (marca, modelo e resolução).
- [ ] Material do E2: foto colorida impressa em A4 do rosto de 2 voluntários (que autorizaram) e um celular
      com foto e vídeo desses rostos.
- [ ] Fita métrica (distâncias de 1 m, 2 m e 3 m marcadas no chão) e cronômetro (o do celular serve).
- [ ] Sistema ligado pelo painel; abrir um PowerShell em `ia\` com o ambiente do módulo:
      ```powershell
      cd C:\LivePresenceAI\ia        # ou a pasta do projeto
      .\.venv\Scripts\activate       # ou .\venv\Scripts\activate
      $env:LIVEPRESENCEAI_BACKEND = "https://localhost:8443"
      $env:CHAVE_MODULO_IA = "<chave do painel: Celulares e outras salas>"
      $env:LIVEPRESENCEAI_CA = "..\config\certificados\ca.crt"
      ```

## 1. Preparação (≈ 20 min)

1. No app, criar a turma **"Experimento E1-E5"** e cadastrar os voluntários (nome e RA fictício, ex.: `V01`),
   marcando a autorização de biometria **depois** de o voluntário assinar o termo.
2. Cadastrar o rosto de cada voluntário **cadastrado** pelo app (como o professor faria).
   Separar **2 ou 3 voluntários sem cadastro facial**: eles são as "pessoas não cadastradas" do E1.
3. Anotar o número da turma e o `aluno_id` de cada voluntário:
   ```powershell
   python experimentos.py capturar --turma <N> --pessoa 0 --condicao x
   ```
   (o comando recusa o aluno 0 e lista os cadastrados com seus números).
4. Planilha de controle (papel ou Excel): voluntário, `aluno_id`, grupo declarado (opcional, ver seção 6),
   tentativas feitas.

## 2. E1 — Reconhecimento (≈ 6 min por voluntário)

Cada tentativa: a pessoa fica diante da câmera, olhando para a sala normalmente (não precisa encarar a
câmera), por 10 s. O comando faz uma contagem de 3 s antes de gravar.

```powershell
python experimentos.py capturar --turma <N> --pessoa <aluno_id> --condicao <condicao> [--grupo <grupo>]
python experimentos.py capturar --turma <N> --pessoa nao-cadastrado --condicao <condicao>
```

Condições (repetir para cada voluntário, cadastrado ou não):

| Condição (`--condicao`) | Como |
|---|---|
| `luz-normal-1m` | Luz da sala, 1 m, de frente |
| `luz-normal-2m` | Luz da sala, 2 m |
| `luz-normal-3m` | Luz da sala, 3 m |
| `lateral-30-2m` | 2 m, rosto virado ~30° |
| `luz-baixa-2m` | Metade das luzes apagadas, 2 m |
| `contraluz-2m` | Janela ou luz atrás da pessoa, 2 m |
| `oculos-2m` | Com óculos (de grau ou escuros, anotar), 2 m |
| `bone-capuz-2m` | Boné ou capuz, 2 m |

Com 8 voluntários cadastrados e 3 não cadastrados, são 88 tentativas (~25 min de gravação).

Análise:
```powershell
python experimentos.py reconhecimento resultados\capturas.jsonl
```
Saída: FMR e FNMR por limiar (ISO/IEC 19795-1), identificação 1:N (acerto, troca de identidade, FPIR para
não cadastrados), resultados por condição e por grupo, limiar sugerido, gráficos (`*_e1_*.png`) e CSV.

## 3. E2 — Ataques de apresentação (≈ 10 min)

Com 2 voluntários cadastrados, 3 tentativas de cada tipo, a 1 m:

```powershell
python experimentos.py capturar --turma <N> --pessoa <aluno_id> --apresentacao foto  --condicao foto-impressa-a4-1m
python experimentos.py capturar --turma <N> --pessoa <aluno_id> --apresentacao video --condicao tela-celular-foto-1m
python experimentos.py capturar --turma <N> --pessoa <aluno_id> --apresentacao video --condicao tela-celular-video-1m
```

As tentativas genuínas do E1 servem como apresentações genuínas (bona fide).

Análise:
```powershell
python experimentos.py prova-de-vida resultados\capturas.jsonl
```
Saída: APCER por tipo de ataque e BPCER por limiar (ISO/IEC 30107-3), limiar sugerido, ataques que passaram
em ao menos um quadro (no sistema, basta um quadro aceito para identificar a pessoa) e gráficos.

## 4. E3 — Permanência e E5 — Desempenho (≈ 25 min, juntos)

1. No app, abrir a chamada da turma de experimento.
2. Num PowerShell, ligar o módulo medindo o desempenho (E5) durante a aula:
   ```powershell
   python modulo_reconhecimento.py --turma <N> --camera 0 --medir resultados\e5.csv --duracao 1200
   ```
   (no painel, deixar o reconhecimento da sala **desligado** para não haver dois módulos na mesma câmera).
3. Noutro PowerShell, o observador abre o cronômetro (E3) com 4 voluntários cadastrados:
   ```powershell
   python experimentos.py cronometro --pessoas "<id>=Ana,<id>=Bruno,<id>=Carla,<id>=Davi"
   ```
   Digitar o número e Enter **no momento em que a pessoa cruza a porta** (entrando ou saindo).
4. Roteiro de 20 minutos (cada um registra a chegada no início):

   | Voluntário | Roteiro |
   |---|---|
   | A | Fica a aula inteira |
   | B | Chega 6 min atrasado |
   | C | Sai no minuto 5, volta no minuto 9 |
   | D | Sai definitivamente no minuto 7 (abaixo dos 40%) |

5. Encerrar a chamada no app ao fim dos 20 min (o módulo para sozinho com `--duracao`).
6. Análises:
   ```powershell
   python experimentos.py permanencia --sessao <número da chamada> --eventos resultados\e3_eventos.csv --email <e-mail do professor>
   python experimentos.py desempenho resultados\e5.csv
   ```
   E3: erro em segundos e em pontos percentuais por aluno e situação (presença/falta) esperada × calculada.
   E5: quadros por segundo, tempo de cada etapa, latência da captura ao registro e uso de CPU, memória e GPU.

Repetir o E5 por 2 minutos com **4 ou mais pessoas** na imagem ao mesmo tempo (o custo do reconhecimento
cresce com o número de rostos).

## 5. E4 — Tempo de chamada (≈ 10 min)

Cronometrar, com a mesma lista de alunos (a turma de experimento ou uma lista impressa de 30 nomes):

| Forma | Início do cronômetro | Fim |
|---|---|---|
| Chamada nominal | Professor começa a ler a lista | Último nome respondido e anotado |
| LivePresenceAI | Professor toca em "Iniciar chamada" | Professor encerra a chamada e confere o relatório (incluindo ajustes manuais, se houver) |

Fazer 3 repetições de cada forma e anotar em `ia\resultados\e4_tempos.csv` (forma; repetição; segundos;
alunos). O tempo do sistema é o **tempo de atenção do professor**, não a duração da aula.

## 6. Ética e privacidade

- Voluntários **adultos**, com termo assinado antes de qualquer cadastro. Quem não quiser participar de
  alguma parte (ex.: foto impressa do E2) apenas não participa.
- Só números são guardados. O cadastro facial é o mesmo vetor do sistema e é **apagado ao final**: no app,
  remover o cadastro facial de cada voluntário (a turma em si não pode ser excluída depois de ter chamadas,
  porque o histórico é preservado — RN-10).
- Grupo demográfico (`--grupo`) só se o voluntário quiser declarar, com categorias definidas antes do teste.
  Com poucos voluntários por grupo, o TCC deve apresentar o resultado como indicativo, não conclusivo.

**Modelo de termo (revisar com o orientador antes de usar):**

> Eu, ______________________________, maior de 18 anos, concordo em participar voluntariamente dos testes do
> trabalho de conclusão de curso "LivePresenceAI" (UNIP), dos alunos João Pedro Santos de Oliveira, Lucas
> Brandão Oliveira e Filipe Félix da Silva, sob orientação do Prof. Álvaro Nunes. Fui informado(a) de que:
> (1) meu rosto será captado pela câmera apenas durante os testes; (2) nenhuma foto ou vídeo será gravado,
> somente medidas numéricas e um vetor de características facial, que serão apagados ao final dos testes;
> (3) os resultados serão publicados apenas de forma agregada, sem me identificar; (4) posso desistir a
> qualquer momento, sem nenhum prejuízo; (5) [se aplicável] autorizo que uma foto do meu rosto seja impressa
> e exibida em tela para o teste de ataques, sendo destruída ao final.
> Data: ___/___/2026  Assinatura: ______________________

## 7. Depois dos testes

1. Rodar as análises e guardar a pasta `ia\resultados\` fora do Git (cópia dos autores).
2. Remover no app o cadastro facial de cada voluntário da turma de experimento.
3. Calibrar `CONFIANCA_MINIMA` (backend) e `LIMIAR_PROVA_VIDA` (módulo de IA) com os limiares sugeridos,
   se os resultados justificarem, e registrar a decisão na documentação técnica.
