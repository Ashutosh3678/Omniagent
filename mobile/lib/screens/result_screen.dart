import 'package:flutter/material.dart';

import '../api/client.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets.dart';

class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key});

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  bool _rerunning = false;

  Future<void> _runAgain(TaskItem task) async {
    setState(() => _rerunning = true);
    try {
      final created = await omniApi.createTask(task.title);
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil(
        '/execution',
        (route) => route.settings.name == '/app' || route.isFirst,
        arguments: created,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Could not reach the server.')));
    } finally {
      if (mounted) setState(() => _rerunning = false);
    }
  }

  String _headline(TaskItem task) {
    return switch (task.status) {
      TaskStatus.completed => task.summary.isEmpty ? 'Task complete' : task.summary,
      TaskStatus.partial => task.error.isEmpty ? 'Task partly done' : task.error,
      TaskStatus.failed => task.error.isEmpty ? 'Task failed' : task.error,
      _ => task.summary.isEmpty ? 'Task in progress' : task.summary,
    };
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final task = args is TaskItem ? args : const TaskItem(title: 'Task', when: '', status: TaskStatus.pending);
    final style = statusStyle(task.status);
    final textTheme = Theme.of(context).textTheme;
    final problems = task.steps.where((s) => s.hasProblem).toList();

    return Scaffold(
      appBar: AppBar(title: const Text('Result')),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(Gap.page, 8, Gap.page, 16),
                children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TaskStatusPill(status: task.status),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(style.icon, color: style.color, size: 28),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          _headline(task),
                          style: textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Padding(
                    padding: const EdgeInsets.only(left: 40),
                    child: Text(
                      task.title,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
                    ),
                  ),
                  if (problems.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Panel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          for (final step in problems)
                            Padding(
                              padding: EdgeInsets.only(top: step == problems.first ? 0 : 10),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Icon(
                                    step.status == 'failed'
                                        ? Icons.cancel_rounded
                                        : Icons.error_outline_rounded,
                                    size: 18,
                                    color: step.status == 'failed' ? AppColors.danger : AppColors.warning,
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      '${step.name}: ${step.detail.isEmpty ? step.status.replaceAll('_', ' ') : step.detail}',
                                      style: textTheme.bodySmall,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                  if (task.screenshotUrl != null) ...[
                    const SizedBox(height: 16),
                    ScreenPreview(
                      height: 220,
                      url: task.screenshotUrl,
                      headers: omniApi.imageHeaders(task.screenshotUrl),
                    ),
                    if (task.fileName != null) ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          const Icon(Icons.image_outlined, size: 16, color: AppColors.textMuted),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              task.fileName!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Gap.page, 0, Gap.page, Gap.page),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FilledButton(
                    onPressed: () => Navigator.of(context)
                        .popUntil((route) => route.settings.name == '/app' || route.isFirst),
                    child: const Text('Done'),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: _rerunning ? null : () => _runAgain(task),
                    icon: const Icon(Icons.replay_rounded),
                    label: Text(_rerunning ? 'Starting' : 'Run again'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
