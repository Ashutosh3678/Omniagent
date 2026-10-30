import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SessionUser {
  const SessionUser({required this.email, required this.name});

  final String email;
  final String name;

  String get displayName => name.isNotEmpty ? name : email.split('@').first;
}

/// The signed-in account. The token lives in the platform's secure storage.
class Session extends ChangeNotifier {
  Session({FlutterSecureStorage? storage}) : _storage = storage ?? const FlutterSecureStorage();

  static const _tokenKey = 'access_token';
  static const _emailKey = 'user_email';
  static const _nameKey = 'user_name';

  final FlutterSecureStorage _storage;
  String? _token;
  SessionUser? _user;

  String? get token => _token;
  SessionUser? get user => _user;
  bool get isSignedIn => _token != null;

  Future<void> load() async {
    try {
      _token = await _storage.read(key: _tokenKey);
      final email = await _storage.read(key: _emailKey);
      final name = await _storage.read(key: _nameKey);
      if (_token != null && email != null) {
        _user = SessionUser(email: email, name: name ?? '');
      } else {
        _token = null;
      }
    } catch (_) {
      _token = null;
      _user = null;
    }
  }

  Future<void> signIn({required String token, required String email, required String name}) async {
    _token = token;
    _user = SessionUser(email: email, name: name);
    try {
      await _storage.write(key: _tokenKey, value: token);
      await _storage.write(key: _emailKey, value: email);
      await _storage.write(key: _nameKey, value: name);
    } catch (_) {
      // Still signed in for this run if storage is unavailable.
    }
    notifyListeners();
  }

  Future<void> signOut() async {
    if (_token == null) return;
    _token = null;
    _user = null;
    // Leave the app first; clearing secure storage can be slow or fail and must not block sign-out.
    notifyListeners();
    try {
      await _storage.deleteAll();
    } catch (_) {}
  }
}

final appSession = Session();
