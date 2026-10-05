// Pinning do certificado do servidor (Dart puro: também roda com `dart run`).

import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// HttpClient que, além dos certificados confiáveis do sistema, aceita o certificado cujo SHA-256 (do DER)
/// é igual a [certificadoSha256] — a impressão digital anunciada pelo servidor na descoberta.
HttpClient _httpClient(String? certificadoSha256) {
  final cliente = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  if (certificadoSha256 != null && certificadoSha256.isNotEmpty) {
    final esperado = certificadoSha256.toLowerCase();
    cliente.badCertificateCallback =
        (X509Certificate certificado, String host, int porta) => sha256.convert(certificado.der).toString() == esperado;
  }
  return cliente;
}

http.Client criarCliente(String? certificadoSha256) => IOClient(_httpClient(certificadoSha256));

WebSocketChannel conectarWebSocket(Uri endereco, String? certificadoSha256) =>
    IOWebSocketChannel.connect(endereco, customClient: _httpClient(certificadoSha256));
