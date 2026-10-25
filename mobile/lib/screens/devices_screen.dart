import 'package:flutter/material.dart';

import '../api/client.dart';
import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key});

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  List<PcDevice> _agents = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final agents = await omniApi.listAgents();
      if (mounted) setState(() => _agents = agents);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final devices = _agents.isEmpty ? const [kOfficePc] : _agents;

    return Scaffold(
      appBar: AppBar(title: const Text('Devices'), automaticallyImplyLeading: false),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        children: [
          for (final device in devices) ...[
            _Card(
              children: [
                Text(device.name, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(device.hostName, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: StatusChip(label: device.online ? 'Online' : 'Offline', selected: device.online),
                ),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () {},
                  style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(44)),
                  child: const Text('Disconnect'),
                ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          _Card(
            children: [
              Text('Add PC', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(kPairingCode, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }
}
