// LivePresenceAI - Ajuste manual da chamada (RN-15): presença ou falta marcada pelo professor, com motivo.
// Usado na chamada ao vivo (ex.: aluno sem autorização de biometria) e no relatório (correções depois da aula).
// Parte da biblioteca de main.dart.

part of 'main.dart';

/// Ajuste já feito para um aluno numa aula.
class AjusteManual {
  final String situacao; // 'presenca' | 'falta'
  final String motivo;
  AjusteManual(this.situacao, this.motivo);

  bool get presenca => situacao == 'presenca';

  factory AjusteManual.fromJson(Map<String, dynamic> json) =>
      AjusteManual(json['situacao'] as String, json['motivo'] as String);
}

const _motivosPresenca = ['Sem biometria (não autorizou)', 'Câmera não reconheceu', 'Chegou atrasado', 'Presença confirmada pelo professor'];
const _motivosFalta = ['Falta justificada', 'Atestado médico', 'Saiu no início da aula', 'Reconhecimento indevido'];

/// Folha para marcar presença/falta manual ou desfazer o ajuste. Devolve true se algo mudou.
Future<bool> _ajustarAluno(BuildContext context,
    {required int sessaoId, required int alunoId, required String nome, AjusteManual? atual, bool semBiometria = false}) async {
  final mudou = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _FolhaAjuste(
        sessaoId: sessaoId, alunoId: alunoId, nome: nome, atual: atual, semBiometria: semBiometria),
  );
  return mudou ?? false;
}

class _FolhaAjuste extends StatefulWidget {
  final int sessaoId;
  final int alunoId;
  final String nome;
  final AjusteManual? atual;
  final bool semBiometria;
  const _FolhaAjuste(
      {required this.sessaoId, required this.alunoId, required this.nome, this.atual, this.semBiometria = false});
  @override
  State<_FolhaAjuste> createState() => _FolhaAjusteState();
}

class _FolhaAjusteState extends State<_FolhaAjuste> {
  late String _situacao = widget.atual?.situacao ?? 'presenca';
  late String? _motivo = widget.atual?.motivo ?? (widget.semBiometria ? _motivosPresenca.first : null);
  final _outro = TextEditingController();
  bool _salvando = false;
  String? _erro;

  List<String> get _sugestoes => _situacao == 'presenca' ? _motivosPresenca : _motivosFalta;

  Future<void> _executar(Future<void> Function() acao) async {
    setState(() {
      _salvando = true;
      _erro = null;
    });
    try {
      await acao();
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      setState(() => _erro = e.mensagem);
    } finally {
      if (mounted) setState(() => _salvando = false);
    }
  }

  void _salvar() {
    final motivo = _outro.text.trim().isNotEmpty ? _outro.text.trim() : (_motivo ?? '');
    if (motivo.length < 3) {
      setState(() => _erro = 'Escolha ou escreva o motivo.');
      return;
    }
    _executar(() => ApiService.ajustarChamada(widget.sessaoId, widget.alunoId, _situacao, motivo));
  }

  Widget _opcaoSituacao(String valor, String texto, IconData icone, Color cor) {
    final escolhida = _situacao == valor;
    return Expanded(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => setState(() {
          _situacao = valor;
          if (_motivo != null && !_sugestoes.contains(_motivo)) _motivo = null;
        }),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: escolhida ? cor.withValues(alpha: 0.12) : Cores.fundo,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: escolhida ? cor : Colors.transparent, width: 1.5),
          ),
          child: Column(children: [
            Icon(icone, color: escolhida ? cor : Cores.textoSecundario),
            const SizedBox(height: 4),
            Text(texto, style: TextStyle(fontWeight: FontWeight.w700, color: escolhida ? cor : Cores.texto)),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(context).viewInsets.bottom + 20),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Avatar(nome: widget.nome, tamanho: 44),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(widget.nome, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                  const Text('Ajuste manual da chamada', style: TextStyle(color: Cores.textoSecundario)),
                ]),
              ),
            ]),
            if (widget.semBiometria)
              Container(
                margin: const EdgeInsets.only(top: 12),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: Cores.azulClaro, borderRadius: BorderRadius.circular(10)),
                child: const Text('Este aluno não tem cadastro facial: a câmera não o reconhece. Marque a presença '
                    'aqui quando ele estiver na aula.', style: TextStyle(color: Cores.azul, fontSize: 13)),
              ),
            const SizedBox(height: 14),
            Row(children: [
              _opcaoSituacao('presenca', 'Presença', Icons.check_circle_outline, Cores.verde),
              const SizedBox(width: 10),
              _opcaoSituacao('falta', 'Falta', Icons.cancel_outlined, Cores.vermelho),
            ]),
            const SizedBox(height: 14),
            const Text('Motivo', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final sugestao in _sugestoes)
                ChoiceChip(
                  label: Text(sugestao),
                  selected: _motivo == sugestao && _outro.text.isEmpty,
                  onSelected: (_) => setState(() {
                    _motivo = sugestao;
                    _outro.clear();
                  }),
                ),
            ]),
            const SizedBox(height: 10),
            TextField(
              controller: _outro,
              maxLength: 200,
              decoration: const InputDecoration(hintText: 'Outro motivo (opcional)', counterText: ''),
              onChanged: (_) => setState(() {}),
            ),
            if (_erro != null)
              Padding(padding: const EdgeInsets.only(top: 8), child: Text(_erro!, style: const TextStyle(color: Cores.vermelho))),
            const SizedBox(height: 14),
            FilledButton(
              onPressed: _salvando ? null : _salvar,
              style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                  backgroundColor: _situacao == 'presenca' ? Cores.verde : Cores.vermelho),
              child: Text(_situacao == 'presenca' ? 'Marcar presença' : 'Marcar falta'),
            ),
            if (widget.atual != null) ...[
              const SizedBox(height: 8),
              TextButton(
                onPressed: _salvando
                    ? null
                    : () => _executar(() => ApiService.removerAjuste(widget.sessaoId, widget.alunoId)),
                child: const Text('Desfazer ajuste (voltar ao cálculo automático)'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
