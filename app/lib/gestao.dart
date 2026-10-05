// LivePresenceAI - Gestão de turmas e alunos, histórico de aulas e exportação do relatório.
// Parte da biblioteca de main.dart (compartilha modelos, utilitários e o tema).

part of 'main.dart';

const _meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

/// "1 aula", "2 aulas" (plural simples, acrescentando "s").
String _qtd(int n, String singular) => '$n ${n == 1 ? singular : '${singular}s'}';

String _formatarData(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

String _formatarHoraMinuto(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

void _avisar(BuildContext context, String mensagem) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(mensagem)));
}

Future<bool> _confirmar(BuildContext context, String titulo, String texto, {String acao = 'Excluir'}) async {
  final resposta = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(titulo),
      content: Text(texto, style: const TextStyle(color: Cores.textoSecundario, fontSize: 15)),
      actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          style: FilledButton.styleFrom(backgroundColor: acao == 'Encerrar' || acao.startsWith('Exclu') || acao == 'Apagar'
              ? Cores.vermelho
              : Cores.azul),
          child: Text(acao),
        ),
      ],
    ),
  );
  return resposta ?? false;
}

/// Opções de um item em folha inferior (como o menu "..." dos apps da Meta).
Future<String?> _menuOpcoes(BuildContext context, String titulo, List<(String, IconData, String, bool)> opcoes) {
  return showModalBottomSheet<String>(
    context: context,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Text(titulo, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
          ),
          for (final (valor, icone, texto, perigo) in opcoes)
            ListTile(
              leading: CircleAvatar(
                backgroundColor: perigo ? Cores.vermelhoClaro : Cores.cinzaBotao,
                child: Icon(icone, color: perigo ? Cores.vermelho : Cores.texto, size: 21),
              ),
              title: Text(texto, style: TextStyle(color: perigo ? Cores.vermelho : Cores.texto)),
              onTap: () => Navigator.pop(context, valor),
            ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}

// ---------------------- MODELOS DA GESTÃO ----------------------

class AlunoCadastro {
  final int id;
  final String nome;
  final String? ra;
  final bool cadastroFacial;
  /// O aluno autorizou o reconhecimento facial no termo assinado na matrícula.
  final bool autorizacaoBiometrica;

  AlunoCadastro({
    required this.id,
    required this.nome,
    this.ra,
    this.cadastroFacial = false,
    this.autorizacaoBiometrica = false,
  });

  factory AlunoCadastro.fromJson(Map<String, dynamic> json) => AlunoCadastro(
        id: json['id'] as int,
        nome: json['nome'] as String,
        ra: json['ra'] as String?,
        cadastroFacial: json['cadastro_facial'] as bool? ?? false,
        autorizacaoBiometrica: json['autorizacao_biometrica'] as bool? ?? false,
      );
}

class AulaResumo {
  final int id;
  final String status;
  final DateTime inicio;
  final DateTime? fim;
  final Duration? duracao;
  final int totalPresencas;
  final int totalFaltas;

  AulaResumo({
    required this.id,
    required this.status,
    required this.inicio,
    this.fim,
    this.duracao,
    this.totalPresencas = 0,
    this.totalFaltas = 0,
  });

  bool get encerrada => status == 'encerrada';

  factory AulaResumo.fromJson(Map<String, dynamic> json) => AulaResumo(
        id: json['id'] as int,
        status: json['status'] as String,
        inicio: _lerHorarioUtc(json['inicio'] as String),
        fim: json['fim'] != null ? _lerHorarioUtc(json['fim'] as String) : null,
        duracao: json['duracao_segundos'] != null ? _segundos(json['duracao_segundos']) : null,
        totalPresencas: json['total_presencas'] as int? ?? 0,
        totalFaltas: json['total_faltas'] as int? ?? 0,
      );
}

// ---------------------- MINHAS TURMAS ----------------------

class SelecaoTurmaScreen extends StatefulWidget {
  const SelecaoTurmaScreen({super.key});
  @override
  State<SelecaoTurmaScreen> createState() => _SelecaoTurmaScreenState();
}

class _SelecaoTurmaScreenState extends State<SelecaoTurmaScreen> {
  late Future<List<Turma>> _futuroTurmas;

  @override
  void initState() {
    super.initState();
    _futuroTurmas = _carregarTurmas();
  }

  Future<List<Turma>> _carregarTurmas() async {
    final dados = await ApiService.listarTurmas();
    return dados.map(Turma.fromJson).toList();
  }

  void _recarregar() => setState(() => _futuroTurmas = _carregarTurmas());

  Future<void> _sair() async {
    await ApiService.logout();
    _usuario = null;
    if (!mounted) return;
    Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  Future<void> _abrir(Widget tela) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => tela));
    if (mounted) _recarregar(); // totais de alunos e aulas podem ter mudado
  }

  Future<void> _editarTurma([Turma? turma]) async {
    final dados = await _pedirDadosTurma(context, turma);
    if (dados == null) return;
    try {
      if (turma == null) {
        await ApiService.criarTurma(dados.$1, dados.$2);
      } else {
        await ApiService.editarTurma(turma.id, dados.$1, dados.$2);
      }
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Future<void> _excluirTurma(Turma turma) async {
    if (turma.totalAulas > 0) {
      _avisar(context, 'Turma com aulas registradas não pode ser excluída (o histórico é preservado).');
      return;
    }
    final ok = await _confirmar(context, 'Excluir turma?',
        '"${turma.nome}" e os ${turma.totalAlunos} aluno(s) dela serão excluídos. Esta ação não pode ser desfeita.');
    if (!ok) return;
    try {
      await ApiService.excluirTurma(turma.id);
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  /// Turma com sala padrão: abre direto nela. Sem sala padrão: pergunta a sala (ou "sem câmera").
  Future<void> _iniciarChamada(Turma turma) async {
    if (turma.salaId != null) {
      return _abrir(ChamadaAtivaScreen(turma: turma));
    }
    final (escolheu, salaId) = await _escolherSala(context);
    if (escolheu && mounted) _abrir(ChamadaAtivaScreen(turma: turma, salaId: salaId));
  }

  Future<void> _opcoesTurma(Turma turma) async {
    final escolha = await _menuOpcoes(context, turma.nome, [
      ('renomear', Icons.edit_outlined, 'Editar turma (nome e sala)', false),
      ('excluir', Icons.delete_outline, 'Excluir turma', true),
    ]);
    if (escolha == 'renomear') _editarTurma(turma);
    if (escolha == 'excluir') _excluirTurma(turma);
  }

  Widget _cartaoTurma(Turma turma) {
    final cor = Cores.avatares[turma.nome.codeUnits.fold<int>(0, (a, b) => a + b) % Cores.avatares.length];
    return Cartao(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Faixa colorida no topo, como a capa dos grupos do Facebook
          Container(
            height: 56,
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: [cor, cor.withValues(alpha: 0.65)]),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 8, 0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Transform.translate(
                  offset: const Offset(0, -18),
                  child: Container(
                    padding: const EdgeInsets.all(3),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16)),
                    child: Container(
                      width: 52,
                      height: 52,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: cor, borderRadius: BorderRadius.circular(13)),
                      child: Text(iniciais(turma.nome),
                          style: const TextStyle(color: Colors.white, fontSize: 19, fontWeight: FontWeight.w800)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(turma.nome,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                        Text('${_qtd(turma.totalAlunos, 'aluno')} · ${_qtd(turma.totalAulas, 'aula')}'
                            '${turma.salaNome != null ? ' · ${turma.salaNome}' : ''}',
                            style: const TextStyle(color: Cores.textoSecundario, fontSize: 13.5)),
                      ],
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Mais opções',
                  icon: const Icon(Icons.more_horiz, color: Cores.textoSecundario),
                  onPressed: () => _opcoesTurma(turma),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                FilledButton.icon(
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: const Text('Iniciar chamada'),
                  onPressed: () => _iniciarChamada(turma),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.people_alt_outlined, size: 20),
                      label: const Text('Alunos'),
                      onPressed: () => _abrir(GestaoAlunosScreen(turma: turma)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.history_rounded, size: 20),
                      label: const Text('Histórico'),
                      onPressed: () => _abrir(HistoricoScreen(turma: turma)),
                    ),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Marca(),
        actions: [
          BotaoCirculo(icone: Icons.add, dica: 'Nova turma', onPressed: () => _editarTurma()),
          BotaoCirculo(icone: Icons.refresh, dica: 'Atualizar', onPressed: _recarregar),
          Padding(
            padding: const EdgeInsets.only(left: 4, right: 12),
            child: Tooltip(
              message: 'Minha conta',
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: () => _abrirMinhaConta(context,
                    onSair: _sair,
                    onAdministracao: () => _abrir(const AdministracaoScreen())),
                child: Avatar(nome: _usuario?['nome'] as String? ?? '?', tamanho: 40),
              ),
            ),
          ),
        ],
      ),
      body: FutureBuilder<List<Turma>>(
        future: _futuroTurmas,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _MensagemErro(
                mensagem: snapshot.error.toString(), onTentarNovamente: _recarregar, onSair: _sair);
          }
          final turmas = snapshot.data ?? [];
          if (turmas.isEmpty) {
            return EstadoVazio(
              icone: Icons.class_outlined,
              titulo: 'Nenhuma turma ainda',
              texto: 'Crie sua primeira turma para cadastrar os alunos e começar a chamada.',
              acao: FilledButton.icon(
                  icon: const Icon(Icons.add), label: const Text('Criar turma'), onPressed: () => _editarTurma()),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _recarregar(),
            child: ListView(
              padding: const EdgeInsets.only(top: 6, bottom: 24),
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(16, 10, 16, 4),
                  child: Text('Suas turmas', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                ),
                ...turmas.map(_cartaoTurma),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Nome e sala padrão da turma; null se cancelado.
Future<(String, int?)?> _pedirDadosTurma(BuildContext context, Turma? turma) async {
  List<Map<String, dynamic>> salas = [];
  try {
    salas = await ApiService.listarSalas();
  } on ApiException {
    // sem salas, a turma fica sem sala padrão
  }
  if (!context.mounted) return null;
  final controle = TextEditingController(text: turma?.nome);
  int? salaId = turma?.salaId;
  return showDialog<(String, int?)>(
    context: context,
    builder: (contexto) => StatefulBuilder(
      builder: (contexto, atualizar) => AlertDialog(
        title: Text(turma == null ? 'Nova turma' : 'Editar turma'),
        content: SizedBox(
          width: 360,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
              controller: controle,
              autofocus: true,
              maxLength: 100,
              decoration: const InputDecoration(hintText: 'Ex.: CC7P68 - Engenharia de Software', counterText: ''),
            ),
            if (salas.isNotEmpty) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<int?>(
                initialValue: salas.any((s) => s['id'] == salaId) ? salaId : null,
                decoration: const InputDecoration(hintText: 'Sala padrão'),
                borderRadius: BorderRadius.circular(12),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('Perguntar ao iniciar a chamada')),
                  for (final sala in salas)
                    DropdownMenuItem<int?>(value: sala['id'] as int, child: Text(sala['nome'] as String)),
                ],
                onChanged: (v) => atualizar(() => salaId = v),
              ),
            ],
          ]),
        ),
        actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        actions: [
          TextButton(onPressed: () => Navigator.pop(contexto), child: const Text('Cancelar')),
          FilledButton(
            onPressed: () {
              final nome = controle.text.trim();
              Navigator.pop(contexto, nome.isEmpty ? null : (nome, salaId));
            },
            child: const Text('Salvar'),
          ),
        ],
      ),
    ),
  );
}

// ---------------------- GESTÃO DE ALUNOS (SALA) ----------------------

class GestaoAlunosScreen extends StatefulWidget {
  final Turma turma;
  const GestaoAlunosScreen({super.key, required this.turma});
  @override
  State<GestaoAlunosScreen> createState() => _GestaoAlunosScreenState();
}

class _GestaoAlunosScreenState extends State<GestaoAlunosScreen> {
  late Future<List<AlunoCadastro>> _futuroAlunos;
  String _busca = '';

  @override
  void initState() {
    super.initState();
    _futuroAlunos = _carregar();
  }

  Future<List<AlunoCadastro>> _carregar() async =>
      (await ApiService.listarAlunos(widget.turma.id)).map(AlunoCadastro.fromJson).toList();

  void _recarregar() => setState(() => _futuroAlunos = _carregar());

  Future<void> _editarAluno([AlunoCadastro? aluno]) async {
    final salvo = await showDialog<bool>(
      context: context,
      builder: (_) => _DialogoAluno(turma: widget.turma, aluno: aluno),
    );
    if (salvo == true) _recarregar();
  }

  Future<void> _cadastrarRosto(AlunoCadastro aluno) async {
    if (!aluno.autorizacaoBiometrica) {
      _avisar(context, '${aluno.nome} não autorizou o reconhecimento facial na matrícula. '
          'Se o termo foi assinado, edite o aluno e marque a autorização.');
      return;
    }
    final cadastrou = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => CadastroRostoScreen(aluno: aluno)),
    );
    if (cadastrou == true) _recarregar();
  }

  Future<void> _excluirRosto(AlunoCadastro aluno) async {
    final ok = await _confirmar(context, 'Apagar cadastro facial?',
        'O rosto cadastrado de ${aluno.nome} será apagado. A autorização continua registrada e o rosto pode ser '
        'cadastrado de novo.',
        acao: 'Apagar');
    if (!ok) return;
    try {
      await ApiService.excluirRosto(aluno.id);
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Future<void> _excluirAluno(AlunoCadastro aluno) async {
    final ok = await _confirmar(context, 'Excluir aluno?',
        '${aluno.nome}${aluno.ra != null ? ' (RA ${aluno.ra})' : ''} será excluído. O cadastro facial também é apagado.');
    if (!ok) return;
    try {
      await ApiService.excluirAluno(aluno.id);
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Future<void> _opcoesAluno(AlunoCadastro aluno) async {
    final escolha = await _menuOpcoes(context, aluno.nome, [
      if (aluno.autorizacaoBiometrica)
        ('rosto', Icons.face_retouching_natural,
            aluno.cadastroFacial ? 'Refazer cadastro facial' : 'Cadastrar rosto', false),
      ('editar', Icons.edit_outlined, 'Editar dados', false),
      if (aluno.cadastroFacial) ('apagar_rosto', Icons.no_photography_outlined, 'Apagar cadastro facial', true),
      ('excluir', Icons.person_remove_outlined, 'Excluir aluno', true),
    ]);
    switch (escolha) {
      case 'rosto':
        _cadastrarRosto(aluno);
      case 'editar':
        _editarAluno(aluno);
      case 'apagar_rosto':
        _excluirRosto(aluno);
      case 'excluir':
        _excluirAluno(aluno);
    }
  }

  Widget _linha(AlunoCadastro aluno) {
    // Selo no avatar: rosto cadastrado (verde), autorizado sem rosto (azul), sem autorização (cinza)
    final Selo selo = aluno.cadastroFacial
        ? const Selo(icone: Icons.check, cor: Cores.verde)
        : aluno.autorizacaoBiometrica
            ? const Selo(icone: Icons.camera_alt, cor: Cores.azul)
            : const Selo(icone: Icons.block, cor: Color(0xFFBCC0C4));
    final situacao = aluno.cadastroFacial
        ? 'rosto cadastrado'
        : aluno.autorizacaoBiometrica
            ? 'falta o rosto'
            : 'sem autorização';
    return ListTile(
      contentPadding: const EdgeInsets.fromLTRB(16, 4, 8, 4),
      leading: Avatar(nome: aluno.nome, selo: selo),
      title: Text(aluno.nome),
      subtitle: Text.rich(TextSpan(children: [
        aluno.ra != null
            ? TextSpan(text: 'RA ${aluno.ra}')
            : const TextSpan(text: 'RA não informado', style: TextStyle(color: Cores.ambar)),
        TextSpan(text: ' · $situacao'),
      ])),
      trailing: aluno.autorizacaoBiometrica && !aluno.cadastroFacial
          ? TextButton(onPressed: () => _cadastrarRosto(aluno), child: const Text('Cadastrar'))
          : IconButton(
              tooltip: 'Opções',
              icon: const Icon(Icons.more_horiz, color: Cores.textoSecundario),
              onPressed: () => _opcoesAluno(aluno),
            ),
      onTap: () => _opcoesAluno(aluno),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: TituloTela('Alunos', subtitulo: widget.turma.nome),
        actions: [
          BotaoCirculo(icone: Icons.person_add_alt_1, dica: 'Novo aluno', onPressed: () => _editarAluno()),
          const SizedBox(width: 8),
        ],
      ),
      body: FutureBuilder<List<AlunoCadastro>>(
        future: _futuroAlunos,
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
          final todos = snapshot.data ?? [];
          if (todos.isEmpty) {
            return EstadoVazio(
              icone: Icons.group_add_outlined,
              titulo: 'Nenhum aluno nesta turma',
              texto: 'Cadastre os alunos com nome e RA. Depois, cadastre o rosto de quem autorizou.',
              acao: FilledButton.icon(
                  icon: const Icon(Icons.person_add_alt_1),
                  label: const Text('Adicionar aluno'),
                  onPressed: () => _editarAluno()),
            );
          }
          final termo = _busca.toLowerCase();
          final alunos = todos
              .where((a) => a.nome.toLowerCase().contains(termo) || (a.ra ?? '').toLowerCase().contains(termo))
              .toList();
          final comRosto = todos.where((a) => a.cadastroFacial).length;
          final pendentes = todos.where((a) => a.autorizacaoBiometrica && !a.cadastroFacial).length;
          final semAutorizacao = todos.where((a) => !a.autorizacaoBiometrica).length;
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              Container(
                color: Cores.superficie,
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      decoration: InputDecoration(
                        prefixIcon: const Icon(Icons.search, color: Cores.textoSecundario),
                        hintText: 'Buscar por nome ou RA',
                        isDense: true,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                        enabledBorder:
                            OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
                      ),
                      onChanged: (texto) => setState(() => _busca = texto),
                    ),
                    const SizedBox(height: 12),
                    Wrap(spacing: 8, runSpacing: 6, children: [
                      Etiqueta(texto: _qtd(todos.length, 'aluno'), cor: Cores.texto, fundo: Cores.cinzaBotao),
                      Etiqueta(
                          texto: '$comRosto com rosto', cor: Cores.verde, fundo: Cores.verdeClaro, icone: Icons.check),
                      if (pendentes > 0)
                        Etiqueta(
                            texto: '$pendentes para cadastrar',
                            cor: Cores.azul,
                            fundo: Cores.azulClaro,
                            icone: Icons.camera_alt),
                      if (semAutorizacao > 0)
                        Etiqueta(
                            texto: '$semAutorizacao sem autorização',
                            cor: Cores.textoSecundario,
                            fundo: Cores.fundo,
                            icone: Icons.block),
                    ]),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Cartao(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: alunos.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(24),
                        child: Text('Nenhum aluno encontrado.', textAlign: TextAlign.center),
                      )
                    : Column(children: [
                        for (var i = 0; i < alunos.length; i++) ...[
                          if (i > 0) const Divider(indent: 72),
                          _linha(alunos[i]),
                        ],
                      ]),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _DialogoAluno extends StatefulWidget {
  final Turma turma;
  final AlunoCadastro? aluno;
  const _DialogoAluno({required this.turma, this.aluno});
  @override
  State<_DialogoAluno> createState() => _DialogoAlunoState();
}

class _DialogoAlunoState extends State<_DialogoAluno> {
  final _formulario = GlobalKey<FormState>();
  late final _nome = TextEditingController(text: widget.aluno?.nome);
  late final _ra = TextEditingController(text: widget.aluno?.ra);
  late bool _autorizou = widget.aluno?.autorizacaoBiometrica ?? false;
  bool _salvando = false;
  String? _erro;

  Future<void> _salvar() async {
    if (!_formulario.currentState!.validate()) return;
    setState(() {
      _salvando = true;
      _erro = null;
    });
    try {
      final nome = _nome.text.trim();
      final ra = _ra.text.trim().toUpperCase();
      if (widget.aluno == null) {
        await ApiService.criarAluno(widget.turma.id, nome, ra, _autorizou);
      } else {
        await ApiService.editarAluno(widget.aluno!.id, nome, ra, _autorizou);
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _erro = e.mensagem);
    } finally {
      if (mounted) setState(() => _salvando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final vaiApagarRosto = !_autorizou && (widget.aluno?.cadastroFacial ?? false);
    return AlertDialog(
      title: Text(widget.aluno == null ? 'Novo aluno' : 'Editar aluno'),
      content: SizedBox(
        width: 360,
        child: Form(
          key: _formulario,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _nome,
                autofocus: true,
                maxLength: 150,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(hintText: 'Nome completo', counterText: ''),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Informe o nome' : null,
              ),
              const SizedBox(height: 10),
              TextFormField(
                controller: _ra,
                maxLength: 20,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(hintText: 'RA (ex.: N0532D0)', counterText: ''),
                validator: (v) {
                  final ra = (v ?? '').trim();
                  if (ra.isEmpty) return 'Informe o RA';
                  if (!RegExp(r'^[A-Za-z0-9-]{1,20}$').hasMatch(ra)) return 'Use letras, números ou hífen';
                  return null;
                },
                onFieldSubmitted: (_) => _salvar(),
              ),
              const SizedBox(height: 10),
              Container(
                decoration: BoxDecoration(color: Cores.fundo, borderRadius: BorderRadius.circular(12)),
                child: SwitchListTile(
                  value: _autorizou,
                  onChanged: (v) => setState(() => _autorizou = v),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  title: const Text('Autorizou o reconhecimento facial', style: TextStyle(fontSize: 15)),
                  subtitle: Text(
                    vaiApagarRosto ? 'Ao salvar, o rosto cadastrado será apagado.' : 'Conforme o termo da matrícula.',
                    style: TextStyle(color: vaiApagarRosto ? Cores.vermelho : Cores.textoSecundario, fontSize: 12.5),
                  ),
                ),
              ),
              if (_erro != null)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(_erro!, style: const TextStyle(color: Cores.vermelho)),
                ),
            ],
          ),
        ),
      ),
      actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      actions: [
        TextButton(onPressed: _salvando ? null : () => Navigator.pop(context, false), child: const Text('Cancelar')),
        FilledButton(
          onPressed: _salvando ? null : _salvar,
          child: _salvando
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Salvar'),
        ),
      ],
    );
  }
}

// ---------------------- HISTÓRICO DE AULAS ----------------------

class HistoricoScreen extends StatefulWidget {
  final Turma turma;
  const HistoricoScreen({super.key, required this.turma});
  @override
  State<HistoricoScreen> createState() => _HistoricoScreenState();
}

class _HistoricoScreenState extends State<HistoricoScreen> {
  late Future<List<AulaResumo>> _futuroAulas;

  @override
  void initState() {
    super.initState();
    _futuroAulas = _carregar();
  }

  Future<List<AulaResumo>> _carregar() async =>
      (await ApiService.historico(widget.turma.id)).map(AulaResumo.fromJson).toList();

  void _recarregar() => setState(() => _futuroAulas = _carregar());

  Future<void> _abrirRelatorio(AulaResumo aula) async {
    if (!aula.encerrada) {
      _avisar(context, 'Esta chamada ainda está aberta. Encerre-a pela tela de chamada para ver o relatório.');
      return;
    }
    try {
      final relatorio = Relatorio.fromJson(await ApiService.relatorio(aula.id));
      if (!mounted) return;
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => RelatorioScreen(
              turma: widget.turma, sessaoId: aula.id, relatorio: relatorio, doHistorico: true),
        ),
      );
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Widget _cartaoAula(AulaResumo aula) {
    final total = aula.totalPresencas + aula.totalFaltas;
    return Cartao(
      onTap: () => _abrirRelatorio(aula),
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          // Bloco de data, como um calendário
          Container(
            width: 54,
            padding: const EdgeInsets.symmetric(vertical: 6),
            decoration: BoxDecoration(
              color: aula.encerrada ? Cores.azulClaro : Cores.vermelhoClaro,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(children: [
              Text(_meses[aula.inicio.month - 1].toUpperCase(),
                  style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w800,
                      color: aula.encerrada ? Cores.azul : Cores.vermelho)),
              Text('${aula.inicio.day}',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Cores.texto)),
            ]),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Text(
                    aula.fim != null
                        ? '${_formatarHoraMinuto(aula.inicio)} – ${_formatarHoraMinuto(aula.fim!)}'
                        : 'Desde ${_formatarHoraMinuto(aula.inicio)}',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(width: 8),
                  if (!aula.encerrada) const AoVivo(),
                ]),
                const SizedBox(height: 2),
                Text(
                  aula.encerrada
                      ? '${_qtd(aula.totalPresencas, 'presença')} · ${_qtd(aula.totalFaltas, 'falta')} · '
                          '${_formatarDuracao(aula.duracao ?? Duration.zero)}'
                      : 'Chamada em andamento',
                  style: const TextStyle(color: Cores.textoSecundario, fontSize: 13.5),
                ),
                if (aula.encerrada && total > 0) ...[
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: aula.totalPresencas / total,
                      minHeight: 5,
                      color: Cores.verde,
                      backgroundColor: Cores.vermelhoClaro,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: Cores.textoSecundario),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: TituloTela('Histórico', subtitulo: widget.turma.nome),
        actions: [
          BotaoCirculo(icone: Icons.refresh, dica: 'Atualizar', onPressed: _recarregar),
          const SizedBox(width: 8),
        ],
      ),
      body: FutureBuilder<List<AulaResumo>>(
        future: _futuroAulas,
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
          final aulas = snapshot.data ?? [];
          if (aulas.isEmpty) {
            return const EstadoVazio(
              icone: Icons.event_note_outlined,
              titulo: 'Nenhuma aula ainda',
              texto: 'As chamadas encerradas desta turma aparecem aqui, com o relatório de cada uma.',
            );
          }
          // Agrupa por mês, do mais recente para o mais antigo
          final itens = <Widget>[];
          String? mesAtual;
          for (final aula in aulas) {
            final mes = '${_meses[aula.inicio.month - 1]} de ${aula.inicio.year}';
            if (mes != mesAtual) {
              mesAtual = mes;
              itens.add(Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
                child: Text(mes[0].toUpperCase() + mes.substring(1),
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: Cores.textoSecundario)),
              ));
            }
            itens.add(_cartaoAula(aula));
          }
          return ListView(padding: const EdgeInsets.only(bottom: 24), children: itens);
        },
      ),
    );
  }
}

// ---------------------- EXPORTAÇÃO ----------------------

class _BotaoExportar extends StatefulWidget {
  final int sessaoId;
  const _BotaoExportar({required this.sessaoId});
  @override
  State<_BotaoExportar> createState() => _BotaoExportarState();
}

class _BotaoExportarState extends State<_BotaoExportar> {
  bool _exportando = false;

  Future<void> _escolherFormato() async {
    final formato = await _menuOpcoes(context, 'Exportar relatório', [
      ('pdf', Icons.picture_as_pdf_outlined, 'PDF', false),
      ('xlsx', Icons.grid_on_outlined, 'Planilha do Excel (XLSX)', false),
      ('csv', Icons.description_outlined, 'CSV', false),
    ]);
    if (formato != null) _exportar(formato);
  }

  Future<void> _exportar(String formato) async {
    setState(() => _exportando = true);
    try {
      final arquivo = await ApiService.exportar(widget.sessaoId, formato);
      final mensagem = await entregarArquivo(arquivo.bytes, arquivo.nome, arquivo.tipo);
      if (mounted) _avisar(context, mensagem);
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    } catch (e) {
      if (mounted) _avisar(context, 'Não foi possível salvar o arquivo: $e');
    } finally {
      if (mounted) setState(() => _exportando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_exportando) {
      return const Padding(
        padding: EdgeInsets.all(12),
        child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      );
    }
    return BotaoCirculo(icone: Icons.ios_share, dica: 'Exportar', onPressed: _escolherFormato);
  }
}
