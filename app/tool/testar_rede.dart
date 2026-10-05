// LivePresenceAI - Teste da descoberta e do pinning (Dart puro, sem Flutter).
// Uso (servidor ligado pelo painel, na mesma rede):  dart run tool/testar_rede.dart
// ignore_for_file: avoid_print

import 'dart:async';

import 'package:livepresenceai_app/rede/cliente_http_io.dart';
import 'package:livepresenceai_app/rede/descoberta_io.dart';

Future<void> main() async {
  final relogio = Stopwatch()..start();
  final achados = await procurarServidores();
  print('descoberta: ${achados.length} servidor(es) em ${relogio.elapsedMilliseconds} ms');
  for (final s in achados) {
    print('  ${s.nome} ${s.url} certificado=${s.certificadoSha256 == null ? '-' : '${s.certificadoSha256!.substring(0, 16)}…'}');
  }
  final https = achados.where((s) => s.url.startsWith('https')).toList();
  if (https.isEmpty) {
    print('nenhum servidor HTTPS encontrado');
    return;
  }
  final servidor = https.first;

  Future<String> tentar(String rotulo, String? pin) async {
    final cliente = criarCliente(pin);
    try {
      final r = await cliente.get(Uri.parse('${servidor.url}/')).timeout(const Duration(seconds: 6));
      return '$rotulo: HTTP ${r.statusCode} ${r.body.contains('LivePresenceAI') ? '(LivePresenceAI)' : ''}';
    } catch (e) {
      return '$rotulo: recusado (${e.runtimeType})';
    } finally {
      cliente.close();
    }
  }

  print(await tentar('com a impressão digital da descoberta', servidor.certificadoSha256));
  print(await tentar('sem impressão digital (CA não instalada)', null));
  print(await tentar('com impressão digital errada', '0' * 64));

  final ws = servidor.url.replaceFirst('https', 'wss');
  Future<String> tentarWs(String rotulo, String? pin) async {
    try {
      final canal = conectarWebSocket(Uri.parse('$ws/ws/sessoes/1?token=invalido'), pin);
      await canal.ready.timeout(const Duration(seconds: 6));
      await canal.stream.drain<void>().timeout(const Duration(seconds: 6));
      return '$rotulo: TLS ok, servidor fechou com código ${canal.closeCode} (token inválido, esperado)';
    } catch (e) {
      // O backend recusa o token inválido antes de aceitar a conexão (HTTP 403): o TLS passou
      if ('$e'.contains('403')) {
        return '$rotulo: TLS ok, servidor recusou o token inválido (403, esperado)';
      }
      return '$rotulo: recusado (${e.runtimeType}: $e)';
    }
  }

  print(await tentarWs('WebSocket com a impressão digital', servidor.certificadoSha256));
  print(await tentarWs('WebSocket sem impressão digital', null));
}
