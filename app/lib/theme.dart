import 'package:flutter/material.dart';

/// Тема «Хапай». Material 3, світла/темна за системою. Червоний акцент — знижка.
const _seed = Color(0xFFE23B3B); // «сейл»-червоний, як у вебі

ThemeData hapayTheme(Brightness b) {
  final scheme = ColorScheme.fromSeed(seedColor: _seed, brightness: b);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: b == Brightness.dark ? const Color(0xFF101114) : const Color(0xFFF4F5F7),
    cardTheme: CardThemeData(   // Flutter 3.27+ очікує ...ThemeData тут; CardTheme = компіл-помилка
      elevation: 0,
      color: b == Brightness.dark ? const Color(0xFF191B1F) : Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
      clipBehavior: Clip.antiAlias,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      isDense: true,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
    ),
  );
}

/// Червоний тег «−X%». За T14 (агрегатор) знижка — головне на картці.
class DiscountTag extends StatelessWidget {
  final int pct;
  const DiscountTag(this.pct, {super.key});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(color: _seed, borderRadius: BorderRadius.circular(7)),
        child: Text('−$pct%',
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 12)),
      );
}
