// Versão Android/iOS (e desktop): grava em pasta temporária e abre o compartilhamento do sistema.

import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Entrega o arquivo ao usuário e devolve a mensagem a exibir.
Future<String> entregarArquivo(Uint8List bytes, String nome, String tipo) async {
  final pasta = await getTemporaryDirectory();
  final arquivo = File('${pasta.path}${Platform.pathSeparator}$nome');
  await arquivo.writeAsBytes(bytes, flush: true);
  await Share.shareXFiles([XFile(arquivo.path, mimeType: tipo, name: nome)], subject: nome);
  return 'Arquivo $nome pronto para salvar ou compartilhar.';
}

/// Apaga o arquivo temporário criado pela câmera (as fotos do cadastro facial não são guardadas).
Future<void> apagarArquivoTemporario(String caminho) async {
  try {
    await File(caminho).delete();
  } catch (_) {}
}
