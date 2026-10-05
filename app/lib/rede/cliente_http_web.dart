import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

/// No navegador, o certificado é validado pelo próprio navegador; a impressão digital não se aplica.
http.Client criarCliente(String? certificadoSha256) => http.Client();

WebSocketChannel conectarWebSocket(Uri endereco, String? certificadoSha256) => WebSocketChannel.connect(endereco);
