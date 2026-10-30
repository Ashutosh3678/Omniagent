import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models.dart';
import 'config.dart';
import 'session.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => message;
}

class OmniApi {
  OmniApi({http.Client? client, String? baseUrl, Session? session})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? kApiBase,
        _session = session ?? appSession;

  final http.Client _client;
  final String _baseUrl;
  final Session _session;

  Map<String, String> get _headers => {
        if (_session.token != null) 'Authorization': 'Bearer ${_session.token}',
        'Content-Type': 'application/json',
      };

  Future<void> register(String email, String password, {String name = ''}) =>
      _authenticate('/api/v1/auth/register', {'email': email, 'password': password, 'name': name});

  Future<void> login(String email, String password) =>
      _authenticate('/api/v1/auth/login', {'email': email, 'password': password});

  Future<void> _authenticate(String path, Map<String, dynamic> payload) async {
    final response = await _client.post(
      Uri.parse('$_baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    final body = _decode(response, signOutOn401: false) as Map<String, dynamic>;
    final user = body['user'] as Map<String, dynamic>;
    await _session.signIn(
      token: body['access_token'] as String,
      email: user['email'] as String,
      name: user['name'] as String? ?? '',
    );
  }

  Future<List<PcDevice>> listAgents() async {
    final body = await _get('/api/v1/agents');
    return (body as List<dynamic>).map((item) {
      final map = item as Map<String, dynamic>;
      return PcDevice(
        id: map['id'] as String?,
        name: map['name'] as String,
        hostName: map['hostname'] as String,
        online: map['online'] as bool? ?? false,
        revoked: map['status'] == 'revoked',
        permittedApps: [
          for (final app in (map['permitted_apps'] as List<dynamic>? ?? const [])) app as String,
        ],
        expiresAt: map['expires_at'] == null ? null : DateTime.parse(map['expires_at'] as String).toLocal(),
      );
    }).toList();
  }

  Future<PairingCode> createPairingCode() async {
    final body = await _send('POST', '/api/v1/agents/pairing-code', const {}) as Map<String, dynamic>;
    return PairingCode(
      code: body['code'] as String,
      expiresAt: DateTime.parse(body['expires_at'] as String).toLocal(),
    );
  }

  Future<void> revokeAgent(String id) async {
    await _send('POST', '/api/v1/agents/$id/revoke', const {});
  }

  Future<PlanPreview> previewPlan(String instruction, {String? agentId}) async {
    final body = await _send(
      'POST',
      '/api/v1/plans/preview',
      {'instruction': instruction, 'agent_id': ?agentId},
    );
    return PlanPreview.fromJson(body as Map<String, dynamic>);
  }

  /// Pass [plan] to run exactly a plan the user already previewed.
  Future<TaskItem> createTask(String instruction, {String? agentId, List<dynamic>? plan}) async {
    final body = await _send(
      'POST',
      '/api/v1/tasks',
      {'instruction': instruction, 'agent_id': ?agentId, 'plan': ?plan},
    );
    return TaskItem.fromJson(body as Map<String, dynamic>, apiBase: _baseUrl);
  }

  Future<TaskItem> getTask(String id) async {
    final body = await _get('/api/v1/tasks/$id');
    return TaskItem.fromJson(body as Map<String, dynamic>, apiBase: _baseUrl);
  }

  Future<List<TaskItem>> listTasks() async {
    final body = await _get('/api/v1/tasks');
    return (body as List<dynamic>)
        .map((item) => TaskItem.fromJson(item as Map<String, dynamic>, apiBase: _baseUrl))
        .toList();
  }

  Future<void> cancelTask(String id) async {
    await _send('POST', '/api/v1/tasks/$id/cancel', const {});
  }

  Future<Uint8List?> getScreenshot(String taskId) async {
    final response = await _client.get(
      Uri.parse('$_baseUrl/api/v1/tasks/$taskId/screenshot'),
      headers: _headers,
    );
    if (response.statusCode == 404) return null;
    if (response.statusCode == 401) _session.signOut();
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, response.body);
    }
    return response.bodyBytes;
  }

  Future<dynamic> _get(String path) async {
    final response = await _client.get(Uri.parse('$_baseUrl$path'), headers: _headers);
    return _decode(response);
  }

  Future<dynamic> _send(String method, String path, Map<String, dynamic> payload) async {
    final uri = Uri.parse('$_baseUrl$path');
    final response = method == 'POST'
        ? await _client.post(uri, headers: _headers, body: jsonEncode(payload))
        : await _client.get(uri, headers: _headers);
    return _decode(response);
  }

  dynamic _decode(http.Response response, {bool signOutOn401 = true}) {
    if (response.statusCode == 401 && signOutOn401) _session.signOut();
    if (response.statusCode >= 400) {
      var message = response.body;
      try {
        final json = jsonDecode(response.body);
        if (json is Map && json['detail'] is String) {
          message = json['detail'] as String;
        } else if (json is Map && json['detail'] is List) {
          message = 'Please check the details you entered.';
        }
      } catch (_) {}
      throw ApiException(response.statusCode, message);
    }
    if (response.body.isEmpty) return null;
    return jsonDecode(response.body);
  }
}

final omniApi = OmniApi();
