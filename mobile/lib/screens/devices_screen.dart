import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../models.dart';
import '../widgets.dart';

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key});

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  List<PcDevice> _devices = const [];
  PairingCode? _pairing;
  bool _loaded = false;
  bool _busy = false;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) => _tick());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _tick() {
    final pairing = _pairing;
    if (pairing != null && !pairing.expiresAt.isAfter(DateTime.now())) {
      setState(() => _pairing = null);
    }
    _load(quiet: true);
  }

  Future<void> _load({bool quiet = false}) async {
    try {
      final devices = await omniApi.listAgents();
      if (!mounted) return;
      final hadNew = _pairing != null && devices.length > _devices.length;
      setState(() {
        _devices = devices;
        _loaded = true;
        if (!quiet) _error = null;
        // The PC used the code, so it is no longer needed.
        if (hadNew) _pairing = null;
      });
    } on ApiException catch (e) {
      if (mounted && !quiet) setState(() => _error = e.message);
    } catch (_) {
      if (mounted && !quiet) setState(() => _error = 'Could not reach the server.');
    }
  }

  Future<void> _generateCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final code = await omniApi.createPairingCode();
      if (mounted) setState(() => _pairing = code);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove(PcDevice device) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove ${device.name}?'),
        content: const Text(
          'It will be disconnected and can no longer receive tasks. '
          'To use it again, pair it with a new code.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true || device.id == null) return;
    try {
      await omniApi.revokeAgent(device.id!);
      await _load();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server.');
    }
  }

  String _statusLabel(PcDevice device) {
    if (device.revoked) return 'Removed';
    if (device.expired) return 'Access expired';
    return device.online ? 'Online' : 'Offline';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Devices'), automaticallyImplyLeading: false),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          children: [
            if (_error != null) ...[
              Text(_error!, style: TextStyle(color: scheme.error)),
              const SizedBox(height: 12),
            ],
            if (_loaded && _devices.isEmpty)
              const Padding(
                padding: EdgeInsets.only(bottom: 16),
                child: Text('No PCs yet. Add one below to start sending tasks.'),
              ),
            for (final device in _devices) ...[
              _Card(
                children: [
                  Text(device.name, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(device.hostName, style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      StatusChip(label: _statusLabel(device), selected: device.usable),
                      for (final app in device.permittedApps)
                        StatusChip(label: app[0].toUpperCase() + app.substring(1), selected: false),
                    ],
                  ),
                  if (!device.revoked) ...[
                    const SizedBox(height: 12),
                    OutlinedButton(
                      onPressed: () => _remove(device),
                      style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(44)),
                      child: const Text('Remove'),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 16),
            ],
            _Card(
              children: [
                Text('Add PC', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                if (_pairing == null) ...[
                  const Text('Get a one-time code, then enter it in the OmniAgent program on your PC.'),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _busy ? null : _generateCode,
                    child: Text(_busy ? 'Creating' : 'Get pairing code'),
                  ),
                ] else ...[
                  SelectableText(
                    _pairing!.code,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(letterSpacing: 4),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Run: python connect.py --code ${_pairing!.code}\n'
                    'Valid for ${_minutesLeft(_pairing!)} min. Works once.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      OutlinedButton(
                        onPressed: () => Clipboard.setData(ClipboardData(text: _pairing!.code)),
                        child: const Text('Copy'),
                      ),
                      const SizedBox(width: 8),
                      TextButton(onPressed: _busy ? null : _generateCode, child: const Text('New code')),
                    ],
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  int _minutesLeft(PairingCode code) {
    final left = code.expiresAt.difference(DateTime.now()).inSeconds;
    return left <= 0 ? 0 : (left / 60).ceil();
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
