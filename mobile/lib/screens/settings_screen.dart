import 'package:flutter/material.dart';

import '../api/session.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = appSession.user;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings'), automaticallyImplyLeading: false),
      body: ListView(
        children: [
          ListTile(
            leading: const CircleAvatar(child: Icon(Icons.person)),
            title: Text(user?.displayName ?? 'Not signed in'),
            subtitle: Text(user?.email ?? ''),
          ),
          const ListTile(
            title: Text('Screenshots'),
            subtitle: Text('Save locally'),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: TextButton(
              onPressed: appSession.signOut,
              style: TextButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
              child: const Text('Sign out'),
            ),
          ),
        ],
      ),
    );
  }
}
