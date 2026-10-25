import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'app_shell.dart';
import 'screens/execution_screen.dart';
import 'screens/live_screen.dart';
import 'screens/result_screen.dart';
import 'screens/welcome_screen.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SemanticsBinding.instance.ensureSemantics();
  runApp(const OmniAgentApp());
}

class OmniAgentApp extends StatelessWidget {
  const OmniAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OmniAgent',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      initialRoute: '/',
      routes: {
        '/': (_) => const WelcomeScreen(),
        '/app': (_) => const AppShell(),
        '/execution': (_) => const ExecutionScreen(),
        '/live': (_) => const LiveScreen(),
        '/result': (_) => const ResultScreen(),
      },
    );
  }
}
