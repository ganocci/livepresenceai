// LivePresenceAI - Cadastro facial do aluno pelo celular do professor.
// O professor enquadra o rosto na moldura e toca em "Capturar": após 3 s o app tira 5 fotos seguidas e as
// envia ao servidor, que gera o vetor facial e descarta as fotos. Nada fica gravado no aparelho.
// Parte da biblioteca de main.dart.

part of 'main.dart';

class CadastroRostoScreen extends StatefulWidget {
  final AlunoCadastro aluno;
  const CadastroRostoScreen({super.key, required this.aluno});
  @override
  State<CadastroRostoScreen> createState() => _CadastroRostoScreenState();
}

enum _Etapa { preparando, enquadrando, contando, capturando, enviando, concluido, erro }

class _CadastroRostoScreenState extends State<CadastroRostoScreen> {
  static const _fotos = 5;
  static const _intervaloFotos = Duration(milliseconds: 400);

  List<CameraDescription> _cameras = [];
  CameraController? _controle;
  int _indiceCamera = 0;
  _Etapa _etapa = _Etapa.preparando;
  int _contagem = 0;
  int _capturadas = 0;
  String? _mensagem;

  @override
  void initState() {
    super.initState();
    _iniciar();
  }

  @override
  void dispose() {
    _controle?.dispose();
    super.dispose();
  }

  Future<void> _iniciar() async {
    try {
      _cameras = await availableCameras();
      if (_cameras.isEmpty) {
        _falhar('Nenhuma câmera encontrada neste aparelho.');
        return;
      }
      // Prefere a câmera traseira: o professor fotografa o aluno à sua frente
      final traseira = _cameras.indexWhere((c) => c.lensDirection == CameraLensDirection.back);
      _indiceCamera = traseira >= 0 ? traseira : 0;
      await _abrirCamera();
    } on CameraException catch (e) {
      _falhar(_mensagemCamera(e));
    }
  }

  Future<void> _abrirCamera() async {
    final anterior = _controle;
    setState(() => _etapa = _Etapa.preparando);
    await anterior?.dispose();
    final controle = CameraController(_cameras[_indiceCamera], ResolutionPreset.high, enableAudio: false);
    try {
      await controle.initialize();
    } on CameraException catch (e) {
      _falhar(_mensagemCamera(e));
      return;
    }
    if (!mounted) {
      await controle.dispose();
      return;
    }
    setState(() {
      _controle = controle;
      _etapa = _Etapa.enquadrando;
    });
  }

  String _mensagemCamera(CameraException e) {
    if (e.code.contains('Denied') || e.code.contains('denied')) {
      return 'O acesso à câmera foi negado. Libere a câmera nas permissões do app (ou do navegador).';
    }
    return 'Não foi possível abrir a câmera (${e.description ?? e.code}).';
  }

  void _falhar(String mensagem) {
    if (!mounted) return;
    setState(() {
      _etapa = _Etapa.erro;
      _mensagem = mensagem;
    });
  }

  Future<void> _trocarCamera() async {
    _indiceCamera = (_indiceCamera + 1) % _cameras.length;
    await _abrirCamera();
  }

  Future<void> _capturar() async {
    final controle = _controle;
    if (controle == null || !controle.value.isInitialized) return;

    for (var i = 3; i >= 1; i--) {
      setState(() {
        _etapa = _Etapa.contando;
        _contagem = i;
      });
      await Future.delayed(const Duration(seconds: 1));
      if (!mounted) return;
    }

    final fotos = <Uint8List>[];
    setState(() {
      _etapa = _Etapa.capturando;
      _capturadas = 0;
    });
    try {
      for (var i = 0; i < _fotos; i++) {
        final arquivo = await controle.takePicture();
        fotos.add(await arquivo.readAsBytes());
        await apagarArquivoTemporario(arquivo.path); // a foto não fica no aparelho
        if (!mounted) return;
        setState(() => _capturadas = i + 1);
        await Future.delayed(_intervaloFotos);
      }
    } on CameraException catch (e) {
      _falhar(_mensagemCamera(e));
      return;
    }

    setState(() => _etapa = _Etapa.enviando);
    try {
      await ApiService.cadastrarRosto(widget.aluno.id, fotos);
      if (mounted) setState(() => _etapa = _Etapa.concluido);
    } on ApiException catch (e) {
      // Ex.: "Rosto pequeno ou pouco nítido. Aproxime o celular e evite contraluz."
      if (mounted) {
        setState(() {
          _etapa = _Etapa.enquadrando;
          _mensagem = e.mensagem;
        });
      }
    }
  }

  Widget _moldura() {
    return IgnorePointer(
      child: Center(
        child: FractionallySizedBox(
          widthFactor: 0.62,
          child: AspectRatio(
            aspectRatio: 3 / 4,
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 3),
                borderRadius: const BorderRadius.all(Radius.elliptical(200, 260)),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _faixaInferior() {
    final String texto;
    Widget? acao;
    switch (_etapa) {
      case _Etapa.contando:
        texto = 'Mantenha o rosto na moldura… $_contagem';
      case _Etapa.capturando:
        texto = 'Capturando $_capturadas/$_fotos…';
      case _Etapa.enviando:
        texto = 'Processando…';
        acao = const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2));
      default:
        texto = _mensagem ?? 'Enquadre o rosto de ${widget.aluno.nome} na moldura, de frente e bem iluminado.';
        acao = FilledButton.icon(
          icon: const Icon(Icons.camera_alt),
          label: Text(_mensagem == null ? 'Capturar' : 'Tentar de novo'),
          onPressed: _capturar,
        );
    }
    return Container(
      width: double.infinity,
      color: Colors.black87,
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(texto,
              textAlign: TextAlign.center,
              style: TextStyle(color: _mensagem != null && _etapa == _Etapa.enquadrando ? Colors.amber : Colors.white,
                  fontSize: 15)),
          if (acao != null) ...[const SizedBox(height: 12), acao],
        ],
      ),
    );
  }

  Widget _concluido() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle, color: Colors.green, size: 72),
            const SizedBox(height: 12),
            Text('Rosto de ${widget.aluno.nome} cadastrado',
                textAlign: TextAlign.center, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            const Text('As fotos foram descartadas; só o vetor facial foi guardado.',
                textAlign: TextAlign.center, style: TextStyle(color: Colors.black54)),
            const SizedBox(height: 20),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Concluir')),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controle = _controle;
    Widget corpo;
    if (_etapa == _Etapa.concluido) {
      corpo = _concluido();
    } else if (_etapa == _Etapa.erro) {
      corpo = Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.no_photography, size: 56, color: Colors.red),
            const SizedBox(height: 12),
            Text(_mensagem ?? 'Erro na câmera.', textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: () => Navigator.pop(context), child: const Text('Voltar')),
          ]),
        ),
      );
    } else if (controle == null || !controle.value.isInitialized) {
      corpo = const Center(child: CircularProgressIndicator());
    } else {
      corpo = Container(
        color: Colors.black,
        child: Column(
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Center(child: CameraPreview(controle)),
                  _moldura(),
                  if (_etapa == _Etapa.contando)
                    Center(
                      child: Text('$_contagem',
                          style: const TextStyle(color: Colors.white, fontSize: 96, fontWeight: FontWeight.bold)),
                    ),
                ],
              ),
            ),
            _faixaInferior(),
          ],
        ),
      );
    }

    final ocupado = _etapa == _Etapa.contando || _etapa == _Etapa.capturando || _etapa == _Etapa.enviando;
    return PopScope(
      canPop: !ocupado,
      child: Scaffold(
        appBar: AppBar(
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Cadastro facial', style: TextStyle(fontSize: 18)),
              Text('${widget.aluno.nome}${widget.aluno.ra != null ? ' • RA ${widget.aluno.ra}' : ''}',
                  style: const TextStyle(fontSize: 12)),
            ],
          ),
          actions: [
            if (_cameras.length > 1 && _etapa == _Etapa.enquadrando)
              IconButton(icon: const Icon(Icons.cameraswitch), tooltip: 'Trocar câmera', onPressed: _trocarCamera),
          ],
        ),
        body: corpo,
      ),
    );
  }
}
