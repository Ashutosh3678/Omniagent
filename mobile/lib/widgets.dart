import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'models.dart';
import 'theme.dart';

class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    this.selected = false,
    this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      showCheckmark: selected,
      onSelected: onTap == null ? null : (_) => onTap!(),
    );
  }
}

class SuccessBadge extends StatelessWidget {
  const SuccessBadge({super.key, this.label = 'Success'});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: kSuccessContainer,
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircleAvatar(radius: 4, backgroundColor: kSuccess),
          const SizedBox(width: 8),
          Text(
            label,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: kOnSuccessContainer,
                ),
          ),
        ],
      ),
    );
  }
}

class TaskTile extends StatelessWidget {
  const TaskTile({super.key, required this.task, this.onTap});

  final TaskItem task;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(task.title),
      subtitle: Text(task.when),
      trailing: Text(
        task.statusLabel,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: task.status == TaskStatus.failed
                  ? Theme.of(context).colorScheme.error
                  : task.status == TaskStatus.completed
                      ? kSuccess
                      : task.status == TaskStatus.partial
                          ? Theme.of(context).colorScheme.tertiary
                          : Theme.of(context).colorScheme.primary,
            ),
      ),
      onTap: onTap,
    );
  }
}

class ScreenPreview extends StatelessWidget {
  const ScreenPreview({super.key, this.height, this.bytes, this.url, this.headers = const {}});

  final double? height;
  final Uint8List? bytes;

  /// A screenshot to load over the network (normally straight from the CDN).
  final String? url;
  final Map<String, String> headers;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: height,
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.outlineVariant),
      ),
      alignment: Alignment.topLeft,
      clipBehavior: Clip.antiAlias,
      child: url != null
          ? Image.network(
              url!,
              headers: headers,
              fit: BoxFit.cover,
              width: double.infinity,
              height: height,
              loadingBuilder: (context, child, progress) =>
                  progress == null ? child : const Center(child: CircularProgressIndicator()),
              errorBuilder: (context, error, stack) => const Center(child: Text('Screenshot unavailable')),
            )
          : bytes != null
          ? Image.memory(bytes!, fit: BoxFit.cover, width: double.infinity, height: height)
          : Container(
        width: 220,
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Notepad', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            Text(
              'Hello from OmniAgent',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}
