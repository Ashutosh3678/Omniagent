import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../mock_data.dart';
import '../models.dart';
import '../theme.dart';

class ExecutionScreen extends StatefulWidget {
  const ExecutionScreen({super.key});

  @override
  State<ExecutionScreen> createState() => _ExecutionScreenState();
}

class _ExecutionScreenState extends State<ExecutionScreen> {
  TaskItem? _task;
  Timer? _poll;
  bool _openedResult = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)?.settings.arguments;
    if (_task == null) {
      if (args is TaskItem) {
        _task = args;
        if (args.id != null) {
          _poll = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
          _refresh();
        }
      } else if (args is String) {
        _task = TaskItem(title: args, when: 'Now', status: TaskStatus.running);
      } else {
        _task = const TaskItem(title: kDefaultTask, when: 'Now', status: TaskStatus.running);
      }
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    final id = _task?.id;
    if (id == null) return;
    try {
      final latest = await omniApi.getTask(id);
      if (!mounted) return;
      setState(() => _task = latest);
      if (!_openedResult && (latest.status == TaskStatus.completed || latest.status == TaskStatus.failed)) {
        _openedResult = true;
        _poll?.cancel();
        Navigator.of(context).pushReplacementNamed('/result', arguments: latest);
      }
    } catch (_) {}
  }

  Future<void> _cancel() async {
    final id = _task?.id;
    if (id != null) {
      try {
        await omniApi.cancelTask(id);
      } catch (_) {}
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final task = _task;
    final steps = task?.steps.isNotEmpty == true
        ? task!.steps
        : [for (final name in kExecutionSteps) TaskStep(name: name, status: 'pending')];
    final done = steps.where((step) => step.status == 'success').length;
    final activeIndex = steps.indexWhere((step) => step.status == 'running');
    final progress = steps.isEmpty ? 0.0 : done / steps.length;

    return Scaffold(
      appBar: AppBar(
        title: Text(task?.statusLabel ?? 'Running'),
        leading: const BackButton(),
        actions: [
          IconButton(
            tooltip: 'Live',
            onPressed: () => Navigator.of(context).pushNamed('/live', arguments: task ?? kDefaultTask),
            icon: const Icon(Icons.videocam_outlined),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(task?.title ?? kDefaultTask, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 20),
            Text('${done.clamp(0, steps.length)} of ${steps.length}', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                value: progress == 0 && task?.status == TaskStatus.running ? null : progress,
                minHeight: 8,
                backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
              ),
            ),
            const SizedBox(height: 20),
            for (var i = 0; i < steps.length; i++)
              _StepRow(
                label: steps[i].name,
                state: steps[i].status == 'success'
                    ? _StepState.done
                    : steps[i].status == 'failed'
                        ? _StepState.failed
                        : (i == activeIndex || steps[i].status == 'running')
                            ? _StepState.active
                            : _StepState.todo,
              ),
            const Spacer(),
            OutlinedButton(
              onPressed: _cancel,
              child: const Text('Cancel'),
            ),
          ],
        ),
      ),
    );
  }
}

enum _StepState { done, active, todo, failed }

class _StepRow extends StatelessWidget {
  const _StepRow({required this.label, required this.state});

  final String label;
  final _StepState state;

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      _StepState.done => kSuccess,
      _StepState.active => Theme.of(context).colorScheme.primary,
      _StepState.failed => Theme.of(context).colorScheme.error,
      _StepState.todo => Theme.of(context).colorScheme.outlineVariant,
    };

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          CircleAvatar(radius: 6, backgroundColor: color),
          const SizedBox(width: 12),
          Text(
            label,
            style: state == _StepState.active
                ? Theme.of(context).textTheme.titleSmall
                : Theme.of(context).textTheme.bodyLarge,
          ),
        ],
      ),
    );
  }
}
