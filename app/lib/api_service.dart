// LivePresenceAI - Serviço de acesso ao backend FastAPI
// Etapa 5: login, turmas, alunos, sessão, reconhecimento e encerramento/relatório.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'config.dart';

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
      resposta = await http
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
      throw ApiException('E-mail ou senha inválidos.');
    }

    throw ApiException('Erro inesperado no login (código ${resposta.statusCode}).');
  }

  static Future<String?> obterToken() => _storage.read(key: _tokenKey);

  static Future<void> logout() => _storage.delete(key: _tokenKey);

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
    } catch (_) {}
    return null;
  }

  static Future<dynamic> _tratar(http.Response resposta) async {
    if (resposta.statusCode == 200) {
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
      resposta = await http
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

      resposta = await http
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

  // ---------------------- TURMAS E ALUNOS ----------------------

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
  static Future<Map<String, dynamic>> abrirSessao(int turmaId) async {
    final dados = await _post('/sessoes/$turmaId/abrir');
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
