// Descoberta por broadcast UDP (protocolo em backend/descoberta.py). Dart puro: também roda com `dart run`.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'servidor_encontrado.dart';

const int portaDescoberta = 47800;
const String perguntaDescoberta = 'LIVEPRESENCEAI_PROCURA';

/// Envia a pergunta três vezes durante [tempo] e devolve os servidores que responderam.
Future<List<ServidorEncontrado>> procurarServidores({Duration tempo = const Duration(seconds: 3)}) async {
  final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
  socket.broadcastEnabled = true;

  // Broadcast geral e o broadcast de cada rede /24 do aparelho (alguns roteadores ignoram 255.255.255.255)
  final destinos = <String>{'255.255.255.255'};
  try {
    for (final interface in await NetworkInterface.list(type: InternetAddressType.IPv4)) {
      for (final endereco in interface.addresses.where((a) => !a.isLoopback)) {
        final partes = endereco.address.split('.');
        destinos.add('${partes[0]}.${partes[1]}.${partes[2]}.255');
      }
    }
  } catch (_) {
    // sem permissão para listar interfaces: fica só o broadcast geral
  }

  final encontrados = <String, ServidorEncontrado>{};
  final assinatura = socket.listen((evento) {
    if (evento != RawSocketEvent.read) return;
    final datagrama = socket.receive();
    if (datagrama == null) return;
    try {
      final dados = jsonDecode(utf8.decode(datagrama.data));
      if (dados is Map<String, dynamic> && dados['projeto'] == 'LivePresenceAI' && dados['url'] is String) {
        final servidor = ServidorEncontrado.fromJson(dados);
        encontrados[servidor.url] = servidor;
      }
    } catch (_) {
      // resposta que não é do LivePresenceAI
    }
  });

  final pergunta = utf8.encode(perguntaDescoberta);
  for (var rodada = 0; rodada < 3; rodada++) {
    for (final destino in destinos) {
      try {
        socket.send(pergunta, InternetAddress(destino), portaDescoberta);
      } catch (_) {}
    }
    await Future.delayed(Duration(milliseconds: tempo.inMilliseconds ~/ 3));
  }
  await assinatura.cancel();
  socket.close();
  return encontrados.values.toList()..sort((a, b) => a.nome.compareTo(b.nome));
}
