// LivePresenceAI - Abertura do app, configuração inicial, servidor, minha conta e administração.
// Parte da biblioteca de main.dart.

part of 'main.dart';

/// Usuário logado (carregado de GET /eu). Nulo antes do login.
Map<String, dynamic>? _usuario;

bool get _ehAdministrador => _usuario?['perfil'] == 'administrador';

// ---------------------- ABERTURA ----------------------

/// Decide a primeira tela: configuração inicial (sem administrador), turmas (sessão válida) ou login.
class InicioScreen extends StatefulWidget {
  const InicioScreen({super.key});
  @override
  State<InicioScreen> createState() => _InicioScreenState();
}

class _InicioScreenState extends State<InicioScreen> {
  String? _erro;

  @override
  void initState() {
    super.initState();
    _decidir();
  }

  Future<void> _decidir({bool tentarDescoberta = true}) async {
    setState(() => _erro = null);
    await ApiService.carregarServidor();
    if (!await ApiService.temServidorSalvo()) {
      // Primeiro uso no celular: procura o servidor na rede em vez de pedir o IP
      if (!mounted) return;
      await Navigator.push(context, MaterialPageRoute(builder: (_) => const EncontrarServidorScreen(primeiroUso: true)));
      if (!await ApiService.temServidorSalvo()) {
        if (mounted) setState(() => _erro = 'Nenhum servidor escolhido.');
        return;
      }
    }
    Widget destino;
    try {
      if (!await ApiService.sistemaConfigurado()) {
        destino = const ConfiguracaoInicialScreen();
      } else if (await ApiService.obterToken() != null) {
        try {
          _usuario = await ApiService.eu();
          destino = const SelecaoTurmaScreen();
        } on ApiException {
          destino = const LoginScreen();
        }
      } else {
        destino = const LoginScreen();
      }
    } on ApiException catch (e) {
      // O servidor pode ter mudado de IP (o roteador troca os endereços): procura de novo na rede e, se
      // houver um único servidor, passa a usá-lo sem perguntar
      if (tentarDescoberta && !servidorDefinidoPelaPagina) {
        final achados = await ApiService.procurarNaRede();
        if (achados.length == 1) {
          try {
            await ApiService.usarServidorEncontrado(achados.first);
            await _decidir(tentarDescoberta: false);
            return;
          } on ApiException {
            // segue para a mensagem de erro
          }
        }
      }
      if (!mounted) return;
      setState(() => _erro = e.mensagem);
      return;
    }
    if (!mounted) return;
    Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => destino));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Cores.superficie,
      body: _erro == null
          ? const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Marca(tamanho: 34),
              SizedBox(height: 24),
              CircularProgressIndicator(),
            ]))
          : EstadoVazio(
              icone: Icons.cloud_off_outlined,
              titulo: 'Servidor não encontrado',
              texto: '$_erro\n\nServidor: $apiBaseUrl',
              acao: Wrap(spacing: 10, runSpacing: 10, alignment: WrapAlignment.center, children: [
                FilledButton(onPressed: _decidir, child: const Text('Tentar novamente')),
                if (!servidorDefinidoPelaPagina)
                  OutlinedButton(
                    onPressed: () async {
                      final mudou = await Navigator.push<bool>(
                          context, MaterialPageRoute(builder: (_) => const EncontrarServidorScreen()));
                      if (mudou == true) _decidir();
                    },
                    child: const Text('Procurar servidor'),
                  ),
              ]),
            ),
    );
  }
}

/// Folha para digitar o endereço do servidor; devolve true se mudou.
Future<bool> _escolherServidor(BuildContext context) async {
  final controle = TextEditingController(text: apiBaseUrl);
  String? erro;
  bool testando = false;
  final mudou = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (context) => StatefulBuilder(
      builder: (context, atualizar) => Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(context).viewInsets.bottom + 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Servidor', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            const Text('Endereço do computador onde o LivePresenceAI está instalado. Ele aparece no painel do '
                'servidor (ex.: https://192.168.0.10:8443).',
                style: TextStyle(color: Cores.textoSecundario)),
            const SizedBox(height: 14),
            TextField(
              controller: controle,
              keyboardType: TextInputType.url,
              autofocus: true,
              decoration: InputDecoration(hintText: 'https://192.168.0.10:8443', errorText: erro, errorMaxLines: 3),
            ),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: testando
                  ? null
                  : () async {
                      atualizar(() {
                        testando = true;
                        erro = null;
                      });
                      try {
                        await ApiService.alterarServidor(controle.text);
                        if (context.mounted) Navigator.pop(context, true);
                      } on ApiException catch (e) {
                        atualizar(() => erro = e.mensagem);
                      } finally {
                        if (context.mounted) atualizar(() => testando = false);
                      }
                    },
              child: testando
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('Conectar'),
            ),
          ],
        ),
      ),
    ),
  );
  return mudou ?? false;
}

// ---------------------- ENCONTRAR O SERVIDOR NA REDE ----------------------

/// Procura o LivePresenceAI na rede (Wi-Fi) e conecta com um toque, sem digitar endereço.
/// Devolve true (Navigator.pop) quando um servidor foi escolhido.
class EncontrarServidorScreen extends StatefulWidget {
  final bool primeiroUso;
  const EncontrarServidorScreen({super.key, this.primeiroUso = false});
  @override
  State<EncontrarServidorScreen> createState() => _EncontrarServidorScreenState();
}

class _EncontrarServidorScreenState extends State<EncontrarServidorScreen> {
  bool _procurando = true;
  List<ServidorEncontrado> _achados = [];
  String? _conectando;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _procurar();
  }

  Future<void> _procurar() async {
    setState(() {
      _procurando = true;
      _erro = null;
    });
    final achados = await ApiService.procurarNaRede();
    if (!mounted) return;
    setState(() {
      _achados = achados;
      _procurando = false;
    });
    // Um único servidor no primeiro uso: conecta direto
    if (widget.primeiroUso && achados.length == 1) _usar(achados.first);
  }

  Future<void> _usar(ServidorEncontrado servidor) async {
    setState(() {
      _conectando = servidor.url;
      _erro = null;
    });
    try {
      await ApiService.usarServidorEncontrado(servidor);
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _erro = e.mensagem);
    } finally {
      if (mounted) setState(() => _conectando = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Cores.superficie,
      appBar: widget.primeiroUso ? null : AppBar(title: const TituloTela('Servidor')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                if (widget.primeiroUso) const Center(child: Marca(tamanho: 30)),
                const SizedBox(height: 18),
                Center(
                  child: Container(
                    padding: const EdgeInsets.all(22),
                    decoration: const BoxDecoration(color: Cores.azulClaro, shape: BoxShape.circle),
                    child: _procurando
                        ? const SizedBox(width: 40, height: 40, child: CircularProgressIndicator(strokeWidth: 3))
                        : const Icon(Icons.wifi_find, size: 40, color: Cores.azul),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  _procurando
                      ? 'Procurando o LivePresenceAI na rede…'
                      : _achados.isEmpty
                          ? 'Nenhum servidor encontrado'
                          : 'Escolha o servidor da sua instituição',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                Text(
                  _procurando || _achados.isNotEmpty
                      ? 'O celular precisa estar no mesmo Wi-Fi do computador onde o sistema está ligado.'
                      : 'Confira se o computador do LivePresenceAI está ligado (painel com "Servidor no ar") e se '
                          'o celular está no mesmo Wi-Fi — redes de visitantes costumam bloquear essa busca.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Cores.textoSecundario),
                ),
                const SizedBox(height: 18),
                for (final servidor in _achados)
                  Card(
                    color: Cores.fundo,
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: const CircleAvatar(backgroundColor: Cores.azul, child: Icon(Icons.dns, color: Colors.white)),
                      title: Text(servidor.nome),
                      subtitle: Text(servidor.url),
                      trailing: _conectando == servidor.url
                          ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.chevron_right),
                      onTap: _conectando == null ? () => _usar(servidor) : null,
                    ),
                  ),
                if (_erro != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(_erro!, textAlign: TextAlign.center, style: const TextStyle(color: Cores.vermelho)),
                  ),
                if (!_procurando) ...[
                  FilledButton.icon(
                    onPressed: _procurar,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Procurar de novo'),
                  ),
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: () async {
                      final mudou = await _escolherServidor(context);
                      if (mudou && context.mounted) Navigator.pop(context, true);
                    },
                    child: const Text('Digitar o endereço manualmente'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------- CONFIGURAÇÃO INICIAL ----------------------

class ConfiguracaoInicialScreen extends StatefulWidget {
  const ConfiguracaoInicialScreen({super.key});
  @override
  State<ConfiguracaoInicialScreen> createState() => _ConfiguracaoInicialScreenState();
}

class _ConfiguracaoInicialScreenState extends State<ConfiguracaoInicialScreen> {
  final _formulario = GlobalKey<FormState>();
  final _nome = TextEditingController();
  final _email = TextEditingController();
  final _senha = TextEditingController();
  final _confirmacao = TextEditingController();
  bool _salvando = false;
  String? _erro;

  Future<void> _salvar() async {
    if (!_formulario.currentState!.validate()) return;
    setState(() {
      _salvando = true;
      _erro = null;
    });
    try {
      await ApiService.configurarSistema(_nome.text.trim(), _email.text.trim(), _senha.text);
      _usuario = await ApiService.eu();
      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
          context, MaterialPageRoute(builder: (_) => const SelecaoTurmaScreen()), (rota) => false);
    } on ApiException catch (e) {
      setState(() => _erro = e.mensagem);
    } finally {
      if (mounted) setState(() => _salvando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Cores.superficie,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formulario,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: Marca(tamanho: 30)),
                    const SizedBox(height: 20),
                    const Text('Boas-vindas! Vamos configurar o sistema.',
                        style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 6),
                    const Text(
                      'Crie a conta do administrador. Ele cadastra os professores e as salas com câmera. '
                      'Esta tela só aparece uma vez.',
                      style: TextStyle(color: Cores.textoSecundario, fontSize: 15),
                    ),
                    const SizedBox(height: 22),
                    TextFormField(
                      controller: _nome,
                      textCapitalization: TextCapitalization.words,
                      decoration: const InputDecoration(hintText: 'Seu nome'),
                      validator: (v) => (v ?? '').trim().isEmpty ? 'Informe o nome' : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(hintText: 'E-mail'),
                      validator: (v) => RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch((v ?? '').trim())
                          ? null
                          : 'Informe um e-mail válido',
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _senha,
                      obscureText: true,
                      decoration: const InputDecoration(hintText: 'Senha (mínimo de 8 caracteres)'),
                      validator: (v) => (v ?? '').length < 8 ? 'Use pelo menos 8 caracteres' : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _confirmacao,
                      obscureText: true,
                      decoration: const InputDecoration(hintText: 'Repita a senha'),
                      validator: (v) => v != _senha.text ? 'As senhas não conferem' : null,
                      onFieldSubmitted: (_) => _salvar(),
                    ),
                    if (_erro != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(_erro!, style: const TextStyle(color: Cores.vermelho)),
                      ),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _salvando ? null : _salvar,
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
                      child: _salvando
                          ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                          : const Text('Criar conta e começar'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------- MINHA CONTA ----------------------

Future<void> _abrirMinhaConta(BuildContext context, {required VoidCallback onSair, VoidCallback? onAdministracao}) {
  final nome = _usuario?['nome'] as String? ?? 'Professor';
  return showModalBottomSheet<void>(
    context: context,
    builder: (contexto) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Avatar(nome: nome, tamanho: 64),
          const SizedBox(height: 10),
          Text(nome, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
          Text(_usuario?['email'] as String? ?? '', style: const TextStyle(color: Cores.textoSecundario)),
          if (_ehAdministrador)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Etiqueta(texto: 'Administrador', cor: Cores.azul, fundo: Cores.azulClaro, icone: Icons.shield_outlined),
            ),
          const SizedBox(height: 12),
          if (_ehAdministrador && onAdministracao != null)
            ListTile(
              leading: const CircleAvatar(backgroundColor: Cores.cinzaBotao,
                  child: Icon(Icons.admin_panel_settings_outlined, color: Cores.texto)),
              title: const Text('Administração'),
              subtitle: const Text('Professores e salas'),
              onTap: () {
                Navigator.pop(contexto);
                onAdministracao();
              },
            ),
          ListTile(
            leading: const CircleAvatar(backgroundColor: Cores.cinzaBotao, child: Icon(Icons.key_outlined, color: Cores.texto)),
            title: const Text('Trocar senha'),
            onTap: () {
              Navigator.pop(contexto);
              _trocarSenha(context);
            },
          ),
          ListTile(
            leading: const CircleAvatar(backgroundColor: Cores.vermelhoClaro, child: Icon(Icons.logout, color: Cores.vermelho)),
            title: const Text('Sair', style: TextStyle(color: Cores.vermelho)),
            onTap: () {
              Navigator.pop(contexto);
              onSair();
            },
          ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}

Future<void> _trocarSenha(BuildContext context) async {
  final atual = TextEditingController();
  final nova = TextEditingController();
  final trocou = await showDialog<bool>(
    context: context,
    builder: (contexto) {
      String? erro;
      return StatefulBuilder(
        builder: (contexto, atualizar) => AlertDialog(
          title: const Text('Trocar senha'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: atual, obscureText: true, decoration: const InputDecoration(hintText: 'Senha atual')),
            const SizedBox(height: 10),
            TextField(controller: nova, obscureText: true, decoration: const InputDecoration(hintText: 'Nova senha (8+ caracteres)')),
            if (erro != null)
              Padding(padding: const EdgeInsets.only(top: 10), child: Text(erro!, style: const TextStyle(color: Cores.vermelho))),
          ]),
          actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          actions: [
            TextButton(onPressed: () => Navigator.pop(contexto, false), child: const Text('Cancelar')),
            FilledButton(
              onPressed: () async {
                try {
                  await ApiService.trocarSenha(atual.text, nova.text);
                  if (contexto.mounted) Navigator.pop(contexto, true);
                } on ApiException catch (e) {
                  atualizar(() => erro = e.mensagem);
                }
              },
              child: const Text('Salvar'),
            ),
          ],
        ),
      );
    },
  );
  if (trocou == true && context.mounted) _avisar(context, 'Senha alterada.');
}

// ---------------------- ADMINISTRAÇÃO ----------------------

class AdministracaoScreen extends StatelessWidget {
  const AdministracaoScreen({super.key});
  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 0,
          title: const TituloTela('Administração', subtitulo: 'Professores e salas com câmera'),
          bottom: const TabBar(
            labelColor: Cores.azul,
            unselectedLabelColor: Cores.textoSecundario,
            indicatorColor: Cores.azul,
            labelStyle: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
            tabs: [Tab(text: 'Professores'), Tab(text: 'Salas')],
          ),
        ),
        body: const TabBarView(children: [_AbaProfessores(), _AbaSalas()]),
      ),
    );
  }
}

class _AbaProfessores extends StatefulWidget {
  const _AbaProfessores();
  @override
  State<_AbaProfessores> createState() => _AbaProfessoresState();
}

class _AbaProfessoresState extends State<_AbaProfessores> {
  late Future<List<Map<String, dynamic>>> _futuro = ApiService.listarProfessores();

  void _recarregar() => setState(() => _futuro = ApiService.listarProfessores());

  Future<void> _editar([Map<String, dynamic>? professor]) async {
    final nome = TextEditingController(text: professor?['nome'] as String?);
    final email = TextEditingController(text: professor?['email'] as String?);
    final senha = TextEditingController();
    var administrador = professor?['perfil'] == 'administrador';
    var ativo = professor?['ativo'] as bool? ?? true;
    final salvo = await showDialog<bool>(
      context: context,
      builder: (contexto) {
        String? erro;
        return StatefulBuilder(
          builder: (contexto, atualizar) => AlertDialog(
            title: Text(professor == null ? 'Novo professor' : 'Editar professor'),
            content: SizedBox(
              width: 360,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(controller: nome, textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(hintText: 'Nome')),
                const SizedBox(height: 10),
                TextField(controller: email, keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(hintText: 'E-mail (login)')),
                const SizedBox(height: 10),
                TextField(
                  controller: senha,
                  obscureText: true,
                  decoration: InputDecoration(
                      hintText: professor == null ? 'Senha inicial (8+ caracteres)' : 'Nova senha (opcional)'),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: administrador,
                  onChanged: (v) => atualizar(() => administrador = v),
                  title: const Text('Administrador'),
                  subtitle: const Text('Pode cadastrar professores e salas'),
                ),
                if (professor != null)
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: ativo,
                    onChanged: (v) => atualizar(() => ativo = v),
                    title: const Text('Conta ativa'),
                    subtitle: const Text('Desativada, a conta não entra no app'),
                  ),
                if (erro != null) Text(erro!, style: const TextStyle(color: Cores.vermelho)),
              ]),
            ),
            actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            actions: [
              TextButton(onPressed: () => Navigator.pop(contexto, false), child: const Text('Cancelar')),
              FilledButton(
                onPressed: () async {
                  try {
                    await ApiService.salvarProfessor(professor?['id'] as int?, {
                      'nome': nome.text.trim(),
                      'email': email.text.trim(),
                      'perfil': administrador ? 'administrador' : 'professor',
                      'ativo': ativo,
                      if (senha.text.isNotEmpty) 'senha': senha.text,
                    });
                    if (contexto.mounted) Navigator.pop(contexto, true);
                  } on ApiException catch (e) {
                    atualizar(() => erro = e.mensagem);
                  }
                },
                child: const Text('Salvar'),
              ),
            ],
          ),
        );
      },
    );
    if (salvo == true) _recarregar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'novo_professor',
        onPressed: () => _editar(),
        icon: const Icon(Icons.person_add_alt_1),
        label: const Text('Professor'),
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _futuro,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _MensagemErro(mensagem: snapshot.error.toString(), onTentarNovamente: _recarregar,
                onSair: () => Navigator.pop(context), textoSair: 'Voltar');
          }
          final professores = snapshot.data ?? [];
          return ListView(padding: const EdgeInsets.only(top: 6, bottom: 96), children: [
            Cartao(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(children: [
                for (var i = 0; i < professores.length; i++) ...[
                  if (i > 0) const Divider(indent: 72),
                  ListTile(
                    leading: Avatar(nome: professores[i]['nome'] as String),
                    title: Text(professores[i]['nome'] as String),
                    subtitle: Text(professores[i]['email'] as String),
                    trailing: professores[i]['ativo'] != true
                        ? const Etiqueta(texto: 'Desativado', cor: Cores.textoSecundario, fundo: Cores.fundo)
                        : professores[i]['perfil'] == 'administrador'
                            ? const Etiqueta(texto: 'Admin', cor: Cores.azul, fundo: Cores.azulClaro)
                            : null,
                    onTap: () => _editar(professores[i]),
                  ),
                ],
              ]),
            ),
          ]);
        },
      ),
    );
  }
}

class _AbaSalas extends StatefulWidget {
  const _AbaSalas();
  @override
  State<_AbaSalas> createState() => _AbaSalasState();
}

class _AbaSalasState extends State<_AbaSalas> {
  late Future<List<Map<String, dynamic>>> _futuro = ApiService.listarSalas();

  void _recarregar() => setState(() => _futuro = ApiService.listarSalas());

  Future<void> _editar([Map<String, dynamic>? sala]) async {
    final controle = TextEditingController(text: sala?['nome'] as String?);
    final nome = await showDialog<String>(
      context: context,
      builder: (contexto) => AlertDialog(
        title: Text(sala == null ? 'Nova sala' : 'Renomear sala'),
        content: TextField(controller: controle, autofocus: true,
            decoration: const InputDecoration(hintText: 'Ex.: Sala 12 · Bloco B')),
        actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        actions: [
          TextButton(onPressed: () => Navigator.pop(contexto), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(contexto, controle.text.trim()), child: const Text('Salvar')),
        ],
      ),
    );
    if (nome == null || nome.isEmpty) return;
    try {
      await ApiService.salvarSala(sala?['id'] as int?, nome);
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  Future<void> _excluir(Map<String, dynamic> sala) async {
    final ok = await _confirmar(context, 'Excluir sala?',
        '"${sala['nome']}" será excluída. Turmas que a usavam como sala padrão ficam sem sala.');
    if (!ok) return;
    try {
      await ApiService.excluirSala(sala['id'] as int);
      _recarregar();
    } on ApiException catch (e) {
      if (mounted) _avisar(context, e.mensagem);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'nova_sala',
        onPressed: () => _editar(),
        icon: const Icon(Icons.add_location_alt_outlined),
        label: const Text('Sala'),
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _futuro,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return _MensagemErro(mensagem: snapshot.error.toString(), onTentarNovamente: _recarregar,
                onSair: () => Navigator.pop(context), textoSair: 'Voltar');
          }
          final salas = snapshot.data ?? [];
          if (salas.isEmpty) {
            return const EstadoVazio(
              icone: Icons.meeting_room_outlined,
              titulo: 'Nenhuma sala cadastrada',
              texto: 'Cadastre as salas que têm câmera. Depois, no computador de cada sala, escolha a sala '
                  'no painel do LivePresenceAI.',
            );
          }
          return ListView(padding: const EdgeInsets.only(top: 6, bottom: 96), children: [
            Cartao(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(children: [
                for (var i = 0; i < salas.length; i++) ...[
                  if (i > 0) const Divider(indent: 72),
                  ListTile(
                    leading: const CircleAvatar(backgroundColor: Cores.azulClaro,
                        child: Icon(Icons.meeting_room_outlined, color: Cores.azul)),
                    title: Text(salas[i]['nome'] as String),
                    subtitle: Text(salas[i]['em_uso'] == true ? 'Chamada em andamento agora' : 'Livre'),
                    trailing: salas[i]['em_uso'] == true
                        ? const AoVivo()
                        : IconButton(
                            tooltip: 'Excluir',
                            icon: const Icon(Icons.delete_outline, color: Cores.textoSecundario),
                            onPressed: () => _excluir(salas[i]),
                          ),
                    onTap: () => _editar(salas[i]),
                  ),
                ],
              ]),
            ),
          ]);
        },
      ),
    );
  }
}

/// Escolha da sala ao iniciar a chamada (turma sem sala padrão). Devolve (escolheu, salaId).
Future<(bool, int?)> _escolherSala(BuildContext context) async {
  List<Map<String, dynamic>> salas;
  try {
    salas = await ApiService.listarSalas();
  } on ApiException catch (e) {
    if (context.mounted) _avisar(context, e.mensagem);
    return (false, null);
  }
  if (salas.isEmpty) return (true, null); // sem salas cadastradas: chamada sem câmera
  if (!context.mounted) return (false, null);
  final escolha = await showModalBottomSheet<int>(
    context: context,
    builder: (contexto) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 4),
          child: Text('Em qual sala?', style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
          child: Text('A câmera dessa sala fará a chamada.', style: TextStyle(color: Cores.textoSecundario)),
        ),
        for (final sala in salas)
          ListTile(
            enabled: sala['em_uso'] != true,
            leading: const CircleAvatar(backgroundColor: Cores.azulClaro,
                child: Icon(Icons.meeting_room_outlined, color: Cores.azul)),
            title: Text(sala['nome'] as String),
            subtitle: sala['em_uso'] == true ? const Text('Ocupada: outra chamada em andamento') : null,
            onTap: () => Navigator.pop(contexto, sala['id'] as int),
          ),
        ListTile(
          leading: const CircleAvatar(backgroundColor: Cores.cinzaBotao, child: Icon(Icons.videocam_off_outlined, color: Cores.texto)),
          title: const Text('Sem câmera'),
          subtitle: const Text('Chamada sem reconhecimento facial'),
          onTap: () => Navigator.pop(contexto, -1),
        ),
        const SizedBox(height: 8),
      ]),
    ),
  );
  if (escolha == null) return (false, null);
  return (true, escolha == -1 ? null : escolha);
}
