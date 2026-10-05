// LivePresenceAI - Endereço do servidor (backend).
//
// - App web servido pelo próprio servidor (versão de produção): usa o mesmo endereço da página.
// - Celular e desenvolvimento: usa o endereço salvo na tela de login (ex.: https://192.168.0.10:8443);
//   sem endereço salvo, o padrão de desenvolvimento http://127.0.0.1:8000.

import 'package:flutter/foundation.dart';

const String servidorPadrao = 'http://127.0.0.1:8000';

/// Endereço atual do backend (sem barra no final). Alterado por [definirServidor].
String apiBaseUrl = _enderecoInicial();

/// Mesmo endereço, com ws:// ou wss:// para o tempo real.
String get wsBaseUrl => apiBaseUrl.replaceFirst(RegExp(r'^http'), 'ws');

/// No navegador, em produção, o app é entregue pelo próprio backend: o servidor é a origem da página.
bool get servidorDefinidoPelaPagina => kIsWeb && !kDebugMode && Uri.base.scheme.startsWith('http');

String _enderecoInicial() => servidorDefinidoPelaPagina ? Uri.base.origin : servidorPadrao;

/// Normaliza o que o usuário digitou: acrescenta https:// se faltar e remove a barra final.
String normalizarServidor(String texto) {
  var endereco = texto.trim();
  if (endereco.isEmpty) return servidorPadrao;
  if (!endereco.startsWith('http://') && !endereco.startsWith('https://')) {
    endereco = 'https://$endereco';
  }
  return endereco.replaceAll(RegExp(r'/+$'), '');
}

void definirServidor(String endereco) => apiBaseUrl = normalizarServidor(endereco);
