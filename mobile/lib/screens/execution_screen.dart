import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/events.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets.dart';

class ExecutionScreen extends StatefulWidget {
  const ExecutionScreen({super.key});

  @override
  State<ExecutionScreen> createState() => _ExecutionScreenState();
}

class _ExecutionScreenState extends State<ExecutionScreen> {
  TaskItem? _task;
  Timer? _poll;
  StreamSubscription<TaskItem>? _live;
  StreamSubscription<void>? _resync;
  bool _openedResult = false;
  bool _cancelling = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_task != null) return;
    final args = ModalRoute.of(context)?.settings.arguments;
    final task = args is TaskItem
        ? args
        : TaskItem(title: args is String ? args : 'Task', when: '', status: TaskStatus.running);
    _task = task;
    final id = task.id;
    if (id == null) return;
    _live = events.tasks.where((item) => item.id == id).listen(_apply);
    _resync = events.resyncs.listen((_) => _refresh());
    // The live stream does the work; this slow check only covers a dropped connection.
    _poll = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!events.connected.value) _refresh();
    });
    _refresh();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _live?.cancel();
    _resync?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    final id = _task?.id;
    if (id == null) return;
    try {
      _apply(await omniApi.getTask(id));
    } catch (_) {}
  }

  void _apply(TaskItem latest) {
    if (!mounted) return;
    setState(() => _task = latest);
    final finished = latest.status == TaskStatus.completed ||
        latest.status == TaskStatus.partial ||
        latest.status == TaskStatus.failed;
    if (!_openedResult && finished) {
      _openedResult = true;
      _poll?.cancel();
      _live?.cancel();
      Navigator.of(context).pushReplacementNamed('/result', arguments: latest);
    }
  }

  Future<void> _cancel() async {
    if (_cancelling) return;
    setState(() => _cancelling = true);
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
    final steps = task?.steps ?? const <TaskStep>[];
    final done = steps.where((step) => step.status == 'success').length;
    final activeIndex = steps.indexWhere((step) => step.status == 'running');
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(
        title: Text(task?.statusLabel ?? 'Running'),
        actions: [
          IconButton(
            tooltip: 'Watch live',
            onPressed: task == null ? null : () => Navigator.of(context).pushNamed('/live', arguments: task),
            icon: const Icon(Icons.videocam_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, Gap.page),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Panel(
                child: Text(
                  task?.title ?? '',
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                steps.isEmpty ? 'Planning…' : '$done of ${steps.length} steps',
                style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(
                  // An unknown amount of work shows a moving bar rather than an empty one.
                  value: steps.isEmpty ? null : done / steps.length,
                  minHeight: 8,
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView.builder(
                  itemCount: steps.length,
                  itemBuilder: (context, i) => _StepRow(
                    label: steps[i].name,
                    detail: steps[i].hasProblem ? steps[i].detail : '',
                    state: switch (steps[i].status) {
                      'success' => _StepState.done,
                      'failed' => _StepState.failed,
                      'held_back' => _StepState.held,
                      'unverified' => _StepState.unverified,
                      'skipped' => _StepState.skipped,
                      _ => (i == activeIndex || steps[i].status == 'running')
                          ? _StepState.active
                          : _StepState.todo,
                    },
                    isLast: i == steps.length - 1,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _cancelling ? null : _cancel,
                child: Text(_cancelling ? 'Cancelling' : 'Cancel task'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

enum _StepState { done, active, todo, failed, held, skipped, unverified }

class _StepRow extends StatelessWidget {
  const _StepRow({
    required this.label,
    required this.state,
    required this.isLast,
    this.detail = '',
  });

  final String label;
  final _StepState state;
  final bool isLast;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final (color, icon) = switch (state) {
      _StepState.done => (AppColors.success, Icons.check_circle_rounded),
      _StepState.active => (AppColors.primary, Icons.autorenew_rounded),
      _StepState.failed => (AppColors.danger, Icons.cancel_rounded),
      _StepState.held => (AppColors.warning, Icons.pause_circle_rounded),
      _StepState.unverified => (AppColors.warning, Icons.help_rounded),
      _StepState.skipped => (AppColors.textMuted, Icons.remove_circle_outline_rounded),
      _StepState.todo => (AppColors.textMuted, Icons.radio_button_unchecked_rounded),
    };

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 28,
            child: Column(
              children: [
                state == _StepState.active
                    ? Padding(
                        padding: const EdgeInsets.all(3),
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2.5, color: color),
                        ),
                      )
                    : Icon(icon, color: color, size: 24),
                if (!isLast)
                  Expanded(child: Container(width: 2, color: AppColors.outline)),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      label,
                      style: textTheme.bodyLarge?.copyWith(
                        fontWeight: state == _StepState.active ? FontWeight.w700 : FontWeight.w400,
                        color: state == _StepState.todo ? AppColors.textMuted : AppColors.text,
                      ),
                    ),
                  ),
                  if (detail.isNotEmpty)
                    Text(detail, style: textTheme.bodySmall?.copyWith(color: color)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
