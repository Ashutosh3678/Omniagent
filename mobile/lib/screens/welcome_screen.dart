import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _slow = false;
  Timer? _slowTimer;
  String? _error;

  static final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  @override
  void dispose() {
    _slowTimer?.cancel();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit({required bool signUp}) async {
    final email = _email.text.trim();
    final password = _password.text;
    if (!_emailPattern.hasMatch(email)) {
      setState(() => _error = 'Enter a valid email address.');
      return;
    }
    if (password.isEmpty || (signUp && password.length < 8)) {
      setState(() => _error = signUp
          ? 'Choose a password with at least 8 characters.'
          : 'Enter your password.');
      return;
    }
    setState(() {
      _busy = true;
      _slow = false;
      _error = null;
    });
    // The free server sleeps when idle; tell the user why the first login is slow.
    _slowTimer = Timer(const Duration(seconds: 6), () {
      if (mounted && _busy) setState(() => _slow = true);
    });
    try {
      if (signUp) {
        await omniApi.register(email, password);
      } else {
        await omniApi.login(email, password);
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/app');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not reach the server. Check your connection.');
      }
    } finally {
      _slowTimer?.cancel();
      if (mounted) {
        setState(() {
          _busy = false;
          _slow = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 56, 24, 24),
          child: Column(
            children: [
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: scheme.primary,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Icon(Icons.desktop_windows_outlined, color: scheme.onPrimary, size: 32),
              ),
              const SizedBox(height: 16),
              Text('OmniAgent', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 40),
              TextField(
                controller: _email,
                enabled: !_busy,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(labelText: 'Email'),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _password,
                enabled: !_busy,
                obscureText: true,
                autofillHints: const [AutofillHints.password],
                decoration: const InputDecoration(labelText: 'Password'),
                onSubmitted: (_) => _submit(signUp: false),
              ),
              if (_slow) ...[
                const SizedBox(height: 16),
                Text(
                  'Waking up the server. The first time can take up to a minute.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!, style: TextStyle(color: scheme.error)),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy ? null : () => _submit(signUp: false),
                child: _busy
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Log in'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _busy ? null : () => _submit(signUp: true),
                child: const Text('Sign up'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
