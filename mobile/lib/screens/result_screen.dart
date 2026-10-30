import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key});

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  Uint8List? _bytes;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final task = ModalRoute.of(context)?.settings.arguments;
    if (task is TaskItem && task.id != null) {
      omniApi.getScreenshot(task.id!).then((bytes) {
        if (mounted) setState(() => _bytes = bytes);
      }).catchError((_) {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final task = ModalRoute.of(context)?.settings.arguments as TaskItem? ?? kHistory.first;
    final ok = task.status == TaskStatus.completed;

    return Scaffold(
      appBar: AppBar(title: const Text('Result'), leading: const BackButton()),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SuccessBadge(label: task.statusLabel),
            const SizedBox(height: 16),
            Text(
              ok
                  ? (task.summary.isEmpty ? 'Task complete' : task.summary)
                  : (task.error.isEmpty ? (task.status == TaskStatus.partial ? 'Task partly done' : 'Task failed') : task.error),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            for (final step in task.steps.where((s) => s.hasProblem))
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  '${step.name}: ${step.detail.isEmpty ? step.status.replaceAll('_', ' ') : step.detail}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: 16),
            ScreenPreview(height: 160, bytes: _bytes),
            if (task.fileName != null)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(task.fileName!),
                subtitle: const Text('PNG'),
              ),
            const Spacer(),
            FilledButton(
              onPressed: () => Navigator.of(context).popUntil((route) => route.settings.name == '/app' || route.isFirst),
              child: const Text('Done'),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () async {
                try {
                  final created = await omniApi.createTask(task.title);
                  if (!context.mounted) return;
                  Navigator.of(context).pushNamedAndRemoveUntil(
                    '/execution',
                    (route) => route.settings.name == '/app' || route.isFirst,
                    arguments: created,
                  );
                } on ApiException catch (error) {
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
                }
              },
              child: const Text('Run again'),
            ),
          ],
        ),
      ),
    );
  }
}
