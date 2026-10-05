// LivePresenceAI - Servidor encontrado na rede local pela descoberta (backend/descoberta.py).

class ServidorEncontrado {
  final String nome; // nome do computador
  final String url; // ex.: https://192.168.0.10:8443
  final String? certificadoSha256; // impressão digital do certificado HTTPS (pinning), ou null em HTTP

  ServidorEncontrado({required this.nome, required this.url, this.certificadoSha256});

  factory ServidorEncontrado.fromJson(Map<String, dynamic> json) => ServidorEncontrado(
        nome: json['nome'] as String? ?? 'Servidor',
        url: json['url'] as String,
        certificadoSha256: json['certificado_sha256'] as String?,
      );
}
