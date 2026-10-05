// LivePresenceAI - App Mobile (Flutter)
// Fluxo: login -> minhas turmas -> chamada ao vivo -> relatório (com exportação).
// Gestão de turmas e alunos, histórico de aulas e exportação ficam em gestao.dart.

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_service.dart';
import 'config.dart';
import 'exportador.dart';
import 'rede/descoberta.dart';

part 'ajuste.dart';
part 'cadastro_rosto.dart';
part 'conta.dart';
part 'gestao.dart';
part 'tema.dart';

void main() {
  runApp(const LivePresenceApp());
}

class LivePresenceApp extends StatelessWidget {
  const LivePresenceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LivePresenceAI',
      debugShowCheckedModeBanner: false,
      theme: temaLivePresence(),
      home: const InicioScreen(),
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
  final int totalAlunos;
  final int totalAulas;
  final int? salaId; // sala padrão das chamadas
  final String? salaNome;

  Turma({required this.id, required this.nome, this.totalAlunos = 0, this.totalAulas = 0, this.salaId, this.salaNome});

  factory Turma.fromJson(Map<String, dynamic> json) => Turma(
        id: json['id'] as int,
        nome: json['nome'] as String,
        totalAlunos: json['total_alunos'] as int? ?? 0,
        totalAulas: json['total_aulas'] as int? ?? 0,
        salaId: json['sala_id'] as int?,
        salaNome: json['sala_nome'] as String?,
      );
}

class Aluno {
  final int id;
  final String nome;
  /// Sem cadastro facial a câmera não reconhece o aluno: a presença dele é marcada manualmente.
  final bool cadastroFacial;
  /// Ajuste manual feito pelo professor nesta aula (RN-15), se houver.
  AjusteManual? ajuste;
  String status; // 'ausente' | 'presente' (já detectado na sessão)
  DateTime? entrada;
  DateTime? ultimaVisualizacao;
  /// Tempo acumulado calculado pelo backend até a última detecção.
  Duration tempoAcumulado = Duration.zero;

  Aluno({required this.id, required this.nome, this.cadastroFacial = true, this.status = 'ausente'});

  factory Aluno.fromJson(Map<String, dynamic> json) => Aluno(
        id: json['id'] as int,
        nome: json['nome'] as String,
        cadastroFacial: json['cadastro_facial'] as bool? ?? true,
      );

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
  final String? ra;
  final bool detectado;
  final DateTime? entrada;
  /// Tempo acumulado calculado pelo backend (desconta os períodos em que o aluno saiu).
  final Duration permanencia;
  final double percentual;
  final String situacao; // 'presenca' | 'falta' (já com o ajuste manual)
  final bool ajusteManual;
  final String? motivoAjuste;

  SituacaoAluno({
    required this.alunoId,
    required this.nome,
    this.ra,
    required this.detectado,
    required this.entrada,
    required this.permanencia,
    required this.percentual,
    required this.situacao,
    this.ajusteManual = false,
    this.motivoAjuste,
  });

  bool get presente => situacao == 'presenca';

  factory SituacaoAluno.fromJson(Map<String, dynamic> json) => SituacaoAluno(
        alunoId: json['aluno_id'] as int,
        nome: json['nome'] as String,
        ra: json['ra'] as String?,
        detectado: json['detectado'] as bool,
        entrada: json['entrada'] != null ? _lerHorarioUtc(json['entrada'] as String) : null,
        permanencia: _segundos(json['tempo_total_presente']),
        percentual: (json['percentual_presenca'] as num?)?.toDouble() ?? 0.0,
        situacao: json['situacao'] as String,
        ajusteManual: json['ajuste_manual'] as bool? ?? false,
        motivoAjuste: json['motivo_ajuste'] as String?,
      );
}

/// Relatório final da sessão, calculado pelo servidor.
class Relatorio {
  final double frequenciaMinima;
  final int totalPresencas;
  final int totalFaltas;
  final List<SituacaoAluno> alunos;
  final DateTime? inicio;
  final DateTime? fim;
  final String? salaNome;

  Relatorio({
    this.salaNome,
    required this.frequenciaMinima,
    required this.totalPresencas,
    required this.totalFaltas,
    required this.alunos,
    this.inicio,
    this.fim,
  });

  factory Relatorio.fromJson(Map<String, dynamic> json) => Relatorio(
        salaNome: json['sala_nome'] as String?,
        inicio: json['inicio'] != null ? _lerHorarioUtc(json['inicio'] as String) : null,
        fim: json['fim'] != null ? _lerHorarioUtc(json['fim'] as String) : null,
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
  // Credenciais de teste do seed só aparecem preenchidas na versão de desenvolvimento
  final _emailController = TextEditingController(text: kDebugMode ? 'professor@livepresenceai.com' : '');
  final _senhaController = TextEditingController(text: kDebugMode ? 'senha123' : '');
  bool _carregando = false;
  bool _senhaVisivel = false;
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
      _usuario = await ApiService.eu();
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
      backgroundColor: Cores.superficie,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF0866FF), Color(0xFF7B61FF)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: const Icon(Icons.face_retouching_natural, color: Colors.white, size: 42),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Center(child: Marca(tamanho: 34)),
                  const SizedBox(height: 6),
                  const Text(
                    'A chamada se faz sozinha. Você só dá a aula.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Cores.textoSecundario, fontSize: 15),
                  ),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    decoration: const InputDecoration(
                      hintText: 'E-mail',
                      prefixIcon: Icon(Icons.alternate_email, color: Cores.textoSecundario),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _senhaController,
                    obscureText: !_senhaVisivel,
                    autofillHints: const [AutofillHints.password],
                    decoration: InputDecoration(
                      hintText: 'Senha',
                      prefixIcon: const Icon(Icons.lock_outline, color: Cores.textoSecundario),
                      suffixIcon: IconButton(
                        tooltip: _senhaVisivel ? 'Ocultar senha' : 'Mostrar senha',
                        icon: Icon(_senhaVisivel ? Icons.visibility_off : Icons.visibility,
                            color: Cores.textoSecundario),
                        onPressed: () => setState(() => _senhaVisivel = !_senhaVisivel),
                      ),
                    ),
                    onSubmitted: (_) => _fazerLogin(),
                  ),
                  if (_erro != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 14),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                            color: Cores.vermelhoClaro, borderRadius: BorderRadius.circular(12)),
                        child: Row(children: [
                          const Icon(Icons.error_outline, color: Cores.vermelho, size: 20),
                          const SizedBox(width: 8),
                          Expanded(child: Text(_erro!, style: const TextStyle(color: Cores.vermelho))),
                        ]),
                      ),
                    ),
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _carregando ? null : _fazerLogin,
                    style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
                    child: _carregando
                        ? const SizedBox(
                            width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                        : const Text('Entrar', style: TextStyle(fontSize: 17)),
                  ),
                  const SizedBox(height: 28),
                  if (!servidorDefinidoPelaPagina)
                    Center(
                      child: TextButton.icon(
                        icon: const Icon(Icons.dns_outlined, size: 18),
                        label: Text('Servidor: ${Uri.tryParse(apiBaseUrl)?.authority ?? apiBaseUrl}'),
                        onPressed: () async {
                          final mudou = await Navigator.push<bool>(
                              context, MaterialPageRoute(builder: (_) => const EncontrarServidorScreen()));
                          if (mudou == true) setState(() {});
                        },
                      ),
                    ),
                  const SizedBox(height: 8),
                  const Text(
                    'LivePresenceAI · reconhecimento facial na rede da sua instituição',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Cores.textoSecundario, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ),
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
    return EstadoVazio(
      icone: Icons.wifi_off_rounded,
      titulo: 'Algo deu errado',
      texto: mensagem,
      acao: Wrap(
        spacing: 10,
        runSpacing: 10,
        alignment: WrapAlignment.center,
        children: [
          FilledButton(onPressed: onTentarNovamente, child: const Text('Tentar novamente')),
          OutlinedButton(onPressed: onSair, child: Text(textoSair)),
        ],
      ),
    );
  }
}

// ---------------------- CHAMADA AO VIVO ----------------------
class ChamadaAtivaScreen extends StatefulWidget {
  final Turma turma;
  /// Sala escolhida ao iniciar; nula = sala padrão da turma (ou chamada sem câmera).
  final int? salaId;
  const ChamadaAtivaScreen({super.key, required this.turma, this.salaId});
  @override
  State<ChamadaAtivaScreen> createState() => _ChamadaAtivaScreenState();
}

class _ChamadaAtivaScreenState extends State<ChamadaAtivaScreen> {
  List<Aluno> _alunos = [];
  bool _carregando = true;
  bool _encerrando = false;
  String? _erro;

  int? _sessaoId;
  String? _salaNome;
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
      if (dadosAlunos.isEmpty) {
        // Sem alunos não há chamada: não abre a sessão (nem ocupa a sala)
        if (mounted) setState(() => _carregando = false);
        return;
      }
      final sessao = await ApiService.abrirSessao(widget.turma.id, salaId: widget.salaId);
      if (!mounted) return;

      setState(() {
        _alunos = dadosAlunos.map(Aluno.fromJson).toList();
        _sessaoId = sessao['id'] as int;
        _salaNome = sessao['sala_nome'] as String?;
        _inicioSessao = _lerHorarioUtc(sessao['inicio'] as String);
        _limiteAusencia = _segundos(sessao['limite_ausencia_segundos']);
        _frequenciaMinima = (sessao['frequencia_minima'] as num?)?.toDouble();
        // Sessão retomada: restaura quem já tinha sido detectado antes de sair da tela
        _aplicarRegistros(sessao['registros'] as List<dynamic>? ?? []);
        _aplicarAjustes(sessao['ajustes'] as List<dynamic>? ?? []);
        _carregando = false;
      });

      if (sessao['retomada'] == true) {
        _avisar(context, 'Chamada em andamento retomada.');
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

  void _aplicarAjustes(List<dynamic> ajustes) {
    final porAluno = {for (final a in ajustes.cast<Map<String, dynamic>>()) a['aluno_id'] as int: AjusteManual.fromJson(a)};
    for (final aluno in _alunos) {
      aluno.ajuste = porAluno[aluno.id];
    }
  }

  Future<void> _ajustar(Aluno aluno) async {
    final sessaoId = _sessaoId;
    if (sessaoId == null) return;
    final mudou = await _ajustarAluno(context,
        sessaoId: sessaoId, alunoId: aluno.id, nome: aluno.nome, atual: aluno.ajuste, semBiometria: !aluno.cadastroFacial);
    if (mudou) await _sincronizar();
  }

  /// Busca o estado atual no backend (eventos perdidos enquanto o WebSocket estava fora).
  Future<void> _sincronizar() async {
    final sessaoId = _sessaoId;
    if (sessaoId == null) return;
    try {
      final sessao = await ApiService.consultarSessao(sessaoId);
      if (!mounted) return;
      setState(() {
        _aplicarRegistros(sessao['registros'] as List<dynamic>? ?? []);
        _aplicarAjustes(sessao['ajustes'] as List<dynamic>? ?? []);
      });
    } on ApiException {
      // Mantém o estado atual; a próxima reconexão tenta de novo.
    }
  }

  Future<void> _conectarWebSocket({bool reconexao = false}) async {
    final sessaoId = _sessaoId;
    if (sessaoId == null || !_telaAtiva) return;

    try {
      // O navegador não envia cabeçalhos no WebSocket: o token vai na URL e o backend confere o dono
      final token = Uri.encodeQueryComponent(await ApiService.obterToken() ?? '');
      final canal = ApiService.abrirWebSocket(Uri.parse('$wsBaseUrl/ws/sessoes/$sessaoId?token=$token'));
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
    if (ausentes.isEmpty) {
      _avisar(context, 'Todos os alunos já foram detectados.');
      return;
    }
    final alvo = ausentes.first;

    try {
      final registrado = await ApiService.reconhecer(sessaoId, alvo.id, 0.9);
      // Sem tempo real, o evento não chega pelo WebSocket: busca o estado no backend
      if (registrado && !_tempoRealAtivo) await _sincronizar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  /// Encerra a sessão no backend e abre o relatório calculado pelo servidor.
  Future<void> _encerrarChamada() async {
    final sessaoId = _sessaoId;
    if (sessaoId == null || _encerrando) return;
    final confirmado = await _confirmar(context, 'Encerrar chamada?',
        'A permanência e a situação de cada aluno serão calculadas agora. Depois de encerrada, a chamada '
        'não pode ser reaberta.',
        acao: 'Encerrar');
    if (!confirmado) return;

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
      if (mounted) _avisar(context, e.mensagem);
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
    final duracao = _inicioSessao != null ? DateTime.now().difference(_inicioSessao!) : null;
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(
          children: [
            Flexible(child: TituloTela(widget.turma.nome, subtitulo: _salaNome != null ? 'Chamada · $_salaNome' : 'Chamada sem câmera')),
            const SizedBox(width: 10),
            if (_sessaoId != null && duracao != null) AoVivo(texto: _formatarDuracao(duracao)),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Tooltip(
              message: _tempoRealAtivo ? 'Tempo real conectado' : 'Tempo real desconectado',
              child: Icon(Icons.circle, size: 12, color: _tempoRealAtivo ? Cores.verde : Cores.ambar),
            ),
          ),
        ],
        bottom: reconectando
            ? PreferredSize(
                preferredSize: const Size.fromHeight(34),
                child: Container(
                  height: 34,
                  width: double.infinity,
                  color: Cores.ambarClaro,
                  alignment: Alignment.center,
                  child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Cores.ambar)),
                    SizedBox(width: 8),
                    Text('Reconectando ao tempo real…',
                        style: TextStyle(color: Color(0xFF8A5A00), fontWeight: FontWeight.w600, fontSize: 13)),
                  ]),
                ),
              )
            : null,
      ),
      body: _corpo(),
      bottomNavigationBar: _carregando || _erro != null || _alunos.isEmpty ? null : _barraInferior(),
    );
  }

  Widget _barraInferior() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
        decoration: const BoxDecoration(
          color: Cores.superficie,
          border: Border(top: BorderSide(color: Cores.divisor, width: 0.6)),
        ),
        child: Row(
          children: [
            Tooltip(
              message: 'Marca o próximo aluno não detectado (teste sem câmera)',
              child: OutlinedButton.icon(
                onPressed: _simularReconhecimento,
                icon: const Icon(Icons.science_outlined, size: 20),
                label: const Text('Simular'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: FilledButton.icon(
                onPressed: _encerrando ? null : _encerrarChamada,
                style: FilledButton.styleFrom(backgroundColor: Cores.vermelho, minimumSize: const Size.fromHeight(46)),
                icon: _encerrando
                    ? const SizedBox(
                        width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.stop_circle_outlined),
                label: const Text('Encerrar chamada'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  ({String estado, Color cor, double percentual, Duration permanencia, bool naSala}) _situacao(
      Aluno aluno, DateTime agora) {
    final entrada = aluno.entrada!;
    final naSala = aluno.naSala(agora, _limiteAusencia);
    final permanencia = aluno.permanenciaParcial(agora, _limiteAusencia);
    final duracaoAula = agora.difference(_inicioSessao ?? entrada);
    final percentual = duracaoAula.inMilliseconds > 0
        ? min(100.0, permanencia.inMilliseconds / duracaoAula.inMilliseconds * 100)
        : 100.0;
    final estado = naSala
        ? 'Na sala'
        : 'Saiu há ${_formatarDuracao(agora.difference(aluno.ultimaVisualizacao!))}';
    return (estado: estado, cor: naSala ? Cores.verde : Cores.ambar, percentual: percentual,
        permanencia: permanencia, naSala: naSala);
  }

  Widget _linhaAluno(Aluno aluno, DateTime agora) {
    final ajuste = aluno.ajuste;
    if (ajuste != null) {
      // RN-15: o ajuste manual prevalece sobre o reconhecimento
      return ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
        leading: Avatar(nome: aluno.nome, anel: ajuste.presenca ? Cores.azul : Cores.vermelho),
        title: Text(aluno.nome),
        subtitle: Text('${ajuste.presenca ? 'Presença' : 'Falta'} manual · ${ajuste.motivo}',
            maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: Etiqueta(
          texto: 'Manual',
          cor: ajuste.presenca ? Cores.azul : Cores.vermelho,
          fundo: ajuste.presenca ? Cores.azulClaro : Cores.vermelhoClaro,
          icone: Icons.edit,
        ),
        onTap: () => _ajustar(aluno),
      );
    }
    if (aluno.entrada == null) {
      return ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
        leading: Avatar(nome: aluno.nome, anel: Cores.divisor, anelTracejado: true),
        title: Text(aluno.nome),
        subtitle: Text(aluno.cadastroFacial ? 'Ainda não detectado' : 'Sem biometria · marque a presença'),
        trailing: aluno.cadastroFacial
            ? null
            : TextButton(onPressed: () => _ajustar(aluno), child: const Text('Presente')),
        onTap: () => _mostrarDetalhes(aluno, agora),
      );
    }

    final s = _situacao(aluno, agora);
    final abaixoDoMinimo = _frequenciaMinima != null && s.percentual < _frequenciaMinima!;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: Avatar(nome: aluno.nome, anel: s.cor),
      title: Text(aluno.nome),
      subtitle: Text('${s.estado} · na aula há ${_formatarDuracao(s.permanencia)}',
          style: TextStyle(color: s.naSala ? Cores.textoSecundario : const Color(0xFF8A5A00))),
      trailing: Etiqueta(
        texto: '${s.percentual.toStringAsFixed(0)}%',
        cor: abaixoDoMinimo ? Cores.vermelho : Cores.verde,
        fundo: abaixoDoMinimo ? Cores.vermelhoClaro : Cores.verdeClaro,
      ),
      onTap: () => _mostrarDetalhes(aluno, agora),
    );
  }

  void _mostrarDetalhes(Aluno aluno, DateTime agora) {
    final s = aluno.entrada != null ? _situacao(aluno, agora) : null;
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Avatar(nome: aluno.nome, tamanho: 72, anel: s?.cor ?? Cores.divisor),
            const SizedBox(height: 12),
            Text(aluno.nome, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Etiqueta(
              texto: s?.estado ?? 'Ainda não detectado',
              cor: s == null ? Cores.textoSecundario : (s.naSala ? Cores.verde : const Color(0xFF8A5A00)),
              fundo: s == null ? Cores.fundo : (s.naSala ? Cores.verdeClaro : Cores.ambarClaro),
            ),
            const SizedBox(height: 20),
            if (s != null)
              Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
                Indicador(valor: _formatarHora(aluno.entrada!).substring(0, 5), legenda: 'Entrada'),
                Indicador(valor: _formatarDuracao(s.permanencia), legenda: 'Na aula'),
                Indicador(valor: '${s.percentual.toStringAsFixed(0)}%', legenda: 'Da aula até agora'),
              ]),
            if (s != null) ...[
              const SizedBox(height: 16),
              Text('Visto pela última vez às ${_formatarHora(aluno.ultimaVisualizacao!)}',
                  style: const TextStyle(color: Cores.textoSecundario)),
            ],
            const SizedBox(height: 18),
            OutlinedButton.icon(
              icon: const Icon(Icons.edit_note),
              label: const Text('Ajustar chamada manualmente'),
              onPressed: () {
                Navigator.pop(context);
                _ajustar(aluno);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _cartaoResumo(DateTime agora) {
    final naSala = _alunos.where((a) => a.naSala(agora, _limiteAusencia)).toList();
    final detectados = _alunos.where((a) => a.status == 'presente').length;
    final sairam = detectados - naSala.length;
    final manuais = _alunos.where((a) => a.ajuste?.presenca ?? false).length;
    return Cartao(
      margem: const EdgeInsets.fromLTRB(12, 12, 12, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(child: Indicador(valor: '${naSala.length}', legenda: 'na sala', cor: Cores.verde)),
            Expanded(child: Indicador(valor: '$sairam', legenda: 'saíram', cor: Cores.ambar)),
            Expanded(child: Indicador(valor: '$detectados/${_alunos.length}', legenda: 'detectados')),
          ]),
          if (manuais > 0)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(manuais == 1 ? '+ 1 presença marcada manualmente' : '+ $manuais presenças marcadas manualmente',
                  style: const TextStyle(color: Cores.azul, fontWeight: FontWeight.w600)),
            ),
          if (naSala.isNotEmpty) ...[
            const SizedBox(height: 14),
            // Faixa de quem está na sala agora, como os stories do Instagram
            SizedBox(
              height: 82,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: naSala.length,
                separatorBuilder: (_, __) => const SizedBox(width: 12),
                itemBuilder: (context, i) => SizedBox(
                  width: 64,
                  child: Column(children: [
                    Avatar(nome: naSala[i].nome, tamanho: 50, anel: Cores.verde),
                    const SizedBox(height: 4),
                    Text(naSala[i].nome.split(' ').first,
                        maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12, color: Cores.texto)),
                  ]),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

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
      return const EstadoVazio(
        icone: Icons.group_add_outlined,
        titulo: 'Turma sem alunos',
        texto: 'Cadastre os alunos na tela Alunos para começar a chamada.',
      );
    }

    final agora = DateTime.now();
    // Ordem: na sala, depois quem saiu, depois não detectados (cada grupo em ordem alfabética)
    int peso(Aluno a) => (a.ajuste?.presenca ?? false)
        ? 0
        : (a.entrada == null ? 2 : (a.naSala(agora, _limiteAusencia) ? 0 : 1));
    final ordenados = [..._alunos]..sort((a, b) {
        final p = peso(a).compareTo(peso(b));
        return p != 0 ? p : a.nome.compareTo(b.nome);
      });

    return ListView(
      padding: const EdgeInsets.only(bottom: 12),
      children: [
        _cartaoResumo(agora),
        Cartao(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 8, 16, 2),
                child: Text('Alunos', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
                child: Text(
                  'Valores parciais; os oficiais saem ao encerrar. Mínimo: '
                  '${(_frequenciaMinima ?? 0).toStringAsFixed(0)}% da aula.',
                  style: const TextStyle(fontSize: 12.5, color: Cores.textoSecundario),
                ),
              ),
              for (final aluno in ordenados) _linhaAluno(aluno, agora),
            ],
          ),
        ),
      ],
    );
  }
}

// ---------------------- RELATÓRIO (vindo do backend) ----------------------
class RelatorioScreen extends StatefulWidget {
  final Turma turma;
  final int sessaoId;
  final Relatorio relatorio;
  /// Aberto pelo histórico: o botão volta ao histórico em vez de ir para as turmas.
  final bool doHistorico;

  const RelatorioScreen({
    super.key,
    required this.turma,
    required this.sessaoId,
    required this.relatorio,
    this.doHistorico = false,
  });

  @override
  State<RelatorioScreen> createState() => _RelatorioScreenState();
}

class _RelatorioScreenState extends State<RelatorioScreen> {
  late Relatorio relatorio = widget.relatorio;
  Turma get turma => widget.turma;
  int get sessaoId => widget.sessaoId;
  bool get doHistorico => widget.doHistorico;

  /// Ajuste manual depois da aula (falta justificada, presença sem biometria...) e recarga do relatório.
  Future<void> _ajustar(SituacaoAluno aluno) async {
    final mudou = await _ajustarAluno(context,
        sessaoId: sessaoId,
        alunoId: aluno.alunoId,
        nome: aluno.nome,
        atual: aluno.ajusteManual ? AjusteManual(aluno.situacao, aluno.motivoAjuste ?? '') : null);
    if (!mudou) return;
    try {
      final novo = Relatorio.fromJson(await ApiService.relatorio(sessaoId));
      if (mounted) setState(() => relatorio = novo);
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Widget _linhaAluno(SituacaoAluno aluno) {
    final minimo = relatorio.frequenciaMinima.toStringAsFixed(0);
    final Widget etiqueta;
    final String detalhe;
    if (aluno.ajusteManual) {
      etiqueta = Etiqueta(
          texto: aluno.presente ? 'Presença' : 'Falta',
          cor: aluno.presente ? Cores.azul : Cores.vermelho,
          fundo: aluno.presente ? Cores.azulClaro : Cores.vermelhoClaro,
          icone: Icons.edit);
      detalhe = 'Manual · ${aluno.motivoAjuste ?? ''}';
    } else if (aluno.presente) {
      etiqueta = const Etiqueta(texto: 'Presença', cor: Cores.verde, fundo: Cores.verdeClaro, icone: Icons.check);
      detalhe = 'Entrou ${_formatarHora(aluno.entrada!).substring(0, 5)} · ficou ${_formatarDuracao(aluno.permanencia)}';
    } else if (aluno.detectado) {
      // Foi visto, mas ficou menos que o mínimo: falta registrada, dados guardados para auditoria
      etiqueta = const Etiqueta(texto: 'Falta', cor: Cores.vermelho, fundo: Cores.vermelhoClaro);
      detalhe = 'Abaixo de $minimo% · ficou ${_formatarDuracao(aluno.permanencia)}';
    } else {
      etiqueta = const Etiqueta(texto: 'Falta', cor: Cores.vermelho, fundo: Cores.vermelhoClaro);
      detalhe = 'Não detectado';
    }
    // No ajuste manual o percentual e so informativo (a situacao veio do professor)
    final cor = aluno.ajusteManual ? Cores.textoSecundario : (aluno.presente ? Cores.verde : Cores.vermelho);

    return InkWell(
      onTap: () => _ajustar(aluno),
      child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Avatar(nome: aluno.nome, tamanho: 42),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(aluno.nome, style: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w700)),
                Text(aluno.ra != null ? 'RA ${aluno.ra} · $detalhe' : detalhe,
                    style: const TextStyle(fontSize: 13, color: Cores.textoSecundario)),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: (aluno.percentual / 100).clamp(0, 1).toDouble(),
                    minHeight: 5,
                    color: cor,
                    backgroundColor: Cores.fundo,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            etiqueta,
            const SizedBox(height: 4),
            Text('${aluno.percentual.toStringAsFixed(1)}%',
                style: TextStyle(fontWeight: FontWeight.w800, color: cor)),
          ]),
        ],
      ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final total = relatorio.alunos.length;
    final taxa = total == 0 ? 0 : (relatorio.totalPresencas / total * 100).round();
    final quando = relatorio.inicio != null
        ? '${_formatarData(relatorio.inicio!)} · ${_formatarHoraMinuto(relatorio.inicio!)}'
            '${relatorio.fim != null ? '–${_formatarHoraMinuto(relatorio.fim!)}' : ''}'
            '${relatorio.salaNome != null ? ' · ${relatorio.salaNome}' : ''}'
        : 'Aula #$sessaoId';
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: doHistorico,
        titleSpacing: doHistorico ? 0 : null,
        title: TituloTela('Relatório da aula', subtitulo: turma.nome),
        actions: [_BotaoExportar(sessaoId: sessaoId), const SizedBox(width: 8)],
      ),
      body: ListView(
        padding: const EdgeInsets.only(bottom: 12),
        children: [
          Cartao(
            margem: const EdgeInsets.fromLTRB(12, 12, 12, 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.event_outlined, size: 18, color: Cores.textoSecundario),
                  const SizedBox(width: 6),
                  Text(quando, style: const TextStyle(color: Cores.textoSecundario, fontWeight: FontWeight.w600)),
                ]),
                const SizedBox(height: 14),
                Row(children: [
                  Expanded(child: Indicador(valor: '${relatorio.totalPresencas}', legenda: 'presenças', cor: Cores.verde)),
                  Expanded(child: Indicador(valor: '${relatorio.totalFaltas}', legenda: 'faltas', cor: Cores.vermelho)),
                  Expanded(child: Indicador(valor: '$taxa%', legenda: 'da turma presente')),
                ]),
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                    value: total == 0 ? 0 : relatorio.totalPresencas / total,
                    minHeight: 8,
                    color: Cores.verde,
                    backgroundColor: Cores.vermelhoClaro,
                  ),
                ),
                const SizedBox(height: 10),
                Text('Presença exige ${relatorio.frequenciaMinima.toStringAsFixed(0)}% do tempo de aula. '
                    'Toque num aluno para ajustar manualmente.',
                    style: const TextStyle(fontSize: 12.5, color: Cores.textoSecundario)),
              ],
            ),
          ),
          Cartao(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(
              children: [
                for (var i = 0; i < relatorio.alunos.length; i++) ...[
                  if (i > 0) const Divider(indent: 70),
                  _linhaAluno(relatorio.alunos[i]),
                ],
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: OutlinedButton(
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(46)),
            onPressed: doHistorico
                ? () => Navigator.pop(context)
                : () => Navigator.pushAndRemoveUntil(
                      context,
                      MaterialPageRoute(builder: (_) => const SelecaoTurmaScreen()),
                      (rota) => false,
                    ),
            child: Text(doHistorico ? 'Voltar ao histórico' : 'Voltar às turmas'),
          ),
        ),
      ),
    );
  }
}
