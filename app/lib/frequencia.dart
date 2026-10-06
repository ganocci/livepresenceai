// LivePresenceAI - Frequência acumulada da turma (RN-16): presenças de cada aluno nas aulas encerradas.
// Parte da biblioteca de main.dart (compartilha modelos, utilitários e o tema).

part of 'main.dart';

class FrequenciaAluno {
  final int id;
  final String nome;
  final String? ra;
  final int aulas;
  final int presencas;
  final int faltas;
  final int ajustes;
  final double? percentual;
  final bool abaixoDoMinimo;
  final List<String?> porAula; // 'P', 'F' ou null (ainda não era da turma), na ordem das aulas

  FrequenciaAluno.fromJson(Map<String, dynamic> json)
      : id = json['aluno_id'] as int,
        nome = json['nome'] as String,
        ra = json['ra'] as String?,
        aulas = json['aulas'] as int,
        presencas = json['presencas'] as int,
        faltas = json['faltas'] as int,
        ajustes = json['ajustes_manuais'] as int,
        percentual = (json['percentual'] as num?)?.toDouble(),
        abaixoDoMinimo = json['abaixo_do_minimo'] as bool,
        porAula = (json['por_aula'] as List<dynamic>).cast<String?>();
}

class FrequenciaTurma {
  final double minimo;
  final double minimoAula;
  final List<DateTime> aulas;
  final List<FrequenciaAluno> alunos;
  final int abaixo;

  FrequenciaTurma.fromJson(Map<String, dynamic> json)
      : minimo = (json['frequencia_minima'] as num).toDouble(),
        minimoAula = (json['frequencia_minima_aula'] as num).toDouble(),
        aulas = (json['aulas'] as List<dynamic>)
            .map((a) => _lerHorarioUtc((a as Map<String, dynamic>)['inicio'] as String))
            .toList(),
        alunos = (json['alunos'] as List<dynamic>)
            .map((a) => FrequenciaAluno.fromJson(a as Map<String, dynamic>))
            .toList(),
        abaixo = json['alunos_abaixo_do_minimo'] as int;
}

String _pct(double valor) => '${valor.toStringAsFixed(valor == valor.roundToDouble() ? 0 : 1).replaceAll('.', ',')}%';

/// Cartão do topo do histórico: resumo da frequência e acesso à tela completa.
class _ResumoFrequencia extends StatelessWidget {
  final Turma turma;
  const _ResumoFrequencia({required this.turma});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: ApiService.frequencia(turma.id),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return const SizedBox.shrink();
        final freq = FrequenciaTurma.fromJson(snapshot.data!);
        if (freq.aulas.isEmpty) return const SizedBox.shrink();
        final alerta = freq.abaixo > 0;
        return Cartao(
          margem: const EdgeInsets.fromLTRB(12, 10, 12, 4),
          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => FrequenciaScreen(turma: turma))),
          child: Row(children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: alerta ? Cores.vermelhoClaro : Cores.verdeClaro, shape: BoxShape.circle),
              child: Icon(alerta ? Icons.warning_amber_rounded : Icons.fact_check_outlined,
                  color: alerta ? Cores.vermelho : Cores.verde),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Frequência da turma', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15.5)),
                Text(
                  alerta
                      ? '${_qtd(freq.abaixo, 'aluno')} abaixo de ${_pct(freq.minimo)} · ${_qtd(freq.aulas.length, 'aula')}'
                      : 'Todos com ${_pct(freq.minimo)} ou mais · ${_qtd(freq.aulas.length, 'aula')}',
                  style: TextStyle(color: alerta ? Cores.vermelho : Cores.textoSecundario, fontSize: 13.5),
                ),
              ]),
            ),
            const Icon(Icons.chevron_right, color: Cores.textoSecundario),
          ]),
        );
      },
    );
  }
}

class FrequenciaScreen extends StatefulWidget {
  final Turma turma;
  const FrequenciaScreen({super.key, required this.turma});
  @override
  State<FrequenciaScreen> createState() => _FrequenciaScreenState();
}

class _FrequenciaScreenState extends State<FrequenciaScreen> {
  late Future<FrequenciaTurma> _futuro;
  bool _soAbaixo = false;

  @override
  void initState() {
    super.initState();
    _futuro = _carregar();
  }

  Future<FrequenciaTurma> _carregar() async => FrequenciaTurma.fromJson(await ApiService.frequencia(widget.turma.id));

  void _recarregar() => setState(() => _futuro = _carregar());

  void _detalhes(FrequenciaAluno aluno, FrequenciaTurma freq) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.75),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
            children: [
              Row(children: [
                Avatar(nome: aluno.nome, tamanho: 40),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(aluno.nome, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                    Text(
                        '${aluno.ra != null ? 'RA ${aluno.ra} · ' : ''}${aluno.presencas} de ${aluno.aulas} aulas'
                        '${aluno.percentual != null ? ' · ${_pct(aluno.percentual!)}' : ''}',
                        style: const TextStyle(color: Cores.textoSecundario)),
                  ]),
                ),
              ]),
              const SizedBox(height: 12),
              for (var i = freq.aulas.length - 1; i >= 0; i--)
                if (aluno.porAula[i] != null)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(aluno.porAula[i] == 'P' ? Icons.check_circle : Icons.cancel,
                        color: aluno.porAula[i] == 'P' ? Cores.verde : Cores.vermelho),
                    title: Text('${_formatarData(freq.aulas[i])} · ${_formatarHoraMinuto(freq.aulas[i])}'),
                    trailing: Text(aluno.porAula[i] == 'P' ? 'Presença' : 'Falta',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: aluno.porAula[i] == 'P' ? Cores.verde : Cores.vermelho)),
                  ),
              if (aluno.ajustes > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('${_qtd(aluno.ajustes, 'aula')} com ajuste manual (veja o relatório de cada aula).',
                      style: const TextStyle(color: Cores.textoSecundario, fontSize: 13)),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _linha(FrequenciaAluno aluno, FrequenciaTurma freq) {
    final cor = aluno.percentual == null
        ? Cores.textoSecundario
        : (aluno.abaixoDoMinimo ? Cores.vermelho : Cores.verde);
    return InkWell(
      onTap: aluno.aulas > 0 ? () => _detalhes(aluno, freq) : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(children: [
          Avatar(nome: aluno.nome,
              selo: aluno.abaixoDoMinimo ? const Selo(icone: Icons.priority_high, cor: Cores.vermelho) : null),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(aluno.nome, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
              Text(
                aluno.aulas == 0
                    ? 'Incluído depois das aulas encerradas'
                    : '${aluno.ra != null ? 'RA ${aluno.ra} · ' : ''}${aluno.presencas} de ${aluno.aulas} aulas'
                        '${aluno.ajustes > 0 ? ' · ${_qtd(aluno.ajustes, 'ajuste')}' : ''}',
                style: const TextStyle(color: Cores.textoSecundario, fontSize: 13),
              ),
              if (aluno.percentual != null) ...[
                const SizedBox(height: 6),
                // Barra com a marca do mínimo exigido
                LayoutBuilder(builder: (context, limites) {
                  return Stack(clipBehavior: Clip.none, children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                          value: aluno.percentual! / 100, minHeight: 5, color: cor, backgroundColor: Cores.fundo),
                    ),
                    Positioned(
                      left: limites.maxWidth * freq.minimo / 100 - 1,
                      top: -2,
                      child: Container(width: 2, height: 9, color: Cores.textoSecundario),
                    ),
                  ]);
                }),
              ],
            ]),
          ),
          const SizedBox(width: 12),
          Text(aluno.percentual == null ? '–' : _pct(aluno.percentual!),
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: cor)),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: TituloTela('Frequência', subtitulo: widget.turma.nome),
        actions: [
          BotaoCirculo(icone: Icons.refresh, dica: 'Atualizar', onPressed: _recarregar),
          _BotaoExportar(turmaFrequencia: widget.turma.id),
          const SizedBox(width: 8),
        ],
      ),
      body: FutureBuilder<FrequenciaTurma>(
        future: _futuro,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _MensagemErro(
              mensagem: snapshot.error.toString(),
              onTentarNovamente: _recarregar,
              onSair: () => Navigator.pop(context),
              textoSair: 'Voltar',
            );
          }
          final freq = snapshot.data!;
          if (freq.aulas.isEmpty) {
            return const EstadoVazio(
              icone: Icons.fact_check_outlined,
              titulo: 'Nenhuma aula encerrada',
              texto: 'A frequência de cada aluno aparece aqui depois da primeira chamada encerrada.',
            );
          }
          // Quem está abaixo do mínimo primeiro (menor frequência no topo); depois, em ordem alfabética
          final alunos = [...freq.alunos.where((a) => !_soAbaixo || a.abaixoDoMinimo)]..sort((a, b) {
              if (a.abaixoDoMinimo != b.abaixoDoMinimo) return a.abaixoDoMinimo ? -1 : 1;
              if (a.abaixoDoMinimo) return a.percentual!.compareTo(b.percentual!);
              return a.nome.compareTo(b.nome);
            });
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              Cartao(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(child: Indicador(valor: '${freq.aulas.length}', legenda: 'aulas encerradas')),
                    Expanded(
                        child: Indicador(
                            valor: '${freq.abaixo}',
                            legenda: 'abaixo de ${_pct(freq.minimo)}',
                            cor: freq.abaixo > 0 ? Cores.vermelho : Cores.verde)),
                    Expanded(child: Indicador(valor: _pct(freq.minimo), legenda: 'mínimo das aulas')),
                  ]),
                  const SizedBox(height: 10),
                  Text(
                    'Desde ${_formatarData(freq.aulas.first)}. Em cada aula, presença exige '
                    '${_pct(freq.minimoAula)} do tempo de aula ou o ajuste manual. Toque num aluno para ver as aulas.',
                    style: const TextStyle(color: Cores.textoSecundario, fontSize: 13),
                  ),
                ]),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
                child: Wrap(spacing: 8, children: [
                  ChoiceChip(
                    label: Text('Todos (${freq.alunos.length})'),
                    selected: !_soAbaixo,
                    onSelected: (_) => setState(() => _soAbaixo = false),
                  ),
                  ChoiceChip(
                    label: Text('Abaixo do mínimo (${freq.abaixo})'),
                    selected: _soAbaixo,
                    onSelected: (_) => setState(() => _soAbaixo = true),
                  ),
                ]),
              ),
              Cartao(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: alunos.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('Nenhum aluno abaixo do mínimo.', style: TextStyle(color: Cores.textoSecundario)),
                      )
                    : Column(children: [for (final aluno in alunos) _linha(aluno, freq)]),
              ),
            ],
          );
        },
      ),
    );
  }
}
