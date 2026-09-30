// LivePresenceAI - App Mobile (Flutter)
// Dia 2 / Etapa 5: encerramento real da sessão e relatório vindo do backend.
// Fluxo completo: login -> turmas -> sessão -> tempo real -> relatório.

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_service.dart';
import 'config.dart';

void main() {
  runApp(const LivePresenceApp());
}

class LivePresenceApp extends StatelessWidget {
  const LivePresenceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LivePresenceAI',
      theme: ThemeData(primarySwatch: Colors.indigo, useMaterial3: true),
      home: const LoginScreen(),
    );
  }
}

// ---------------------- UTILITÁRIOS ----------------------

/// O backend envia horários em UTC sem sufixo; acrescenta 'Z' e converte para o fuso local.
DateTime _lerHorarioUtc(String texto) {
  final normalizado = texto.endsWith('Z') ? texto : '${texto}Z';
  return DateTime.parse(normalizado).toLocal();
}

String _formatarDuracao(Duration d) {
  final horas = d.inHours;
  final minutos = d.inMinutes.remainder(60).toString().padLeft(2, '0');
  final segundos = d.inSeconds.remainder(60).toString().padLeft(2, '0');
  return horas > 0 ? '$horas:$minutos:$segundos' : '$minutos:$segundos';
}

String _formatarHora(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}:${d.second.toString().padLeft(2, '0')}';

// ---------------------- MODELOS ----------------------
class Turma {
  final int id;
  final String nome;

  Turma({required this.id, required this.nome});

  factory Turma.fromJson(Map<String, dynamic> json) =>
      Turma(id: json['id'] as int, nome: json['nome'] as String);
}

class Aluno {
  final int id;
  final String nome;
  String status; // 'ausente' | 'presente' (já detectado na sessão)
  DateTime? entrada;
  DateTime? ultimaVisualizacao;
  /// Tempo acumulado calculado pelo backend até a última detecção.
  Duration tempoAcumulado = Duration.zero;

  Aluno({required this.id, required this.nome, this.status = 'ausente'});

  factory Aluno.fromJson(Map<String, dynamic> json) =>
      Aluno(id: json['id'] as int, nome: json['nome'] as String);

  /// Aplica o estado vindo do backend (registro da sessão ou evento do WebSocket).
  void aplicarDeteccao({
    required DateTime entrada,
    required DateTime ultimaVisualizacao,
    required Duration tempoAcumulado,
  }) {
    status = 'presente';
    this.entrada = entrada;
    this.ultimaVisualizacao = ultimaVisualizacao;
    this.tempoAcumulado = tempoAcumulado;
  }

  /// Visto há no máximo [limite] (mesma regra RN-02 do backend).
  bool naSala(DateTime agora, Duration limite) =>
      ultimaVisualizacao != null && agora.difference(ultimaVisualizacao!) <= limite;

  /// Estimativa ao vivo, apenas para exibição: o valor oficial é calculado pelo backend ao encerrar.
  Duration permanenciaParcial(DateTime agora, Duration limite) =>
      naSala(agora, limite) ? tempoAcumulado + agora.difference(ultimaVisualizacao!) : tempoAcumulado;
}

Duration _segundos(dynamic valor) =>
    Duration(milliseconds: (((valor as num?) ?? 0) * 1000).round());

/// Linha do relatório devolvida por POST /sessoes/{id}/encerrar (campo 'alunos').
/// A situação (presença/falta, RN-03) é decidida pelo backend.
class SituacaoAluno {
  final int alunoId;
  final String nome;
  final bool detectado;
  final DateTime? entrada;
  /// Tempo acumulado calculado pelo backend (desconta os períodos em que o aluno saiu).
  final Duration permanencia;
  final double percentual;
  final String situacao; // 'presenca' | 'falta'

  SituacaoAluno({
    required this.alunoId,
    required this.nome,
    required this.detectado,
    required this.entrada,
    required this.permanencia,
    required this.percentual,
    required this.situacao,
  });

  bool get presente => situacao == 'presenca';

  factory SituacaoAluno.fromJson(Map<String, dynamic> json) => SituacaoAluno(
        alunoId: json['aluno_id'] as int,
        nome: json['nome'] as String,
        detectado: json['detectado'] as bool,
        entrada: json['entrada'] != null ? _lerHorarioUtc(json['entrada'] as String) : null,
        permanencia: _segundos(json['tempo_total_presente']),
        percentual: (json['percentual_presenca'] as num?)?.toDouble() ?? 0.0,
        situacao: json['situacao'] as String,
      );
}

/// Relatório final da sessão, calculado pelo servidor.
class Relatorio {
  final double frequenciaMinima;
  final int totalPresencas;
  final int totalFaltas;
  final List<SituacaoAluno> alunos;

  Relatorio({
    required this.frequenciaMinima,
    required this.totalPresencas,
    required this.totalFaltas,
    required this.alunos,
  });

  factory Relatorio.fromJson(Map<String, dynamic> json) => Relatorio(
        frequenciaMinima: (json['frequencia_minima'] as num).toDouble(),
        totalPresencas: json['total_presencas'] as int,
        totalFaltas: json['total_faltas'] as int,
        alunos: (json['alunos'] as List<dynamic>)
            .map((item) => SituacaoAluno.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

// ---------------------- LOGIN ----------------------
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController(text: 'professor@livepresenceai.com');
  final _senhaController = TextEditingController(text: 'senha123');
  bool _carregando = false;
  String? _erro;

  Future<void> _fazerLogin() async {
    setState(() {
      _carregando = true;
      _erro = null;
    });

    try {
      await ApiService.login(
        _emailController.text.trim(),
        _senhaController.text,
      );
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const SelecaoTurmaScreen()),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.mensagem);
    } finally {
      if (mounted) setState(() => _carregando = false);
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _senhaController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('LivePresenceAI - Login')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                TextField(
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'E-mail do professor'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _senhaController,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Senha'),
                  onSubmitted: (_) => _fazerLogin(),
                ),
                const SizedBox(height: 16),
                if (_erro != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      _erro!,
                      style: const TextStyle(color: Colors.red),
                      textAlign: TextAlign.center,
                    ),
                  ),
                _carregando
                    ? const CircularProgressIndicator()
                    : ElevatedButton(
                        onPressed: _fazerLogin,
                        child: const Text('Entrar'),
                      ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------- SELEÇÃO DE TURMA ----------------------
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

  void _recarregar() {
    setState(() => _futuroTurmas = _carregarTurmas());
  }

  Future<void> _sair() async {
    await ApiService.logout();
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Selecione a turma'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Atualizar',
            onPressed: _recarregar,
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sair',
            onPressed: _sair,
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
              mensagem: snapshot.error.toString(),
              onTentarNovamente: _recarregar,
              onSair: _sair,
            );
          }

          final turmas = snapshot.data ?? [];
          if (turmas.isEmpty) {
            return const Center(child: Text('Nenhuma turma cadastrada.'));
          }

          return ListView.builder(
            itemCount: turmas.length,
            itemBuilder: (context, index) {
              final turma = turmas[index];
              return ListTile(
                leading: const Icon(Icons.groups),
                title: Text(turma.nome),
                trailing: const Icon(Icons.arrow_forward_ios),
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => ChamadaAtivaScreen(turma: turma),
                    ),
                  );
                },
              );
            },
          );
        },
      ),
    );
  }
}

class _MensagemErro extends StatelessWidget {
  final String mensagem;
  final VoidCallback onTentarNovamente;
  final VoidCallback onSair;
  final String textoSair;

  const _MensagemErro({
    required this.mensagem,
    required this.onTentarNovamente,
    required this.onSair,
    this.textoSair = 'Voltar ao login',
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 48),
            const SizedBox(height: 12),
            Text(mensagem, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              children: [
                ElevatedButton(
                  onPressed: onTentarNovamente,
                  child: const Text('Tentar novamente'),
                ),
                OutlinedButton(
                  onPressed: onSair,
                  child: Text(textoSair),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------- CHAMADA ATIVA ----------------------
class ChamadaAtivaScreen extends StatefulWidget {
  final Turma turma;
  const ChamadaAtivaScreen({super.key, required this.turma});
  @override
  State<ChamadaAtivaScreen> createState() => _ChamadaAtivaScreenState();
}

class _ChamadaAtivaScreenState extends State<ChamadaAtivaScreen> {
  List<Aluno> _alunos = [];
  bool _carregando = true;
  bool _encerrando = false;
  String? _erro;

  int? _sessaoId;
  DateTime? _inicioSessao;
  // Parâmetros das regras informados pelo backend (RN-02 e RN-03)
  Duration _limiteAusencia = Duration.zero;
  double? _frequenciaMinima;

  bool _tempoRealAtivo = false;
  bool _telaAtiva = true; // false ao sair da tela ou encerrar: para de reconectar
  int _tentativasReconexao = 0;
  WebSocketChannel? _canal;
  StreamSubscription? _assinatura;
  Timer? _timerReconexao;
  Timer? _relogio; // redesenha a tela a cada segundo para atualizar tempos ao vivo

  @override
  void initState() {
    super.initState();
    _iniciarChamada();
  }

  Future<void> _iniciarChamada() async {
    setState(() {
      _carregando = true;
      _erro = null;
    });

    try {
      final dadosAlunos = await ApiService.listarAlunos(widget.turma.id);
      final sessao = await ApiService.abrirSessao(widget.turma.id);
      if (!mounted) return;

      setState(() {
        _alunos = dadosAlunos.map(Aluno.fromJson).toList();
        _sessaoId = sessao['id'] as int;
        _inicioSessao = _lerHorarioUtc(sessao['inicio'] as String);
        _limiteAusencia = _segundos(sessao['limite_ausencia_segundos']);
        _frequenciaMinima = (sessao['frequencia_minima'] as num?)?.toDouble();
        // Sessão retomada: restaura quem já tinha sido detectado antes de sair da tela
        _aplicarRegistros(sessao['registros'] as List<dynamic>? ?? []);
        _carregando = false;
      });

      if (sessao['retomada'] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Chamada em andamento retomada (Sessão #${sessao['id']}).')),
        );
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = e.mensagem;
        _carregando = false;
      });
      return;
    }

    _relogio ??= Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    _conectarWebSocket();
  }

  /// Aplica a lista de registros da sessão (formato de RegistroPresencaOut do backend).
  void _aplicarRegistros(List<dynamic> registros) {
    for (final item in registros) {
      final registro = item as Map<String, dynamic>;
      for (final aluno in _alunos.where((a) => a.id == registro['aluno_id'])) {
        aluno.aplicarDeteccao(
          entrada: _lerHorarioUtc(registro['entrada'] as String),
          ultimaVisualizacao: _lerHorarioUtc(registro['ultima_visualizacao'] as String),
          tempoAcumulado: _segundos(registro['tempo_total_presente']),
        );
      }
    }
  }

  /// Busca o estado atual no backend (eventos perdidos enquanto o WebSocket estava fora).
  Future<void> _sincronizar() async {
    final sessaoId = _sessaoId;
    if (sessaoId == null) return;
    try {
      final sessao = await ApiService.consultarSessao(sessaoId);
      if (!mounted) return;
      setState(() => _aplicarRegistros(sessao['registros'] as List<dynamic>? ?? []));
    } on ApiException {
      // Mantém o estado atual; a próxima reconexão tenta de novo.
    }
  }

  Future<void> _conectarWebSocket({bool reconexao = false}) async {
    final sessaoId = _sessaoId;
    if (sessaoId == null || !_telaAtiva) return;

    try {
      final canal = WebSocketChannel.connect(
        Uri.parse('$wsBaseUrl/ws/sessoes/$sessaoId'),
      );
      await canal.ready;

      if (!mounted || !_telaAtiva) {
        canal.sink.close();
        return;
      }

      await _assinatura?.cancel();
      _canal?.sink.close();
      _canal = canal;
      _assinatura = canal.stream.listen(
        _tratarMensagem,
        onDone: _conexaoPerdida,
        onError: (_) => _conexaoPerdida(),
      );
      _tentativasReconexao = 0;
      setState(() => _tempoRealAtivo = true);

      if (reconexao) await _sincronizar();
    } catch (_) {
      _conexaoPerdida();
    }
  }

  void _conexaoPerdida() {
    if (!mounted || !_telaAtiva) return;
    setState(() => _tempoRealAtivo = false);
    _agendarReconexao();
  }

  /// Tenta reconectar com espera crescente (2 s, 4 s, ... até 10 s).
  void _agendarReconexao() {
    if (!mounted || !_telaAtiva || (_timerReconexao?.isActive ?? false)) return;
    _tentativasReconexao++;
    final espera = Duration(seconds: min(2 * _tentativasReconexao, 10));
    _timerReconexao = Timer(espera, () => _conectarWebSocket(reconexao: true));
  }

  void _tratarMensagem(dynamic mensagem) {
    final dados = jsonDecode(mensagem as String) as Map<String, dynamic>;
    final indice = _alunos.indexWhere((a) => a.id == dados['aluno_id']);
    if (indice == -1) return;

    final horario = _lerHorarioUtc(dados['horario'] as String);
    setState(() {
      _alunos[indice].aplicarDeteccao(
        entrada: dados['entrada'] != null ? _lerHorarioUtc(dados['entrada'] as String) : horario,
        ultimaVisualizacao: horario,
        tempoAcumulado: _segundos(dados['tempo_total_presente']),
      );
    });
  }

  Future<void> _simularReconhecimento() async {
    final sessaoId = _sessaoId;
    if (sessaoId == null) return;

    final ausentes = _alunos.where((a) => a.status == 'ausente').toList();
    if (ausentes.isEmpty) return;
    final alvo = ausentes.first;

    try {
      final registrado = await ApiService.reconhecer(sessaoId, alvo.id, 0.9);
      // Sem tempo real, o evento não chega pelo WebSocket: busca o estado no backend
      if (registrado && !_tempoRealAtivo) await _sincronizar();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.mensagem)),
      );
    }
  }

  /// Encerra a sessão no backend e abre o relatório calculado pelo servidor.
  Future<void> _encerrarChamada() async {
    final sessaoId = _sessaoId;
    if (sessaoId == null || _encerrando) return;

    setState(() => _encerrando = true);
    try {
      final relatorio = Relatorio.fromJson(await ApiService.encerrarSessao(sessaoId));

      if (!mounted) return;
      _pararTempoReal();
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => RelatorioScreen(
            turma: widget.turma,
            sessaoId: sessaoId,
            relatorio: relatorio,
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.mensagem)),
      );
    } finally {
      if (mounted) setState(() => _encerrando = false);
    }
  }

  void _pararTempoReal() {
    _telaAtiva = false;
    _timerReconexao?.cancel();
    _relogio?.cancel();
    _assinatura?.cancel();
    _canal?.sink.close();
  }

  @override
  void dispose() {
    _pararTempoReal();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reconectando = !_tempoRealAtivo && _sessaoId != null && !_carregando;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.turma.nome, style: const TextStyle(fontSize: 18)),
            Text(
              _sessaoId != null ? 'Sessão #$_sessaoId' : 'Abrindo sessão...',
              style: const TextStyle(fontSize: 12),
            ),
          ],
        ),
        actions: [
          Tooltip(
            message: _tempoRealAtivo ? 'Tempo real conectado' : 'Tempo real desconectado',
            child: Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Icon(
                _tempoRealAtivo ? Icons.cloud_done : Icons.cloud_sync,
                color: _tempoRealAtivo ? Colors.green : Colors.orange,
              ),
            ),
          ),
        ],
        bottom: reconectando
            ? const PreferredSize(
                preferredSize: Size.fromHeight(24),
                child: ColoredBox(
                  color: Colors.orange,
                  child: SizedBox(
                    height: 24,
                    width: double.infinity,
                    child: Center(
                      child: Text(
                        'Tempo real desconectado — reconectando...',
                        style: TextStyle(color: Colors.white, fontSize: 12),
                      ),
                    ),
                  ),
                ),
              )
            : null,
      ),
      body: _corpo(),
    );
  }

  Widget _linhaAluno(Aluno aluno, DateTime agora) {
    final entrada = aluno.entrada;
    if (entrada == null) {
      return ListTile(
        leading: const Icon(Icons.circle_outlined, color: Colors.grey),
        title: Text(aluno.nome),
        subtitle: const Text('Ainda não detectado'),
        onTap: () => _abrirDetalhes(aluno),
      );
    }

    final naSala = aluno.naSala(agora, _limiteAusencia);
    final permanencia = aluno.permanenciaParcial(agora, _limiteAusencia);
    final duracaoAula = agora.difference(_inicioSessao ?? entrada);
    final percentual = duracaoAula.inMilliseconds > 0
        ? min(100.0, permanencia.inMilliseconds / duracaoAula.inMilliseconds * 100)
        : 100.0;
    final abaixoDoMinimo = _frequenciaMinima != null && percentual < _frequenciaMinima!;

    final estado = naSala
        ? 'Na sala'
        : 'Fora da sala há ${_formatarDuracao(agora.difference(aluno.ultimaVisualizacao!))}';

    return ListTile(
      leading: Icon(
        naSala ? Icons.check_circle : Icons.directions_walk,
        color: naSala ? Colors.green : Colors.orange,
      ),
      title: Text(aluno.nome),
      subtitle: Text(
        '$estado • Entrada: ${_formatarHora(entrada)} • Permanência: ${_formatarDuracao(permanencia)}',
      ),
      trailing: Text(
        '${percentual.toStringAsFixed(0)}%',
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: abaixoDoMinimo ? Colors.red : null,
        ),
      ),
      onTap: () => _abrirDetalhes(aluno),
    );
  }

  void _abrirDetalhes(Aluno aluno) => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => DetalhesAlunoScreen(aluno: aluno)),
      );

  Widget _corpo() {
    if (_carregando) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_erro != null) {
      return _MensagemErro(
        mensagem: _erro!,
        onTentarNovamente: _iniciarChamada,
        onSair: () => Navigator.pop(context),
        textoSair: 'Voltar',
      );
    }

    if (_alunos.isEmpty) {
      return const Center(child: Text('Esta turma não tem alunos cadastrados.'));
    }

    final agora = DateTime.now();
    final naSala = _alunos.where((a) => a.naSala(agora, _limiteAusencia)).length;
    final detectados = _alunos.where((a) => a.status == 'presente').length;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          child: Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              Text(
                'Na sala: $naSala  •  Detectados: $detectados/${_alunos.length}',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              ElevatedButton.icon(
                onPressed: _simularReconhecimento,
                icon: const Icon(Icons.face),
                label: const Text('Simular reconhecimento'),
              ),
            ],
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(12, 4, 12, 4),
          child: Text(
            'Permanência e percentual parciais; os valores oficiais são calculados ao encerrar.',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: _alunos.length,
            itemBuilder: (context, index) => _linhaAluno(_alunos[index], agora),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: _encerrando
              ? const CircularProgressIndicator()
              : ElevatedButton(
                  onPressed: _encerrarChamada,
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                  child: const Text('Encerrar chamada'),
                ),
        ),
      ],
    );
  }
}

// ---------------------- DETALHES DO ALUNO ----------------------
class DetalhesAlunoScreen extends StatelessWidget {
  final Aluno aluno;
  const DetalhesAlunoScreen({super.key, required this.aluno});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(aluno.nome)),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Status: ${aluno.status}', style: const TextStyle(fontSize: 18)),
            const SizedBox(height: 12),
            Text('Entrada: ${aluno.entrada != null ? _formatarHora(aluno.entrada!) : "Não detectado"}'),
            const SizedBox(height: 12),
            Text(
              'Última visualização: ${aluno.ultimaVisualizacao != null ? _formatarHora(aluno.ultimaVisualizacao!) : "Não detectado"}',
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------- RELATÓRIO (vindo do backend) ----------------------
class RelatorioScreen extends StatelessWidget {
  final Turma turma;
  final int sessaoId;
  final Relatorio relatorio;

  const RelatorioScreen({
    super.key,
    required this.turma,
    required this.sessaoId,
    required this.relatorio,
  });

  Widget _linhaAluno(SituacaoAluno aluno) {
    final minimo = relatorio.frequenciaMinima.toStringAsFixed(0);

    final Icon icone;
    final String detalhe;
    if (aluno.presente) {
      icone = const Icon(Icons.check_circle, color: Colors.green);
      detalhe = 'Presença • Entrada: ${_formatarHora(aluno.entrada!)} • '
          'Permanência: ${_formatarDuracao(aluno.permanencia)}';
    } else if (aluno.detectado) {
      // Foi visto, mas ficou menos que o mínimo: falta registrada, dados guardados para auditoria
      icone = const Icon(Icons.warning_amber_rounded, color: Colors.orange);
      detalhe = 'Falta (abaixo de $minimo%) • Entrada: ${_formatarHora(aluno.entrada!)} • '
          'Permanência: ${_formatarDuracao(aluno.permanencia)}';
    } else {
      icone = const Icon(Icons.cancel, color: Colors.red);
      detalhe = 'Falta • Não detectado';
    }

    return ListTile(
      leading: icone,
      title: Text(aluno.nome),
      subtitle: Text(detalhe),
      trailing: Text(
        '${aluno.percentual.toStringAsFixed(1)}%',
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: aluno.presente ? null : Colors.red,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Relatório da sessão', style: TextStyle(fontSize: 18)),
            Text('${turma.nome} • Sessão #$sessaoId', style: const TextStyle(fontSize: 12)),
          ],
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              children: [
                Text(
                  'Presenças: ${relatorio.totalPresencas}  •  Faltas: ${relatorio.totalFaltas}',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 4),
                Text(
                  'Frequência mínima: ${relatorio.frequenciaMinima.toStringAsFixed(0)}% do tempo de aula',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: relatorio.alunos.length,
              itemBuilder: (context, index) => _linhaAluno(relatorio.alunos[index]),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: ElevatedButton(
              onPressed: () => Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const SelecaoTurmaScreen()),
                (rota) => false,
              ),
              child: const Text('Voltar às turmas'),
            ),
          ),
        ],
      ),
    );
  }
}
