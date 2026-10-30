import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../api/session.dart';
import '../app_shell.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets.dart';
import 'plan_sheet.dart';

const _examples = [
  'Open Notepad and type Hello from OmniAgent',
  'Take a screenshot of my desktop',
];

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.onNavigate});

  /// Lets the screen send the user to another tab (pairing a PC, seeing all history).
  final ValueChanged<AppTab>? onNavigate;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _task = TextEditingController();
  List<PcDevice> _agents = const [];
  List<TaskItem> _recent = const [];
  bool _loaded = false;
  bool _busy = false;
  final List<StreamSubscription<dynamic>> _live = [];
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _task.addListener(() => setState(() {}));
    _refresh();
    // Anything that changes on the server refreshes the device status and recent tasks.
    _live.addAll([
      events.tasks.listen((_) => _scheduleRefresh()),
      events.agents.listen((_) => _scheduleRefresh()),
      events.resyncs.listen((_) => _scheduleRefresh()),
    ]);
  }

  void _scheduleRefresh() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), _refresh);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    for (final subscription in _live) {
      subscription.cancel();
    }
    _task.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final agents = await omniApi.listAgents();
      final tasks = await omniApi.listTasks();
      if (!mounted) return;
      setState(() {
        _agents = agents;
        _recent = tasks.take(3).toList();
        _loaded = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _agents = const [];
        _recent = const [];
        _loaded = true;
      });
    }
  }

  PcDevice? get _device {
    for (final agent in _agents) {
      if (agent.usable) return agent;
    }
    for (final agent in _agents) {
      if (!agent.revoked) return agent;
    }
    return null;
  }

  Future<void> _runTask() async {
    final instruction = _task.text.trim();
    if (instruction.isEmpty || _busy) return;
    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      // Plans made by the AI are shown first; plain "open notepad..." phrases run straight away.
      final preview = await omniApi.previewPlan(instruction, agentId: _device?.id);
      if (!mounted) return;
      List<dynamic>? confirmed;
      if (preview.planner != 'rules') {
        final ok = await showPlanSheet(context, preview);
        if (ok != true || !mounted) return;
        confirmed = preview.plan;
      }
      final task = await omniApi.createTask(instruction, agentId: _device?.id, plan: confirmed);
      if (!mounted) return;
      _task.clear();
      await Navigator.of(context).pushNamed('/execution', arguments: task);
      await _refresh();
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      await _refresh();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Could not reach the server. Check your connection.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final device = _device;
    final online = device?.usable ?? false;
    final name = appSession.user?.displayName;

    return Scaffold(
      appBar: AppBar(
        title: const Text('OmniAgent'),
        automaticallyImplyLeading: false,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: Gap.page),
            child: Center(
              child: Pill(
                label: !_loaded ? 'Checking' : (online ? 'PC online' : 'PC offline'),
                color: !_loaded
                    ? AppColors.textMuted
                    : (online ? AppColors.success : AppColors.warning),
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, 24),
          children: [
            Text(
              name == null || name.isEmpty ? 'What should I do?' : 'Hi $name, what should I do?',
              style: textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              'Describe a task and your PC will carry it out.',
              style: textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
            ),
            const SizedBox(height: 20),
            if (_loaded && device == null) ...[
              _NoPcCard(onPair: () => widget.onNavigate?.call(AppTab.devices)),
              const SizedBox(height: 16),
            ] else if (_loaded && !online) ...[
              const ErrorBanner(
                'Your PC is offline. Start the OmniAgent program on it to run tasks.',
                color: AppColors.warning,
              ),
              const SizedBox(height: 16),
            ],
            TextField(
              controller: _task,
              minLines: 3,
              maxLines: 5,
              enabled: !_busy,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                hintText: 'e.g. Open Notepad and type Hello',
                alignLabelWithHint: true,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final example in _examples)
                  ActionChip(
                    label: Text(example, overflow: TextOverflow.ellipsis),
                    onPressed: _busy ? null : () => _task.text = example,
                  ),
              ],
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _busy || _task.text.trim().isEmpty ? null : _runTask,
              icon: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.play_arrow_rounded),
              label: Text(_busy ? 'Starting' : 'Run task'),
            ),
            const SizedBox(height: 28),
            Row(
              children: [
                Expanded(child: Text('Recent', style: textTheme.titleMedium)),
                if (_recent.isNotEmpty)
                  TextButton(
                    onPressed: () => widget.onNavigate?.call(AppTab.history),
                    child: const Text('See all'),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            if (_recent.isEmpty)
              const Panel(
                child: EmptyState(
                  icon: Icons.history_rounded,
                  title: 'No tasks yet',
                  message: 'Tasks you run will show up here.',
                ),
              )
            else
              for (final task in _recent) ...[
                TaskTile(
                  task: task,
                  onTap: () => Navigator.of(context).pushNamed('/result', arguments: task),
                ),
                const SizedBox(height: 10),
              ],
          ],
        ),
      ),
    );
  }
}

class _NoPcCard extends StatelessWidget {
  const _NoPcCard({required this.onPair});

  final VoidCallback onPair;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Panel(
      child: Row(
        children: [
          const Icon(Icons.desktop_access_disabled_outlined, color: AppColors.warning),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('No PC connected', style: textTheme.titleSmall),
                const SizedBox(height: 2),
                Text(
                  'Pair a PC to start sending tasks.',
                  style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          TextButton(onPressed: onPair, child: const Text('Pair')),
        ],
      ),
    );
  }
}
