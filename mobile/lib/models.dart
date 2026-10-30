enum TaskStatus { pending, running, completed, partial, failed }

class TaskStep {
  const TaskStep({required this.name, required this.status, this.detail = ''});

  final String name;
  final String status;
  final String detail;
}

class TaskItem {
  const TaskItem({
    required this.title,
    required this.when,
    required this.status,
    this.id,
    this.fileName,
    this.screenshotUrl,
    this.summary = '',
    this.error = '',
    this.steps = const [],
  });

  final String? id;
  final String title;
  final String when;
  final TaskStatus status;
  final String? fileName;
  final String? screenshotUrl;
  final String summary;
  final String error;
  final List<TaskStep> steps;

  String get statusLabel => switch (status) {
        TaskStatus.pending => 'Pending',
        TaskStatus.running => 'Running',
        TaskStatus.completed => 'Success',
        TaskStatus.partial => 'Partial',
        TaskStatus.failed => 'Failed',
      };

  factory TaskItem.fromJson(Map<String, dynamic> json, {String apiBase = ''}) {
    final statusName = json['status'] as String? ?? 'pending';
    final screenshot = json['screenshot_url'] as String?;
    return TaskItem(
      id: json['id'] as String?,
      title: json['instruction'] as String? ?? json['title'] as String? ?? '',
      when: json['updated_at'] as String? ?? json['created_at'] as String? ?? '',
      status: TaskStatus.values.firstWhere(
        (value) => value.name == statusName,
        orElse: () => TaskStatus.pending,
      ),
      fileName: screenshot?.split('/').last,
      screenshotUrl: screenshot == null ? null : '$apiBase$screenshot',
      summary: json['summary'] as String? ?? '',
      error: json['error'] as String? ?? '',
      steps: [
        for (final step in (json['steps'] as List<dynamic>? ?? const []))
          TaskStep(
            name: (step as Map<String, dynamic>)['name'] as String? ?? '',
            status: step['status'] as String? ?? 'pending',
            detail: step['detail'] as String? ?? '',
          ),
      ],
    );
  }
}

class PcDevice {
  const PcDevice({
    required this.name,
    required this.hostName,
    required this.online,
    this.id,
    this.revoked = false,
    this.permittedApps = const [],
    this.expiresAt,
  });

  final String? id;
  final String name;
  final String hostName;
  final bool online;
  final bool revoked;
  final List<String> permittedApps;
  final DateTime? expiresAt;

  bool get expired => expiresAt != null && !expiresAt!.isAfter(DateTime.now());

  /// Whether tasks can be sent to this PC right now.
  bool get usable => online && !revoked && !expired;
}

class PreviewStep {
  const PreviewStep({required this.description, required this.confidence});

  final String description;
  final double confidence;
}

class HeldStep {
  const HeldStep({required this.reason, required this.detail});

  final String reason;
  final String detail;
}

/// A plan the backend has made and checked but not run yet.
class PlanPreview {
  const PlanPreview({
    required this.planner,
    required this.steps,
    required this.heldBack,
    required this.runnable,
    required this.lowConfidence,
    required this.note,
    required this.plan,
    this.confidence,
  });

  final String planner;
  final List<PreviewStep> steps;
  final List<HeldStep> heldBack;
  final bool runnable;
  final bool lowConfidence;
  final String note;
  final double? confidence;

  /// The raw plan, sent back unchanged when the user confirms.
  final List<dynamic> plan;

  factory PlanPreview.fromJson(Map<String, dynamic> json) {
    return PlanPreview(
      planner: json['planner'] as String? ?? '',
      steps: [
        for (final step in (json['steps'] as List<dynamic>? ?? const []))
          PreviewStep(
            description: (step as Map<String, dynamic>)['description'] as String? ?? '',
            confidence: (step['confidence'] as num?)?.toDouble() ?? 1,
          ),
      ],
      heldBack: [
        for (final held in (json['held_back'] as List<dynamic>? ?? const []))
          HeldStep(
            reason: (held as Map<String, dynamic>)['reason'] as String? ?? '',
            detail: held['detail'] as String? ?? '',
          ),
      ],
      runnable: json['runnable'] as bool? ?? false,
      lowConfidence: json['low_confidence'] as bool? ?? false,
      note: json['note'] as String? ?? '',
      confidence: (json['confidence'] as num?)?.toDouble(),
      plan: json['plan'] as List<dynamic>? ?? const [],
    );
  }
}

class PairingCode {
  const PairingCode({required this.code, required this.expiresAt});

  final String code;
  final DateTime expiresAt;
}
