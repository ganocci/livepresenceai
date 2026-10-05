// LivePresenceAI - Cliente HTTP e WebSocket.
// Celular/desktop (cliente_http_io.dart): confia no certificado do servidor pela impressão digital recebida na
// descoberta (pinning), sem instalar a CA no aparelho. Navegador: cliente padrão do navegador.

export 'cliente_http_io.dart' if (dart.library.js_interop) 'cliente_http_web.dart';
