import 'package:flutter/material.dart';

import '../mock_data.dart';
import '../models.dart';
import '../widgets.dart';

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final task = ModalRoute.of(context)?.settings.arguments as TaskItem? ?? kHistory.first;
    final ok = task.status != TaskStatus.failed;

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
              ok ? 'Task complete' : 'Task failed',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            const ScreenPreview(height: 160),
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
              onPressed: () {
                Navigator.of(context).pushNamedAndRemoveUntil(
                  '/execution',
                  (route) => route.settings.name == '/app' || route.isFirst,
                  arguments: task.title,
                );
              },
              child: const Text('Run again'),
            ),
          ],
        ),
      ),
    );
  }
}
