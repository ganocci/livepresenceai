// LivePresenceAI - Serviço de acesso ao backend FastAPI
// Etapa 5: login, turmas, alunos, sessão, reconhecimento e encerramento/relatório.

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'config.dart';
import 'rede/cliente_http.dart';
import 'rede/descoberta.dart';

class ApiException implements Exception {
  final String mensagem;
  ApiException(this.mensagem);

  @override
  String toString() => mensagem;
}

class ApiService {
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'access_token';
  static const _timeout = Duration(seconds: 10);

  // ---------------------- AUTENTICAÇÃO ----------------------

  static Future<void> login(String email, String senha) async {
    http.Response resposta;
    try {
      resposta = await _cliente
          .post(
            Uri.parse('$apiBaseUrl/login'),
            body: {'username': email, 'password': senha},
          )
          .timeout(_timeout);
    } on TimeoutException {
      throw ApiException('O servidor demorou para responder.');
    } catch (_) {
      throw ApiException(
        'Não foi possível conectar ao servidor. Verifique se o backend está rodando.',
      );
    }

    if (resposta.statusCode == 200) {
      final dados = jsonDecode(utf8.decode(resposta.bodyBytes)) as Map<String, dynamic>;
      await _storage.write(key: _tokenKey, value: dados['access_token'] as String);
      return;
    }

    if (resposta.statusCode == 401) {
      // "E-mail ou senha incorretos" ou "Conta desativada. Procure o administrador."
      throw ApiException(_detalhe(resposta) ?? 'E-mail ou senha incorretos.');
    }

    throw ApiException('Erro inesperado no login (código ${resposta.statusCode}).');
  }

  static Future<String?> obterToken() => _storage.read(key: _tokenKey);

  static Future<void> logout() => _storage.delete(key: _tokenKey);

  // ---------------------- SERVIDOR E PRIMEIRO ACESSO ----------------------

  static const _servidorKey = 'servidor';
  static const _certificadoKey = 'servidor_certificado';

  /// Impressão digital do certificado do servidor (pinning), recebida na descoberta.
  static String? _certificado;
  static http.Client _cliente = criarCliente(null);

  static void _usarServidor(String url, String? certificado) {
    definirServidor(url);
    _certificado = certificado;
    _cliente.close();
    _cliente = criarCliente(certificado);
  }

  /// Há um servidor escolhido? (No app web de produção, sempre: é a própria página.)
  static Future<bool> temServidorSalvo() async =>
      servidorDefinidoPelaPagina || (await _storage.read(key: _servidorKey)) != null;

  /// Canal do tempo real com o mesmo pinning do cliente HTTP.
  static WebSocketChannel abrirWebSocket(Uri endereco) => conectarWebSocket(endereco, _certificado);

  /// Procura servidores LivePresenceAI na rede local (UDP); vazio no navegador.
  static Future<List<ServidorEncontrado>> procurarNaRede() => procurarServidores();

  /// Conecta a um servidor encontrado: confere que responde (com o certificado anunciado) e salva.
  static Future<void> usarServidorEncontrado(ServidorEncontrado servidor) async {
    final teste = criarCliente(servidor.certificadoSha256);
    try {
      final resposta = await teste.get(Uri.parse('${servidor.url}/')).timeout(const Duration(seconds: 6));
      final dados = jsonDecode(utf8.decode(resposta.bodyBytes));
      if (resposta.statusCode != 200 || dados is! Map || dados['projeto'] != 'LivePresenceAI') {
        throw ApiException('O servidor encontrado não respondeu como esperado.');
      }
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('Não foi possível conectar a ${servidor.nome} (${servidor.url}).');
    } finally {
      teste.close();
    }
    final anterior = apiBaseUrl;
    _usarServidor(servidor.url, servidor.certificadoSha256);
    await _storage.write(key: _servidorKey, value: servidor.url);
    if (servidor.certificadoSha256 != null) {
      await _storage.write(key: _certificadoKey, value: servidor.certificadoSha256);
    } else {
      await _storage.delete(key: _certificadoKey);
    }
    // Mesmo servidor com outro IP (ex.: o roteador trocou o endereço): a sessão continua valendo
    if (Uri.parse(anterior).port != Uri.parse(servidor.url).port) await logout();
  }

  /// Carrega o endereço do servidor salvo (celular/desenvolvimento). No app web de produção, o servidor é
  /// a própria página e nada é carregado.
  static Future<void> carregarServidor() async {
    if (servidorDefinidoPelaPagina) return;
    final salvo = await _storage.read(key: _servidorKey);
    if (salvo != null && salvo.isNotEmpty) _usarServidor(salvo, await _storage.read(key: _certificadoKey));
  }

  /// Testa o endereço (GET /) e, se responder, passa a usá-lo e o salva.
  static Future<void> alterarServidor(String endereco) async {
    final candidato = normalizarServidor(endereco);
    try {
      final resposta = await criarCliente(null).get(Uri.parse('$candidato/')).timeout(const Duration(seconds: 6));
      final dados = jsonDecode(utf8.decode(resposta.bodyBytes));
      if (resposta.statusCode != 200 || dados is! Map || dados['projeto'] != 'LivePresenceAI') {
        throw ApiException('Esse endereço respondeu, mas não é um servidor LivePresenceAI.');
      }
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('Não foi possível falar com $candidato. Confira o endereço e a rede, ou use '
          '"Procurar na rede" (com HTTPS, o celular só confia no servidor encontrado pela busca ou com o '
          'certificado instalado).');
    }
    _usarServidor(candidato, null);
    await _storage.write(key: _servidorKey, value: candidato);
    await _storage.delete(key: _certificadoKey);
    await logout(); // o token de outro servidor não vale aqui
  }

  /// GET /configuracao/estado -> o sistema já tem administrador?
  static Future<bool> sistemaConfigurado() async {
    http.Response resposta;
    try {
      resposta = await _cliente.get(Uri.parse('$apiBaseUrl/configuracao/estado')).timeout(_timeout);
    } catch (e) {
      throw _erroDeRede(e);
    }
    final dados = await _tratar(resposta) as Map<String, dynamic>;
    return dados['configurado'] == true;
  }

  /// POST /configuracao/inicial: cria o primeiro administrador e já entra com ele.
  static Future<void> configurarSistema(String nome, String email, String senha) async {
    http.Response resposta;
    try {
      resposta = await _cliente
          .post(Uri.parse('$apiBaseUrl/configuracao/inicial'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'nome': nome, 'email': email, 'senha': senha}))
          .timeout(_timeout);
    } catch (e) {
      throw _erroDeRede(e);
    }
    final dados = await _tratar(resposta) as Map<String, dynamic>;
    await _storage.write(key: _tokenKey, value: dados['access_token'] as String);
  }

  /// GET /eu -> {id, nome, email, perfil, ativo}; serve também para validar o token salvo.
  static Future<Map<String, dynamic>> eu() async => await _get('/eu') as Map<String, dynamic>;

  static Future<void> trocarSenha(String atual, String nova) =>
      _enviar('PUT', '/eu/senha', json: {'senha_atual': atual, 'nova_senha': nova});

  // ---------------------- ADMINISTRAÇÃO ----------------------

  static Future<List<Map<String, dynamic>>> listarProfessores() async =>
      (await _get('/professores') as List<dynamic>).cast<Map<String, dynamic>>();

  static Future<void> salvarProfessor(int? id, Map<String, dynamic> dados) =>
      id == null ? _post('/professores', json: dados) : _enviar('PUT', '/professores/$id', json: dados);

  static Future<List<Map<String, dynamic>>> listarSalas() async =>
      (await _get('/salas') as List<dynamic>).cast<Map<String, dynamic>>();

  static Future<void> salvarSala(int? id, String nome) =>
      id == null ? _post('/salas', json: {'nome': nome}) : _enviar('PUT', '/salas/$id', json: {'nome': nome});

  static Future<void> excluirSala(int id) => _enviar('DELETE', '/salas/$id');

  static Future<Map<String, String>> cabecalhosAutenticados() async {
    final token = await obterToken();
    return {'Authorization': 'Bearer $token'};
  }

  // ---------------------- TRATAMENTO COMUM DE RESPOSTA ----------------------

  static String? _detalhe(http.Response resposta) {
    try {
      final corpo = jsonDecode(utf8.decode(resposta.bodyBytes));
      if (corpo is Map && corpo['detail'] is String) {
        return corpo['detail'] as String;
      }
      // 422 do FastAPI: lista de erros de validação; mostra só as mensagens
      if (corpo is Map && corpo['detail'] is List) {
        return (corpo['detail'] as List)
            .map((e) => (e is Map ? e['msg']?.toString() ?? '' : '').replaceFirst('Value error, ', ''))
            .where((m) => m.isNotEmpty)
            .join('\n');
      }
    } catch (_) {}
    return null;
  }

  static Future<dynamic> _tratar(http.Response resposta) async {
    if (resposta.statusCode == 204) return null;
    if (resposta.statusCode >= 200 && resposta.statusCode < 300) {
      return jsonDecode(utf8.decode(resposta.bodyBytes));
    }

    if (resposta.statusCode == 401) {
      await logout();
      throw ApiException('Sessão expirada. Faça login novamente.');
    }

    if (resposta.statusCode == 404) {
      throw ApiException(_detalhe(resposta) ?? 'Recurso não encontrado.');
    }

    throw ApiException(
      _detalhe(resposta) ?? 'Erro inesperado (código ${resposta.statusCode}).',
    );
  }

  static ApiException _erroDeRede(Object erro) {
    if (erro is TimeoutException) {
      return ApiException('O servidor demorou para responder.');
    }
    return ApiException(
      'Não foi possível conectar ao servidor. Verifique se o backend está rodando.',
    );
  }

  // ---------------------- GET / POST AUTENTICADOS ----------------------

  static Future<dynamic> _get(String caminho) async {
    http.Response resposta;
    try {
      resposta = await _cliente
          .get(
            Uri.parse('$apiBaseUrl$caminho'),
            headers: await cabecalhosAutenticados(),
          )
          .timeout(_timeout);
    } catch (e) {
      throw _erroDeRede(e);
    }
    return _tratar(resposta);
  }

  static Future<dynamic> _post(String caminho, {Map<String, dynamic>? json}) async {
    http.Response resposta;
    try {
      final cabecalhos = await cabecalhosAutenticados();
      if (json != null) cabecalhos['Content-Type'] = 'application/json';

      resposta = await _cliente
          .post(
            Uri.parse('$apiBaseUrl$caminho'),
            headers: cabecalhos,
            body: json != null ? jsonEncode(json) : null,
          )
          .timeout(_timeout);
    } catch (e) {
      throw _erroDeRede(e);
    }
    return _tratar(resposta);
  }

  static Future<dynamic> _enviar(String metodo, String caminho, {Map<String, dynamic>? json}) async {
    http.Response resposta;
    try {
      final requisicao = http.Request(metodo, Uri.parse('$apiBaseUrl$caminho'))
        ..headers.addAll(await cabecalhosAutenticados());
      if (json != null) {
        requisicao.headers['Content-Type'] = 'application/json';
        requisicao.body = jsonEncode(json);
      }
      resposta = await http.Response.fromStream(await _cliente.send(requisicao).timeout(_timeout));
    } catch (e) {
      throw _erroDeRede(e);
    }
    return _tratar(resposta);
  }

  // ---------------------- TURMAS E ALUNOS ----------------------

  /// [salaId]: sala padrão das chamadas da turma (opcional).
  static Future<Map<String, dynamic>> criarTurma(String nome, int? salaId) async =>
      await _post('/turmas', json: {'nome': nome, 'sala_id': salaId}) as Map<String, dynamic>;

  static Future<Map<String, dynamic>> editarTurma(int turmaId, String nome, int? salaId) async =>
      await _enviar('PUT', '/turmas/$turmaId', json: {'nome': nome, 'sala_id': salaId}) as Map<String, dynamic>;

  /// Só funciona para turma sem aulas registradas (o backend responde 409 nos demais casos).
  static Future<void> excluirTurma(int turmaId) => _enviar('DELETE', '/turmas/$turmaId');

  /// [autorizou]: o aluno autorizou o reconhecimento facial no termo assinado na matrícula.
  static Future<Map<String, dynamic>> criarAluno(int turmaId, String nome, String ra, bool autorizou) async =>
      await _post('/turmas/$turmaId/alunos',
          json: {'nome': nome, 'ra': ra, 'autorizou_biometria': autorizou}) as Map<String, dynamic>;

  /// Desmarcar [autorizou] revoga a autorização e o backend apaga o cadastro facial.
  static Future<Map<String, dynamic>> editarAluno(int alunoId, String nome, String ra, bool autorizou) async =>
      await _enviar('PUT', '/alunos/$alunoId',
          json: {'nome': nome, 'ra': ra, 'autorizou_biometria': autorizou}) as Map<String, dynamic>;

  /// POST /alunos/{id}/rosto (multipart): as fotos viram o vetor facial no servidor e são descartadas.
  static Future<Map<String, dynamic>> cadastrarRosto(int alunoId, List<Uint8List> fotos) async {
    http.Response resposta;
    try {
      final requisicao = http.MultipartRequest('POST', Uri.parse('$apiBaseUrl/alunos/$alunoId/rosto'))
        ..headers.addAll(await cabecalhosAutenticados());
      for (var i = 0; i < fotos.length; i++) {
        requisicao.files.add(http.MultipartFile.fromBytes('fotos', fotos[i], filename: 'foto$i.jpg'));
      }
      // A primeira vez o servidor carrega o modelo de reconhecimento (alguns segundos)
      resposta = await http.Response.fromStream(await _cliente.send(requisicao).timeout(const Duration(seconds: 60)));
    } catch (e) {
      throw _erroDeRede(e);
    }
    return await _tratar(resposta) as Map<String, dynamic>;
  }

  /// PUT /sessoes/{id}/ajustes/{aluno}: presença ou falta manual com motivo (RN-15).
  static Future<void> ajustarChamada(int sessaoId, int alunoId, String situacao, String motivo) =>
      _enviar('PUT', '/sessoes/$sessaoId/ajustes/$alunoId', json: {'situacao': situacao, 'motivo': motivo});

  /// DELETE /sessoes/{id}/ajustes/{aluno}: volta a valer o cálculo automático.
  static Future<void> removerAjuste(int sessaoId, int alunoId) =>
      _enviar('DELETE', '/sessoes/$sessaoId/ajustes/$alunoId');

  /// DELETE /alunos/{id}/rosto: apaga o cadastro facial; a autorização continua registrada.
  static Future<Map<String, dynamic>> excluirRosto(int alunoId) async =>
      await _enviar('DELETE', '/alunos/$alunoId/rosto') as Map<String, dynamic>;

  /// Só funciona para aluno sem presenças registradas (409 nos demais casos).
  static Future<void> excluirAluno(int alunoId) => _enviar('DELETE', '/alunos/$alunoId');

  // ---------------------- HISTÓRICO E EXPORTAÇÃO ----------------------

  /// GET /turmas/{id}/sessoes -> aulas da turma, da mais recente para a mais antiga.
  static Future<List<Map<String, dynamic>>> historico(int turmaId) async {
    final dados = await _get('/turmas/$turmaId/sessoes') as List<dynamic>;
    return dados.cast<Map<String, dynamic>>();
  }

  /// GET /sessoes/{id}/relatorio -> relatório de uma aula encerrada.
  static Future<Map<String, dynamic>> relatorio(int sessaoId) async =>
      await _get('/sessoes/$sessaoId/relatorio') as Map<String, dynamic>;

  /// GET /sessoes/{id}/exportar?formato=csv|xlsx|pdf -> conteúdo e nome do arquivo.
  static Future<({Uint8List bytes, String nome, String tipo})> exportar(int sessaoId, String formato) async {
    http.Response resposta;
    try {
      resposta = await _cliente
          .get(Uri.parse('$apiBaseUrl/sessoes/$sessaoId/exportar?formato=$formato'),
              headers: await cabecalhosAutenticados())
          .timeout(const Duration(seconds: 30));
    } catch (e) {
      throw _erroDeRede(e);
    }
    if (resposta.statusCode != 200) {
      await _tratar(resposta); // lança a ApiException com a mensagem do backend
    }
    final disposicao = resposta.headers['content-disposition'] ?? '';
    final nome = RegExp(r'filename="([^"]+)"').firstMatch(disposicao)?.group(1) ??
        'chamada_aula$sessaoId.$formato';
    final tipo = resposta.headers['content-type'] ?? 'application/octet-stream';
    return (bytes: resposta.bodyBytes, nome: nome, tipo: tipo);
  }

  static Future<List<Map<String, dynamic>>> listarTurmas() async {
    final dados = await _get('/turmas') as List<dynamic>;
    return dados.cast<Map<String, dynamic>>();
  }

  static Future<List<Map<String, dynamic>>> listarAlunos(int turmaId) async {
    final dados = await _get('/turmas/$turmaId/alunos') as List<dynamic>;
    return dados.cast<Map<String, dynamic>>();
  }

  // ---------------------- SESSÃO ----------------------

  /// POST /sessoes/{turmaId}/abrir -> {id, turma_id, status, inicio, fim}
  /// [salaId]: sala da chamada; sem ela, o backend usa a sala padrão da turma.
  static Future<Map<String, dynamic>> abrirSessao(int turmaId, {int? salaId}) async {
    final dados = await _post('/sessoes/$turmaId/abrir${salaId != null ? '?sala_id=$salaId' : ''}');
    return dados as Map<String, dynamic>;
  }

  /// GET /sessoes/{sessaoId} -> estado atual (registros e parâmetros), usado ao reconectar.
  static Future<Map<String, dynamic>> consultarSessao(int sessaoId) async {
    final dados = await _get('/sessoes/$sessaoId');
    return dados as Map<String, dynamic>;
  }

  /// POST /sessoes/{sessaoId}/reconhecimento -> {registrado: bool, ...}
  /// Hoje é chamado pelo botão de simulação; depois será chamado pela IA real.
  static Future<bool> reconhecer(int sessaoId, int alunoId, double confianca) async {
    final dados = await _post(
      '/sessoes/$sessaoId/reconhecimento',
      json: {'aluno_id': alunoId, 'confianca': confianca},
    ) as Map<String, dynamic>;
    return dados['registrado'] == true;
  }

  /// POST /sessoes/{sessaoId}/encerrar -> {sessao_id, status, registros: [...]}
  static Future<Map<String, dynamic>> encerrarSessao(int sessaoId) async {
    final dados = await _post('/sessoes/$sessaoId/encerrar');
    return dados as Map<String, dynamic>;
  }
}
