import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'api/session.dart';
import 'app_shell.dart';
import 'screens/execution_screen.dart';
import 'screens/live_screen.dart';
import 'screens/result_screen.dart';
import 'screens/welcome_screen.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SemanticsBinding.instance.ensureSemantics();
  await appSession.load();
  runApp(const OmniAgentApp());
}

class OmniAgentApp extends StatefulWidget {
  const OmniAgentApp({super.key});

  @override
  State<OmniAgentApp> createState() => _OmniAgentAppState();
}

class _OmniAgentAppState extends State<OmniAgentApp> {
  final _navigator = GlobalKey<NavigatorState>();
  late bool _wasSignedIn = appSession.isSignedIn;

  @override
  void initState() {
    super.initState();
    appSession.addListener(_onSessionChanged);
  }

  @override
  void dispose() {
    appSession.removeListener(_onSessionChanged);
    super.dispose();
  }

  // Signing out (or an expired token) always lands on the login screen.
  void _onSessionChanged() {
    final signedIn = appSession.isSignedIn;
    if (_wasSignedIn && !signedIn) {
      _navigator.currentState?.pushNamedAndRemoveUntil('/', (_) => false);
    }
    _wasSignedIn = signedIn;
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigator,
      title: 'OmniAgent',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      initialRoute: appSession.isSignedIn ? '/app' : '/',
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
