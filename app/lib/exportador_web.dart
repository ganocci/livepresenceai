// Versão web: baixa o arquivo pelo navegador.

import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

/// Entrega o arquivo ao usuário e devolve a mensagem a exibir.
Future<String> entregarArquivo(Uint8List bytes, String nome, String tipo) async {
  final blob = web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: tipo));
  final url = web.URL.createObjectURL(blob);
  final link = web.document.createElement('a') as web.HTMLAnchorElement
    ..href = url
    ..download = nome;
  web.document.body!.appendChild(link);
  link.click();
  link.remove();
  web.URL.revokeObjectURL(url);
  return 'Arquivo $nome baixado.';
}

/// No navegador a câmera não grava arquivo em disco: nada a apagar.
Future<void> apagarArquivoTemporario(String caminho) async {}
