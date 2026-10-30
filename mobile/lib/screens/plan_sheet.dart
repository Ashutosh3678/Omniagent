import 'package:flutter/material.dart';

import '../models.dart';

/// Shows what the AI plans to do and asks for a go-ahead. Resolves to true if confirmed.
Future<bool?> showPlanSheet(BuildContext context, PlanPreview preview) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => PlanSheet(preview: preview),
  );
}

class PlanSheet extends StatelessWidget {
  const PlanSheet({super.key, required this.preview});

  final PlanPreview preview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(preview.runnable ? 'Here is the plan' : 'Nothing to run', style: theme.textTheme.titleMedium),
            const SizedBox(height: 12),
            if (!preview.runnable)
              Text(
                preview.note.isNotEmpty
                    ? preview.note
                    : (preview.heldBack.isNotEmpty ? preview.heldBack.first.detail : 'That is not something this PC can do.'),
              ),
            for (var i = 0; i < preview.steps.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 12,
                      backgroundColor: scheme.primaryContainer,
                      child: Text('${i + 1}', style: theme.textTheme.labelSmall),
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: Text(preview.steps[i].description)),
                  ],
                ),
              ),
            if (preview.heldBack.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Will not run', style: theme.textTheme.labelLarge?.copyWith(color: scheme.tertiary)),
              for (final held in preview.heldBack)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(held.detail.isEmpty ? held.reason : held.detail, style: theme.textTheme.bodySmall),
                ),
            ],
            if (preview.lowConfidence) ...[
              const SizedBox(height: 12),
              Text(
                'The AI is not very sure about this plan. Check it before you run it.',
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
              ),
            ],
            const SizedBox(height: 20),
            if (preview.runnable)
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text(preview.heldBack.isEmpty ? 'Run' : 'Run what can run'),
              ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text(preview.runnable ? 'Cancel' : 'Close'),
            ),
          ],
        ),
      ),
    );
  }
}
