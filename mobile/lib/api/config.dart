/// The deployed backend. To use a backend on your own machine instead:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000   (Android emulator)
const String kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://omniagent-backend-22fj.onrender.com',
);
