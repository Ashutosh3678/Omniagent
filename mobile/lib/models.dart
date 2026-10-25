enum TaskStatus { success, failed, running }

class TaskItem {
  const TaskItem({
    required this.title,
    required this.when,
    required this.status,
    this.fileName,
  });

  final String title;
  final String when;
  final TaskStatus status;
  final String? fileName;

  String get statusLabel => switch (status) {
        TaskStatus.success => 'Success',
        TaskStatus.failed => 'Failed',
        TaskStatus.running => 'Running',
      };
}

class PcDevice {
  const PcDevice({
    required this.name,
    required this.hostName,
    required this.online,
  });

  final String name;
  final String hostName;
  final bool online;
}
