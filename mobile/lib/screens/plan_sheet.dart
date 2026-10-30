import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';
import '../widgets.dart';

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
    final textTheme = theme.textTheme;

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Long plans scroll; the buttons below stay in view.
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(Gap.page, 0, Gap.page, 8),
                children: [
                  Text(
                    preview.runnable ? 'Here is the plan' : 'Nothing to run',
                    style: textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 14),
                  if (!preview.runnable)
                    Text(
                      preview.note.isNotEmpty
                          ? preview.note
                          : (preview.heldBack.isNotEmpty
                              ? preview.heldBack.first.detail
                              : 'That is not something this PC can do.'),
                    ),
                  for (var i = 0; i < preview.steps.length; i++)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          CircleAvatar(
                            radius: 13,
                            backgroundColor: theme.colorScheme.primaryContainer,
                            child: Text(
                              '${i + 1}',
                              style: textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w700),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.only(top: 3),
                              child: Text(preview.steps[i].description),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (preview.heldBack.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Will not run',
                      style: textTheme.labelLarge?.copyWith(color: AppColors.warning),
                    ),
                    for (final held in preview.heldBack)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          held.detail.isEmpty ? held.reason : held.detail,
                          style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                        ),
                      ),
                  ],
                  if (preview.lowConfidence) ...[
                    const SizedBox(height: 12),
                    const ErrorBanner(
                      'The AI is not very sure about this plan. Check it before you run it.',
                      color: AppColors.warning,
                    ),
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Gap.page, 12, Gap.page, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (preview.runnable) ...[
                    FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: Text(preview.heldBack.isEmpty ? 'Run' : 'Run what can run'),
                    ),
                    const SizedBox(height: 8),
                  ],
                  OutlinedButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: Text(preview.runnable ? 'Cancel' : 'Close'),
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
