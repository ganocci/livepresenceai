# Protocolo dos experimentos (E1 a E5) e da avaliação de usabilidade

Roteiro prático para executar os experimentos do TCC (seção 4.6). **Somente os três autores participam**: não há
voluntários nem dados de outras pessoas. Isso transforma os experimentos em testes do sistema executados pela
própria equipe, sobre os próprios dados (seção 4.7 do TCC). Para dar escala ao E1, ele é complementado por uma
base pública de pesquisa, a LFW (seção 3).

As medidas saem de `ia/experimentos.py` e de `ia/modulo_reconhecimento.py --medir`. **Nenhuma imagem é gravada**:
só números (similaridades, escores e tempos), em `ia/resultados/` (fora do Git). Registrar no TCC somente o que
for medido aqui, com as condições reais (computador, câmera, iluminação, número de tentativas).

Limitações a declarar no TCC: três pessoas não permitem análise por grupo demográfico nem generalizar a acurácia
em sala; a LFW é uma base de fotos da internet, não uma sala de aula; os testes são executados por quem
desenvolveu o sistema.

**Jeito mais fácil:** na pasta do projeto (as ferramentas dos experimentos não vão no instalador final), com o
servidor ligado e nenhum outro programa usando a câmera, rodar
`powershell -ExecutionPolicy Bypass -File ia\experimentos.ps1`. O menu lê a configuração da instalação, se houver,
ou usa o servidor de desenvolvimento em `https://localhost:8443`, lista as turmas e os números dos alunos, conduz o E1 e o E2 com
`experimentos.py roteiro` (modelos carregados uma vez; pode parar e continuar), liga o E3 + E5 e gera um `.zip`
com os resultados na Área de Trabalho. Os comandos abaixo continuam valendo para quem preferir rodá-los à mão.

---

## 0. Antes do dia

- [ ] Computador do teste: o notebook que será descrito no TCC. Anotar processador, memória, placa de vídeo
      (ou "sem placa dedicada"), sistema e câmera (marca, modelo e resolução).
- [ ] Material do E2: foto colorida impressa em A4 do rosto de cada autor e um celular com foto e vídeo de
      cada um.
- [ ] Fita métrica (1 m, 2 m e 3 m marcados no chão) e cronômetro (o do celular serve).
- [ ] Sistema ligado pelo painel; abrir um PowerShell em `ia\` com o ambiente do módulo:
      ```powershell
      cd C:\LivePresenceAI\ia        # ou a pasta do projeto
      .\.venv\Scripts\activate       # ou .\venv\Scripts\activate
      $env:LIVEPRESENCEAI_BACKEND = "https://localhost:8443"
      $env:CHAVE_MODULO_IA = "<chave do painel: Celulares e outras salas>"
      $env:LIVEPRESENCEAI_CA = "..\config\certificados\ca.crt"
      ```

## 1. Preparação (≈ 15 min)

1. No app, criar quatro turmas e cadastrar os três autores como alunos em cada uma (RA fictício, ex.: `A1`, `A2`,
   `A3` com um sufixo por turma), marcando a autorização de biometria:
   - **"E1 Todos"**: rosto cadastrado dos três;
   - **"E1 Sem A1"**, **"E1 Sem A2"**, **"E1 Sem A3"**: rosto cadastrado de dois; o terceiro fica sem cadastro
     facial e faz o papel de "pessoa não cadastrada" (rodízio).
2. Cadastrar os rostos pelo app, como o professor faria.
3. Anotar o número de cada turma e o `aluno_id` de cada autor:
   ```powershell
   python experimentos.py capturar --turma <N> --pessoa 0 --condicao x
   ```
   (o comando recusa o aluno 0 e lista os cadastrados com seus números).

## 2. E1 — Reconhecimento em sala (≈ 5 min por pessoa e turma)

Cada tentativa: a pessoa fica diante da câmera, olhando para a sala normalmente, por 10 s (contagem de 3 s antes).

```powershell
# na turma "E1 Todos": cada autor, como ele mesmo
python experimentos.py capturar --turma <E1 Todos> --pessoa <aluno_id> --condicao <condicao>
# nas turmas de rodízio: o autor sem cadastro, como não cadastrado
python experimentos.py capturar --turma <E1 Sem A1> --pessoa nao-cadastrado --condicao <condicao>
```

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

Repetir cada condição **2 vezes** por pessoa: 3 autores × 8 condições × 2 = 48 tentativas genuínas, e
3 × 8 = 24 tentativas de não cadastrado (uma por condição em cada rodízio). Cerca de 15 min de gravação.

Análise (os arquivos de todas as turmas podem ser analisados juntos):
```powershell
python experimentos.py reconhecimento resultados\capturas.jsonl
```

## 3. E1 — Base pública LFW (sem pessoas, ≈ 20 min de processamento)

A LFW (Labeled Faces in the Wild) é a base clássica de verificação facial: 13.233 fotos de 5.749 pessoas, com o
protocolo padrão de 6.000 pares (3.000 da mesma pessoa e 3.000 de pessoas diferentes) em 10 partes.

```powershell
python experimentos.py lfw --pasta <pasta com lfw\ e pairs.txt>
```

Saída: FMR e FNMR por limiar no mesmo modelo usado em sala, acurácia de verificação nas 10 partes, EER, limiar
sugerido e gráficos. É o número com escala; o da sala (seção 2) mostra o efeito das condições reais.

## 4. E2 — Ataques de apresentação (≈ 10 min)

Cada autor, na turma "E1 Todos", 3 tentativas de cada tipo, a 1 m:

```powershell
python experimentos.py capturar --turma <E1 Todos> --pessoa <aluno_id> --apresentacao foto  --condicao foto-impressa-a4-1m
python experimentos.py capturar --turma <E1 Todos> --pessoa <aluno_id> --apresentacao video --condicao tela-celular-foto-1m
python experimentos.py capturar --turma <E1 Todos> --pessoa <aluno_id> --apresentacao video --condicao tela-celular-video-1m
```

As tentativas genuínas do E1 servem como apresentações genuínas (bona fide). Registrar também a distância em que
rostos genuínos começam a ser recusados (seção 2: as condições a 2 m e 3 m mostram isso).

```powershell
python experimentos.py prova-de-vida resultados\capturas.jsonl
```

## 5. E3 — Permanência e E5 — Desempenho (≈ 25 min, juntos)

1. No app, abrir a chamada da turma "E1 Todos".
2. Num PowerShell, ligar o módulo medindo o desempenho (E5):
   ```powershell
   python modulo_reconhecimento.py --turma <E1 Todos> --camera 0 --medir resultados\e5.csv --duracao 1200
   ```
   (no painel, deixar o reconhecimento da sala **desligado** para não haver dois módulos na mesma câmera).
3. O autor A fica a aula inteira diante do notebook e opera o cronômetro do E3:
   ```powershell
   python experimentos.py cronometro --pessoas "<id>=A,<id>=B,<id>=C"
   ```
   B e C avisam em voz alta ao cruzar a porta, e A digita o número e Enter na hora.
4. Roteiro de 20 minutos:

   | Autor | Roteiro |
   |---|---|
   | A | Fica a aula inteira (e opera o cronômetro) |
   | B | Sai no minuto 5 e volta no minuto 9 |
   | C | Chega 4 min atrasado e sai definitivamente no minuto 10 (abaixo dos 40%) |

5. Encerrar a chamada no app ao fim dos 20 min (o módulo para sozinho com `--duracao`).
6. Análises:
   ```powershell
   python experimentos.py permanencia --sessao <número da chamada> --eventos resultados\e3_eventos.csv --email <e-mail do professor>
   python experimentos.py desempenho resultados\e5.csv
   ```

Repetir o E5 por 2 minutos com os três autores na imagem ao mesmo tempo.

## 6. E4 — Tempo de chamada (simulado, ≈ 10 min)

Sem alunos reais: um autor faz o papel do professor, outro responde "presente", com uma lista impressa de
**40 nomes fictícios**. A turma e a lista são criadas por
`python experimentos.py e4-preparar --email <professor>` (turma "Experimento E4 - chamada", 40 alunos sem
biometria, lista em `ia\resultados\e4_lista_nomes.txt` e modelo em `ia\resultados\e4_tempos.csv`).

| Forma | Início do cronômetro | Fim |
|---|---|---|
| Chamada nominal | Começa a ler a lista | Último nome respondido e anotado |
| LivePresenceAI | Toca em "Iniciar chamada" | Encerra a chamada e confere o relatório (incluindo 2 ajustes manuais) |

3 repetições de cada forma, anotadas em `ia\resultados\e4_tempos.csv` (forma; repetição; segundos; nomes). O
tempo do sistema é o **tempo de atenção do professor**, não a duração da aula. Declarar no TCC que a chamada
nominal foi simulada.

## 7. Avaliação heurística de usabilidade (≈ 1 h, sem participantes)

> **Não executada no TCC** (decisão dos autores em 06/11/2026: só um avaliador disponível). Fica como
> trabalho futuro; o roteiro abaixo é mantido para essa avaliação.

Cada autor, **sozinho**, percorre as tarefas abaixo no app (celular ou navegador) e registra cada problema
encontrado, a heurística de Nielsen violada e a gravidade de 0 a 4 (0 = não é problema; 1 = estético; 2 = pequeno;
3 = grande; 4 = catástrofe). Depois, os três juntam as listas, eliminam repetições e usam a média das gravidades.

Tarefas: entrar no app; criar turma; incluir 3 alunos; cadastrar um rosto; fazer uma chamada; ajustar uma
presença; exportar o relatório em PDF; ver a frequência da turma.

As 10 heurísticas: visibilidade do estado do sistema; correspondência com o mundo real; controle e liberdade do
usuário; consistência e padrões; prevenção de erros; reconhecer em vez de lembrar; flexibilidade e eficiência;
estética e design minimalista; ajudar a reconhecer, diagnosticar e corrigir erros; ajuda e documentação.

Modelo de registro (`ia\resultados\heuristica_<autor>.csv`): tela; problema; heurística; gravidade.

## 8. Privacidade e depois dos testes

- Só os autores participam, sobre os próprios dados, e só números são guardados.
- Ao final, remover no app o cadastro facial dos três em todas as turmas de experimento (as turmas não podem ser
  excluídas depois de ter chamadas, porque o histórico é preservado — RN-10).
- Guardar `ia\resultados\` fora do Git (cópia dos autores).
- Calibrar `CONFIANCA_MINIMA` (backend) e `LIMIAR_PROVA_VIDA` (módulo de IA) com os limiares sugeridos, se os
  resultados justificarem, e registrar a decisão.
