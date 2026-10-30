import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'models.dart';
import 'theme.dart';

/// "just now", "5 min ago", "Yesterday", "Oct 24" from an ISO timestamp. Unparseable text is shown as-is.
String formatWhen(String value, {DateTime? now}) {
  final parsed = DateTime.tryParse(value);
  if (parsed == null) return value;
  final time = parsed.toLocal();
  final current = now ?? DateTime.now();
  final diff = current.difference(time);
  if (diff.inSeconds < 60) return 'Just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
  final today = DateTime(current.year, current.month, current.day);
  final day = DateTime(time.year, time.month, time.day);
  final days = today.difference(day).inDays;
  if (days == 0) return '${diff.inHours} h ago';
  if (days == 1) return 'Yesterday';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${months[time.month - 1]} ${time.day}';
}

/// Color and icon that go with each task status; used everywhere a status is shown.
({Color color, IconData icon}) statusStyle(TaskStatus status) => switch (status) {
      TaskStatus.completed => (color: AppColors.success, icon: Icons.check_circle_rounded),
      TaskStatus.partial => (color: AppColors.warning, icon: Icons.error_rounded),
      TaskStatus.failed => (color: AppColors.danger, icon: Icons.cancel_rounded),
      TaskStatus.running => (color: AppColors.secondary, icon: Icons.autorenew_rounded),
      TaskStatus.pending => (color: AppColors.textMuted, icon: Icons.schedule_rounded),
    };

/// A rounded surface that groups related content.
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Gap.radius),
        side: const BorderSide(color: AppColors.outline),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(padding: padding, child: SizedBox(width: double.infinity, child: child)),
      ),
    );
  }
}

/// A small read-only label with a colored dot or icon (device state, task status, permissions).
class Pill extends StatelessWidget {
  const Pill({super.key, required this.label, required this.color, this.icon});

  final String label;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null)
            Icon(icon, size: 14, color: color)
          else
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: color, fontSize: 12.5, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class TaskStatusPill extends StatelessWidget {
  const TaskStatusPill({super.key, required this.status, this.label});

  final TaskStatus status;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final style = statusStyle(status);
    return Pill(
      label: label ?? TaskItem(title: '', when: '', status: status).statusLabel,
      color: style.color,
    );
  }
}

/// A selectable filter. Unlike a status label, this one is tappable.
class FilterPill extends StatelessWidget {
  const FilterPill({super.key, required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      showCheckmark: false,
      onSelected: (_) => onTap(),
    );
  }
}

class TaskTile extends StatelessWidget {
  const TaskTile({super.key, required this.task, this.onTap});

  final TaskItem task;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final style = statusStyle(task.status);
    final textTheme = Theme.of(context).textTheme;
    return Panel(
      onTap: onTap,
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: style.color.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(style.icon, color: style.color, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  task.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                Text(
                  formatWhen(task.when),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          TaskStatusPill(status: task.status),
        ],
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.message = ''});

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: AppColors.surfaceHigh,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Icon(icon, size: 30, color: AppColors.primary),
          ),
          const SizedBox(height: 16),
          Text(title, textAlign: TextAlign.center, style: textTheme.titleMedium),
          if (message.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
            ),
          ],
        ],
      ),
    );
  }
}

class ErrorBanner extends StatelessWidget {
  const ErrorBanner(this.message, {super.key, this.color = AppColors.danger});

  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline_rounded, color: color, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(message, style: TextStyle(color: color, height: 1.3))),
        ],
      ),
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
    final textTheme = Theme.of(context).textTheme;
    Widget message(IconData icon, String text) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: AppColors.textMuted, size: 32),
              const SizedBox(height: 8),
              Text(text, style: textTheme.bodyMedium?.copyWith(color: AppColors.textMuted)),
            ],
          ),
        );

    final Widget content;
    if (url != null) {
      content = Image.network(
        url!,
        headers: headers,
        fit: BoxFit.contain,
        width: double.infinity,
        height: height,
        loadingBuilder: (context, child, progress) =>
            progress == null ? child : const Center(child: CircularProgressIndicator()),
        errorBuilder: (context, error, stack) => message(Icons.broken_image_outlined, 'Screenshot unavailable'),
      );
    } else if (bytes != null) {
      content = Image.memory(bytes!, fit: BoxFit.contain, width: double.infinity, height: height);
    } else {
      content = message(Icons.desktop_windows_outlined, 'Waiting for a screenshot');
    }

    return Container(
      height: height,
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(Gap.radius),
        border: Border.all(color: AppColors.outline),
      ),
      clipBehavior: Clip.antiAlias,
      child: content,
    );
  }
}
