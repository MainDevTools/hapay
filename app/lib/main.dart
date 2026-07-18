import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'theme.dart';

void main() => runApp(const HapayApp());

class HapayApp extends StatelessWidget {
  const HapayApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Хапай',
      debugShowCheckedModeBanner: false,
      theme: hapayTheme(Brightness.light),
      darkTheme: hapayTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      home: const HomeScreen(),
    );
  }
}
