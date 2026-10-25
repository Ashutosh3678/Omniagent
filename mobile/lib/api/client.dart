import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models.dart';
import 'config.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => message;
}

class OmniApi {
  OmniApi({http.Client? client, String? baseUrl, String? token})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? kApiBase,
        _token = token ?? kAppToken;

  final http.Client _client;
  final String _baseUrl;
  final String _token;

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $_token',
        'Content-Type': 'application/json',
      };

  Future<List<PcDevice>> listAgents() async {
    final body = await _get('/v1/agents');
    return (body as List<dynamic>).map((item) {
      final map = item as Map<String, dynamic>;
      return PcDevice(
        id: map['id'] as String?,
        name: map['name'] as String,
        hostName: map['hostname'] as String,
        online: map['online'] as bool? ?? false,
      );
    }).toList();
  }

  Future<TaskItem> createTask(String instruction, {String? agentId}) async {
    final body = await _send(
      'POST',
      '/v1/tasks',
      {'instruction': instruction, 'agent_id': ?agentId},
    );
    return TaskItem.fromJson(body as Map<String, dynamic>, apiBase: _baseUrl);
  }

  Future<TaskItem> getTask(String id) async {
    final body = await _get('/v1/tasks/$id');
    return TaskItem.fromJson(body as Map<String, dynamic>, apiBase: _baseUrl);
  }

  Future<List<TaskItem>> listTasks() async {
    final body = await _get('/v1/tasks');
    return (body as List<dynamic>)
        .map((item) => TaskItem.fromJson(item as Map<String, dynamic>, apiBase: _baseUrl))
        .toList();
  }

  Future<void> cancelTask(String id) async {
    await _send('POST', '/v1/tasks/$id/cancel', const {});
  }

  Future<Uint8List?> getScreenshot(String taskId) async {
    final response = await _client.get(
      Uri.parse('$_baseUrl/v1/tasks/$taskId/screenshot'),
      headers: _headers,
    );
    if (response.statusCode == 404) return null;
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

  dynamic _decode(http.Response response) {
    if (response.statusCode >= 400) {
      var message = response.body;
      try {
        final json = jsonDecode(response.body);
        if (json is Map && json['detail'] != null) {
          message = json['detail'].toString();
        }
      } catch (_) {}
      throw ApiException(response.statusCode, message);
    }
    if (response.body.isEmpty) return null;
    return jsonDecode(response.body);
  }
}

final omniApi = OmniApi();
