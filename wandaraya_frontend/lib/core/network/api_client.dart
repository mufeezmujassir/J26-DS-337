import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/environment.dart';
import 'api_exception.dart';

final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: Environment.apiBaseUrl,
      connectTimeout: const Duration(seconds: 12),
      // The research graph evaluates several context layers sequentially.
      receiveTimeout: const Duration(seconds: 135),
      sendTimeout: const Duration(seconds: 15),
      headers: const {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    ),
  );
  ref.onDispose(() => dio.close(force: true));
  return dio;
});

ApiException mapDioException(DioException error) {
  final status = error.response?.statusCode;
  final data = error.response?.data;
  final detail = data is Map<String, dynamic> ? data['detail'] : null;
  if (detail is String && detail.isNotEmpty) {
    return ApiException(detail, statusCode: status);
  }
  if (status == 401) {
    return const ApiException(
      'Research authentication was rejected.',
      statusCode: 401,
    );
  }
  if (status == 403) {
    return const ApiException(
      'This research session is not authorized.',
      statusCode: 403,
    );
  }
  if (status == 422 || status == 400) {
    return ApiException(
      'The request was not accepted by the recommendation service.',
      statusCode: status,
    );
  }
  if (status == 503) {
    return const ApiException(
      'This research capability is currently disabled or unavailable.',
      statusCode: 503,
    );
  }
  if (error.type == DioExceptionType.receiveTimeout) {
    return const ApiException(
      'The recommendation is taking longer than expected. Please retry once.',
    );
  }
  if (error.type == DioExceptionType.connectionTimeout ||
      error.type == DioExceptionType.connectionError) {
    return const ApiException(
      'Unable to connect to the WANDARAYA recommendation service.',
    );
  }
  return ApiException(
    'The recommendation service returned an unexpected response.',
    statusCode: status,
  );
}
