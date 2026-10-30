import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../models.dart';
import '../theme.dart';
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
  final List<StreamSubscription<dynamic>> _live = [];

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) => _tick());
    _live.addAll([
      events.agents.listen((_) => _load(quiet: true)),
      events.resyncs.listen((_) => _load(quiet: true)),
    ]);
  }

  @override
  void dispose() {
    _timer?.cancel();
    for (final subscription in _live) {
      subscription.cancel();
    }
    super.dispose();
  }

  void _tick() {
    final pairing = _pairing;
    if (pairing != null && !pairing.expiresAt.isAfter(DateTime.now())) {
      setState(() => _pairing = null);
    }
    // The live stream refreshes this; polling only covers a dropped connection.
    if (!events.connected.value) _load(quiet: true);
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

  /// Runs a server call and shows its failure inline, so every action reports errors the same way.
  Future<void> _guard(Future<void> Function() action) async {
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server.');
    }
  }

  Future<void> _generateCode() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    await _guard(() async {
      final code = await omniApi.createPairingCode();
      if (mounted) setState(() => _pairing = code);
    });
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _setApp(PcDevice device, String appId, bool allowed) async {
    if (device.id == null) return;
    final apps = {...device.permittedApps}
      ..remove(appId)
      ..addAll(allowed ? [appId] : const <String>[]);
    await _guard(() async {
      await omniApi.setPermittedApps(device.id!, apps.toList()..sort());
      await _load();
    });
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
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger,
              foregroundColor: AppColors.background,
              minimumSize: const Size(0, 44),
            ),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || device.id == null) return;
    await _guard(() async {
      await omniApi.revokeAgent(device.id!);
      await _load();
    });
  }

  ({String label, Color color}) _status(PcDevice device) {
    if (device.revoked) return (label: 'Removed', color: AppColors.textMuted);
    if (device.expired) return (label: 'Access expired', color: AppColors.warning);
    return device.online
        ? (label: 'Online', color: AppColors.success)
        : (label: 'Offline', color: AppColors.textMuted);
  }

  int _minutesLeft(PairingCode code) {
    final left = code.expiresAt.difference(DateTime.now()).inSeconds;
    return left <= 0 ? 0 : (left / 60).ceil();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Devices'), automaticallyImplyLeading: false),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, 24),
          children: [
            if (_error != null) ...[
              ErrorBanner(_error!),
              const SizedBox(height: 12),
            ],
            if (!_loaded && _error == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(child: CircularProgressIndicator()),
              ),
            for (final device in _devices) ...[
              _DeviceCard(
                device: device,
                status: _status(device),
                onAppChanged: (appId, value) => _setApp(device, appId, value),
                onRemove: () => _remove(device),
              ),
              const SizedBox(height: 14),
            ],
            _PairCard(
              pairing: _pairing,
              busy: _busy,
              hasDevices: _devices.isNotEmpty,
              minutesLeft: _pairing == null ? 0 : _minutesLeft(_pairing!),
              onGenerate: _generateCode,
            ),
          ],
        ),
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({
    required this.device,
    required this.status,
    required this.onAppChanged,
    required this.onRemove,
  });

  final PcDevice device;
  final ({String label, Color color}) status;
  final void Function(String appId, bool allowed) onAppChanged;
  final VoidCallback onRemove;

  String _appHint(AppInfo app) {
    if (app.id == 'browser' && !device.canBrowse) return 'Install Playwright on this PC to use this';
    if (app.needsWorkspace) {
      return device.workspaces.isEmpty
          ? 'Add a folder in the OmniAgent program on the PC first'
          : 'Works in: ${device.workspaces.join(', ')}';
    }
    return 'Lets tasks open and control ${app.label}';
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Panel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: status.color.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(Icons.desktop_windows_rounded, color: status.color),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      device.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      device.hostName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Pill(label: status.label, color: status.color),
            ],
          ),
          if (!device.revoked) ...[
            const SizedBox(height: 12),
            const Divider(),
            if (device.apps.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  'Open the OmniAgent program on this PC to choose which apps tasks may open.',
                  style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                ),
              )
            else ...[
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Apps tasks may open', style: textTheme.labelLarge),
              ),
              for (final app in device.apps)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(app.label),
                  subtitle: Text(_appHint(app)),
                  value: device.permittedApps.contains(app.id),
                  onChanged: (value) => onAppChanged(app.id, value),
                ),
            ],
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: onRemove,
                style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                icon: const Icon(Icons.delete_outline_rounded, size: 20),
                label: const Text('Remove PC'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PairCard extends StatelessWidget {
  const _PairCard({
    required this.pairing,
    required this.busy,
    required this.hasDevices,
    required this.minutesLeft,
    required this.onGenerate,
  });

  final PairingCode? pairing;
  final bool busy;
  final bool hasDevices;
  final int minutesLeft;
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final code = pairing;
    return Panel(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(hasDevices ? 'Add another PC' : 'Add your first PC', style: textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            'Get a one-time code, then enter it in the OmniAgent program on your PC.',
            style: textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: 16),
          if (code == null)
            FilledButton.icon(
              onPressed: busy ? null : onGenerate,
              icon: const Icon(Icons.add_link_rounded),
              label: Text(busy ? 'Creating' : 'Get pairing code'),
            )
          else ...[
            Container(
              padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
              decoration: BoxDecoration(
                color: AppColors.surfaceHigh,
                borderRadius: BorderRadius.circular(14),
              ),
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: SelectableText(
                  code.code,
                  style: textTheme.headlineMedium?.copyWith(
                    letterSpacing: 6,
                    fontWeight: FontWeight.w800,
                    color: AppColors.secondary,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Run: python connect.py --code ${code.code}\n'
              'Valid for $minutesLeft min. Works once.',
              style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted, height: 1.4),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: code.code));
                      ScaffoldMessenger.of(context)
                          .showSnackBar(const SnackBar(content: Text('Code copied')));
                    },
                    icon: const Icon(Icons.copy_rounded, size: 18),
                    label: const Text('Copy'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: busy ? null : onGenerate,
                    icon: const Icon(Icons.refresh_rounded, size: 18),
                    label: const Text('New code'),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
