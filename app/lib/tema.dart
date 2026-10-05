// LivePresenceAI - Identidade visual e componentes compartilhados.
// Referência: apps da Meta (Facebook, Instagram, WhatsApp) — fundo cinza-claro com cartões brancos,
// azul de destaque, cantos arredondados, botões em pílula, avatares com anel de status.
// Parte da biblioteca de main.dart.

part of 'main.dart';

class Cores {
  static const azul = Color(0xFF0866FF);
  static const azulClaro = Color(0xFFEBF5FF);
  static const fundo = Color(0xFFF0F2F5);
  static const superficie = Colors.white;
  static const cinzaBotao = Color(0xFFE4E6EB);
  static const texto = Color(0xFF050505);
  static const textoSecundario = Color(0xFF65676B);
  static const divisor = Color(0xFFDADDE1);
  static const verde = Color(0xFF31A24C);
  static const verdeClaro = Color(0xFFE6F4EA);
  static const ambar = Color(0xFFE59400);
  static const ambarClaro = Color(0xFFFFF4E0);
  static const vermelho = Color(0xFFE41E3F);
  static const vermelhoClaro = Color(0xFFFDECEE);

  /// Tons de fundo dos avatares (escolhidos pelo nome, sempre o mesmo para a mesma pessoa).
  static const avatares = [
    Color(0xFF1877F2), Color(0xFF7B61FF), Color(0xFFE4405F), Color(0xFF00A884),
    Color(0xFFF7B928), Color(0xFF0097A7), Color(0xFFFF6F00), Color(0xFF8E24AA),
  ];
}

ThemeData temaLivePresence() {
  final esquema = ColorScheme.fromSeed(
    seedColor: Cores.azul,
    primary: Cores.azul,
    surface: Cores.superficie,
    error: Cores.vermelho,
  );
  final pilula = RoundedRectangleBorder(borderRadius: BorderRadius.circular(24));
  return ThemeData(
    useMaterial3: true,
    colorScheme: esquema,
    scaffoldBackgroundColor: Cores.fundo,
    fontFamily: 'Roboto',
    appBarTheme: const AppBarTheme(
      backgroundColor: Cores.superficie,
      foregroundColor: Cores.texto,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleTextStyle: TextStyle(color: Cores.texto, fontSize: 22, fontWeight: FontWeight.w800),
    ),
    cardTheme: CardThemeData(
      color: Cores.superficie,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Cores.azul,
        foregroundColor: Colors.white,
        minimumSize: const Size(0, 44),
        padding: const EdgeInsets.symmetric(horizontal: 18),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        shape: pilula,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Cores.texto,
        backgroundColor: Cores.cinzaBotao,
        side: BorderSide.none,
        minimumSize: const Size(0, 44),
        padding: const EdgeInsets.symmetric(horizontal: 16),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        shape: pilula,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: Cores.azul,
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        shape: pilula,
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: Cores.azul,
      foregroundColor: Colors.white,
      elevation: 2,
      shape: StadiumBorder(),
      extendedTextStyle: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Cores.fundo,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Cores.azul, width: 1.5)),
      errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Cores.vermelho)),
      hintStyle: const TextStyle(color: Cores.textoSecundario),
      labelStyle: const TextStyle(color: Cores.textoSecundario),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Cores.superficie,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      titleTextStyle: const TextStyle(color: Cores.texto, fontSize: 20, fontWeight: FontWeight.w800),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Cores.superficie,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      showDragHandle: true,
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: Cores.superficie,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      textStyle: const TextStyle(color: Cores.texto, fontSize: 15),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: const Color(0xFF242526),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    switchTheme: SwitchThemeData(
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Cores.azul : null),
    ),
    listTileTheme: const ListTileThemeData(
      titleTextStyle: TextStyle(color: Cores.texto, fontSize: 16, fontWeight: FontWeight.w600),
      subtitleTextStyle: TextStyle(color: Cores.textoSecundario, fontSize: 13.5),
    ),
    dividerTheme: const DividerThemeData(color: Cores.divisor, thickness: 0.6, space: 1),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: Cores.azul),
  );
}

// ---------------------- COMPONENTES ----------------------

/// Nome da marca no estilo das logos de texto da Meta (minúsculas, negrito, azul).
class Marca extends StatelessWidget {
  final double tamanho;
  const Marca({super.key, this.tamanho = 26});
  @override
  Widget build(BuildContext context) => Text.rich(
        TextSpan(children: [
          const TextSpan(text: 'livepresence', style: TextStyle(color: Cores.azul)),
          // "AI" com o gradiente do ícone do app (azul -> roxo)
          WidgetSpan(
            alignment: PlaceholderAlignment.baseline,
            baseline: TextBaseline.alphabetic,
            child: ShaderMask(
              shaderCallback: (r) =>
                  const LinearGradient(colors: [Color(0xFF0866FF), Color(0xFF7B61FF)]).createShader(r),
              child: Text('AI',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: tamanho,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -tamanho * 0.02)),
            ),
          ),
        ]),
        semanticsLabel: 'LivePresenceAI',
        style: TextStyle(fontSize: tamanho, fontWeight: FontWeight.w900, letterSpacing: -tamanho * 0.04),
      );
}

/// Botão redondo cinza do cabeçalho (como os ícones do topo do Facebook).
class BotaoCirculo extends StatelessWidget {
  final IconData icone;
  final String dica;
  final VoidCallback? onPressed;
  const BotaoCirculo({super.key, required this.icone, required this.dica, this.onPressed});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: Tooltip(
          message: dica,
          child: Material(
            color: Cores.cinzaBotao,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: onPressed,
              child: SizedBox(width: 40, height: 40, child: Icon(icone, size: 22, color: Cores.texto)),
            ),
          ),
        ),
      );
}

String iniciais(String nome) {
  // So letras e numeros: "Ajuste (teste)" vira "AT", e nao "A("
  final partes = nome
      .split(' ')
      .map((p) => p.replaceAll(RegExp(r'[^0-9A-Za-zÀ-ÿ]'), ''))
      .where((p) => p.isNotEmpty)
      .toList();
  if (partes.isEmpty) return '?';
  final primeira = partes.first[0];
  final ultima = partes.length > 1 ? partes.last[0] : '';
  return (primeira + ultima).toUpperCase();
}

/// Avatar com iniciais; [anel] desenha o contorno de status (como o anel dos stories).
class Avatar extends StatelessWidget {
  final String nome;
  final double tamanho;
  final Color? anel;
  final bool anelTracejado;
  final Widget? selo;
  const Avatar({super.key, required this.nome, this.tamanho = 44, this.anel, this.anelTracejado = false, this.selo});

  @override
  Widget build(BuildContext context) {
    final cor = Cores.avatares[nome.codeUnits.fold<int>(0, (a, b) => a + b) % Cores.avatares.length];
    Widget circulo = Container(
      width: tamanho,
      height: tamanho,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: cor, shape: BoxShape.circle),
      child: Text(iniciais(nome),
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: tamanho * 0.36)),
    );
    if (anel != null) {
      circulo = Container(
        padding: const EdgeInsets.all(2.5),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: anel!, width: anelTracejado ? 1.5 : 2.5),
        ),
        child: Container(
          padding: const EdgeInsets.all(1.5),
          decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
          child: circulo,
        ),
      );
    }
    if (selo == null) return circulo;
    return Stack(clipBehavior: Clip.none, children: [
      circulo,
      Positioned(right: -2, bottom: -2, child: selo!),
    ]);
  }
}

/// Selo redondo pequeno sobre o avatar (como o ponto verde de "online").
class Selo extends StatelessWidget {
  final IconData icone;
  final Color cor;
  const Selo({super.key, required this.icone, required this.cor});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(2),
        decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
        child: CircleAvatar(radius: 8, backgroundColor: cor, child: Icon(icone, size: 11, color: Colors.white)),
      );
}

/// Etiqueta em pílula (status, contadores).
class Etiqueta extends StatelessWidget {
  final String texto;
  final Color cor;
  final Color fundo;
  final IconData? icone;
  const Etiqueta({super.key, required this.texto, required this.cor, required this.fundo, this.icone});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(color: fundo, borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icone != null) ...[Icon(icone, size: 14, color: cor), const SizedBox(width: 4)],
          Text(texto, style: TextStyle(color: cor, fontSize: 12.5, fontWeight: FontWeight.w700)),
        ]),
      );
}

/// Pílula vermelha "AO VIVO" (como as transmissões ao vivo do Facebook).
class AoVivo extends StatelessWidget {
  final String? texto;
  const AoVivo({super.key, this.texto});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: Cores.vermelho, borderRadius: BorderRadius.circular(6)),
        child: Text(texto == null ? 'AO VIVO' : 'AO VIVO · $texto',
            style: const TextStyle(color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w800, letterSpacing: 0.3)),
      );
}

/// Cartão branco com cantos arredondados e margem padrão.
class Cartao extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final EdgeInsets margem;
  final VoidCallback? onTap;
  const Cartao({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margem = const EdgeInsets.fromLTRB(12, 6, 12, 6),
    this.onTap,
  });
  @override
  Widget build(BuildContext context) => Padding(
        padding: margem,
        child: Material(
          color: Cores.superficie,
          borderRadius: BorderRadius.circular(12),
          clipBehavior: Clip.antiAlias,
          child: InkWell(onTap: onTap, child: Padding(padding: padding, child: child)),
        ),
      );
}

/// Número em destaque com legenda (painéis de resumo).
class Indicador extends StatelessWidget {
  final String valor;
  final String legenda;
  final Color cor;
  const Indicador({super.key, required this.valor, required this.legenda, this.cor = Cores.texto});
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(valor, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: cor)),
          Text(legenda, style: const TextStyle(fontSize: 12.5, color: Cores.textoSecundario)),
        ],
      );
}

/// Estado vazio amigável, com ícone, título, texto e ação opcional.
class EstadoVazio extends StatelessWidget {
  final IconData icone;
  final String titulo;
  final String texto;
  final Widget? acao;
  const EstadoVazio({super.key, required this.icone, required this.titulo, required this.texto, this.acao});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: const BoxDecoration(color: Cores.azulClaro, shape: BoxShape.circle),
              child: Icon(icone, size: 40, color: Cores.azul),
            ),
            const SizedBox(height: 16),
            Text(titulo, textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Cores.texto)),
            const SizedBox(height: 6),
            Text(texto, textAlign: TextAlign.center, style: const TextStyle(color: Cores.textoSecundario)),
            if (acao != null) ...[const SizedBox(height: 18), acao!],
          ]),
        ),
      );
}

/// Título com subtítulo para a AppBar das telas internas.
class TituloTela extends StatelessWidget {
  final String titulo;
  final String? subtitulo;
  const TituloTela(this.titulo, {super.key, this.subtitulo});
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: Cores.texto)),
          if (subtitulo != null)
            Text(subtitulo!,
                style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500, color: Cores.textoSecundario)),
        ],
      );
}
