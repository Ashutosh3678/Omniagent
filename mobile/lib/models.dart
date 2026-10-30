enum TaskStatus { pending, running, completed, partial, failed }

/// Screenshots arrive as full CDN addresses, or as paths on the backend when the CDN is not in use.
String? resolveUrl(String apiBase, String? value) {
  if (value == null || value.isEmpty) return null;
  return value.startsWith('http') ? value : '$apiBase$value';
}

class TaskStep {
  const TaskStep({
    required this.name,
    required this.status,
    this.detail = '',
    this.hasScreenshot = false,
    this.screenshotUrl,
  });

  final String name;
  final String status;
  final String detail;
  final bool hasScreenshot;
  final String? screenshotUrl;

  /// A step that did something but could not be confirmed, or did not work.
  bool get hasProblem =>
      status == 'failed' || status == 'unverified' || status == 'held_back';
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
      when:
          json['updated_at'] as String? ?? json['created_at'] as String? ?? '',
      status: TaskStatus.values.firstWhere(
        (value) => value.name == statusName,
        orElse: () => TaskStatus.pending,
      ),
      fileName: screenshot?.split('?').first.split('/').last,
      screenshotUrl: resolveUrl(apiBase, screenshot),
      summary: json['summary'] as String? ?? '',
      error: json['error'] as String? ?? '',
      steps: [
        for (final step in (json['steps'] as List<dynamic>? ?? const []))
          TaskStep(
            name: (step as Map<String, dynamic>)['name'] as String? ?? '',
            status: step['status'] as String? ?? 'pending',
            detail: step['detail'] as String? ?? '',
            hasScreenshot: step['has_screenshot'] as bool? ?? false,
            screenshotUrl: resolveUrl(
              apiBase,
              step['screenshot_url'] as String?,
            ),
          ),
      ],
    );
  }
}

/// An app a PC can open, as its OmniAgent program reported it.
class AppInfo {
  const AppInfo({
    required this.id,
    required this.label,
    this.needsWorkspace = false,
  });

  final String id;
  final String label;

  /// True for apps that work inside a folder chosen on the PC (Claude Code).
  final bool needsWorkspace;

  factory AppInfo.fromJson(Map<String, dynamic> map) => AppInfo(
    id: map['id'] as String,
    label: map['label'] as String? ?? map['id'] as String,
    needsWorkspace: map['needs_workspace'] as bool? ?? false,
  );
}

class PcDevice {
  const PcDevice({
    required this.name,
    required this.hostName,
    required this.online,
    this.id,
    this.revoked = false,
    this.permittedApps = const [],
    this.actions = const [],
    this.apps = const [],
    this.workspaces = const [],
    this.expiresAt,
  });

  final String? id;
  final String name;
  final String hostName;
  final bool online;
  final bool revoked;
  final List<String> permittedApps;

  /// What the PC's agent says it can do (empty until it has connected).
  final List<String> actions;

  /// The apps this PC can open, and the folder names set up on it (empty until it has connected).
  final List<AppInfo> apps;
  final List<String> workspaces;
  final DateTime? expiresAt;

  bool get canBrowse => actions.contains('browser_navigate');

  factory PcDevice.fromJson(Map<String, dynamic> map) => PcDevice(
    id: map['id'] as String?,
    name: map['name'] as String,
    hostName: map['hostname'] as String,
    online: map['online'] as bool? ?? false,
    revoked: map['status'] == 'revoked',
    permittedApps: [
      for (final app in (map['permitted_apps'] as List<dynamic>? ?? const []))
        app as String,
    ],
    actions: [
      for (final action in (map['actions'] as List<dynamic>? ?? const []))
        action as String,
    ],
    apps: [
      for (final app in (map['apps'] as List<dynamic>? ?? const []))
        AppInfo.fromJson(app as Map<String, dynamic>),
    ],
    workspaces: [
      for (final name in (map['workspaces'] as List<dynamic>? ?? const []))
        name as String,
    ],
    expiresAt: map['expires_at'] == null
        ? null
        : DateTime.parse(map['expires_at'] as String).toLocal(),
  );

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
            description:
                (step as Map<String, dynamic>)['description'] as String? ?? '',
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
