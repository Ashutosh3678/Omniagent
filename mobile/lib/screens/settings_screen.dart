import 'package:flutter/material.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _faceId = true;
  bool _haptics = true;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings'), automaticallyImplyLeading: false),
      body: ListView(
        children: [
          const ListTile(
            leading: CircleAvatar(child: Icon(Icons.person)),
            title: Text('Alex Chen'),
            subtitle: Text('alex@omniagent.app'),
          ),
          SwitchListTile(
            title: const Text('Face ID'),
            value: _faceId,
            onChanged: (value) => setState(() => _faceId = value),
          ),
          SwitchListTile(
            title: const Text('Haptics'),
            value: _haptics,
            onChanged: (value) => setState(() => _haptics = value),
          ),
          const ListTile(
            title: Text('Screenshots'),
            subtitle: Text('Save locally'),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: TextButton(
              onPressed: () => Navigator.of(context).pushNamedAndRemoveUntil('/', (_) => false),
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
