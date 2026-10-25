// Testes do aplicativo: funções de apoio, leitura das respostas do servidor e componentes visuais.
// Uso: flutter test

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:livepresenceai_app/config.dart';
import 'package:livepresenceai_app/main.dart';
import 'package:livepresenceai_app/rede/servidor_encontrado.dart';

void main() {
  group('iniciais do avatar', () {
    test('primeira letra do primeiro e do último nome', () => expect(iniciais('Ana Souza Lima'), 'AL'));
    test('um nome só', () => expect(iniciais('Ana'), 'A'));
    test('ignora símbolos e espaços extras', () => expect(iniciais('  (Bruno)   Costa! '), 'BC'));
  });

  group('endereço do servidor digitado', () {
    test('sem esquema vira https', () => expect(normalizarServidor('192.168.0.10:8443'), 'https://192.168.0.10:8443'));
    test('mantém http e tira a barra final', () => expect(normalizarServidor('http://host:8000/'), 'http://host:8000'));
    test('vazio volta ao padrão', () => expect(normalizarServidor('   '), servidorPadrao));
  });

  test('servidor encontrado na rede (resposta UDP do backend)', () {
    final s = ServidorEncontrado.fromJson(
        {'projeto': 'LivePresenceAI', 'nome': 'SERVIDOR', 'url': 'https://10.0.0.5:8443', 'certificado_sha256': 'ab'});
    expect(s.url, 'https://10.0.0.5:8443');
    expect(s.certificadoSha256, 'ab');
    expect(ServidorEncontrado.fromJson({'url': 'http://x'}).nome, 'Servidor');
  });

  test('frequência do aluno (resposta de GET /turmas/{id}/frequencia)', () {
    final a = FrequenciaAluno.fromJson({
      'aluno_id': 1, 'nome': 'Bia', 'ra': 'R1', 'aulas': 4, 'presencas': 2, 'faltas': 2, 'ajustes_manuais': 1,
      'percentual': 50.0, 'abaixo_do_minimo': true, 'por_aula': ['P', 'F', null, 'P'],
    });
    expect(a.abaixoDoMinimo, isTrue);
    expect(a.porAula, ['P', 'F', null, 'P']);
    final novo = FrequenciaAluno.fromJson({
      'aluno_id': 2, 'nome': 'Davi', 'aulas': 0, 'presencas': 0, 'faltas': 0, 'ajustes_manuais': 0,
      'percentual': null, 'abaixo_do_minimo': false, 'por_aula': [],
    });
    expect(novo.percentual, isNull);
  });

  testWidgets('avatar mostra as iniciais e o selo', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Avatar(nome: 'Carla Mendes', selo: Selo(icone: Icons.check, cor: Colors.green))),
    ));
    expect(find.text('CM'), findsOneWidget);
    expect(find.byIcon(Icons.check), findsOneWidget);
  });

  testWidgets('etiqueta mostra texto e ícone', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Etiqueta(texto: '3 com rosto', cor: Colors.green, fundo: Colors.white, icone: Icons.face)),
    ));
    expect(find.text('3 com rosto'), findsOneWidget);
    expect(find.byIcon(Icons.face), findsOneWidget);
  });
}
