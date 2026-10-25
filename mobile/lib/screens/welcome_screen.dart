import 'package:flutter/material.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: SafeArea(
        child: Padding(
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
              const TextField(
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(labelText: 'Email'),
              ),
              const SizedBox(height: 16),
              const TextField(
                obscureText: true,
                decoration: InputDecoration(labelText: 'Password'),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => Navigator.of(context).pushReplacementNamed('/app'),
                child: const Text('Log in'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => Navigator.of(context).pushReplacementNamed('/app'),
                child: const Text('Sign up'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
