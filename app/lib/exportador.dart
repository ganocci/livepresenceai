// LivePresenceAI - Entrega do arquivo exportado (CSV, PDF ou XLSX) ao professor.
// No navegador o arquivo é baixado; no Android/iOS é gravado em pasta temporária e aberto na
// folha de compartilhamento do sistema (salvar, enviar por e-mail, WhatsApp etc.).

export 'exportador_io.dart' if (dart.library.js_interop) 'exportador_web.dart';
