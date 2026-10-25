import 'package:flutter/material.dart';

import '../mock_data.dart';
import '../theme.dart';

class ExecutionScreen extends StatelessWidget {
  const ExecutionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final task = ModalRoute.of(context)?.settings.arguments as String? ?? kDefaultTask;
    const activeIndex = 1;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Running'),
        leading: const BackButton(),
        actions: [
          IconButton(
            tooltip: 'Live',
            onPressed: () => Navigator.of(context).pushNamed('/live', arguments: task),
            icon: const Icon(Icons.videocam_outlined),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(task, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 20),
            Text('2 of 4', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                value: 0.5,
                minHeight: 8,
                backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
              ),
            ),
            const SizedBox(height: 20),
            for (var i = 0; i < kExecutionSteps.length; i++)
              _StepRow(
                label: kExecutionSteps[i],
                state: i < activeIndex ? _StepState.done : i == activeIndex ? _StepState.active : _StepState.todo,
              ),
            const Spacer(),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
          ],
        ),
      ),
    );
  }
}

enum _StepState { done, active, todo }

class _StepRow extends StatelessWidget {
  const _StepRow({required this.label, required this.state});

  final String label;
  final _StepState state;

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      _StepState.done => kSuccess,
      _StepState.active => Theme.of(context).colorScheme.primary,
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
