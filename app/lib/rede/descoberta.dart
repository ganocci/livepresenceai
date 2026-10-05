// LivePresenceAI - Procura o servidor na rede local, sem o usuário digitar o IP.
// Celular/desktop: broadcast UDP (descoberta_io.dart). Navegador: não se aplica (o app web é entregue pelo
// próprio servidor), então devolve lista vazia.

export 'descoberta_io.dart' if (dart.library.js_interop) 'descoberta_web.dart';
export 'servidor_encontrado.dart';
