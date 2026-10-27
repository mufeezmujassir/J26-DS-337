import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/config/environment.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../domain/component1_models.dart';
import '../domain/recommendation_models.dart';

final component1ApiProvider = Provider<Component1Api>(
  (ref) => Component1Api(ref.watch(dioProvider)),
);

final researchCredentialsProvider = Provider<ResearchCredentialsStore>(
  (ref) => const ResearchCredentialsStore(),
);

class ResearchCredentialsStore {
  const ResearchCredentialsStore();
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'component1_research_token';

  Future<String?> readToken() => _storage.read(key: _tokenKey);
  Future<void> saveToken(String value) =>
      _storage.write(key: _tokenKey, value: value.trim());
  Future<void> clear() => _storage.delete(key: _tokenKey);
}

class Component1Api {
  const Component1Api(this._dio);
  final Dio _dio;

  Future<bool> health() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/health');
      return response.data?['status'] == 'ok';
    } on DioException catch (error) {
      throw mapDioException(error);
    }
  }

  Future<KnowledgeBaseStatus> status() async =>
      _getObject('/api/v1/knowledge-base/status', KnowledgeBaseStatus.fromJson);

  Future<List<AttractionSummary>> attractions({int limit = 20}) async =>
      _getList(
        '/api/v1/knowledge-base/attractions',
        AttractionSummary.fromJson,
        query: {'limit': limit},
      );

  Future<List<AttractionSummary>> semanticSearch(
    String query, {
    int limit = 10,
  }) async => _getList(
    '/api/v1/knowledge-base/semantic-search',
    AttractionSummary.fromJson,
    query: {'query': query, 'limit': limit},
  );

  Future<AttractionDetail> attraction(int id) async => _getObject(
    '/api/v1/knowledge-base/attractions/$id',
    AttractionDetail.fromJson,
  );

  Future<List<TaxonomyItem>> categories() async =>
      _getList('/api/v1/knowledge-base/categories', TaxonomyItem.category);

  Future<List<TaxonomyItem>> districts() async =>
      _getList('/api/v1/knowledge-base/districts', TaxonomyItem.district);

  Future<RecommendationResponse> recommend(
    TravelRecommendationRequest request, {
    required String token,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v1/research/recommendations/context-aware',
        data: request.toJson(),
        options: Options(headers: {'X-Research-Token': token}),
      );
      return RecommendationResponse.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw mapDioException(error);
    } on FormatException {
      throw const ApiException('The recommendation response was malformed.');
    }
  }

  Future<AgentResponse> agent({
    required String sessionId,
    required String message,
    String? token,
    RerankerConfiguration configuration = RerankerConfiguration.r3,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v1/research/agents/context-aware',
        data: {
          'session_id': sessionId,
          'message': message,
          'reranker_configuration': configuration.apiValue,
          'candidate_limit': 50,
          'result_limit': 20,
        },
        options: Options(
          headers: {
            if (token?.isNotEmpty ?? false) 'X-Research-Token': token,
            'X-Research-Owner': Environment.researchOwner,
          },
        ),
      );
      return AgentResponse.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw mapDioException(error);
    } on FormatException {
      throw const ApiException('The LangGraph response was malformed.');
    }
  }

  Future<T> _getObject<T>(
    String path,
    T Function(Map<String, dynamic>) parser,
  ) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(path);
      return parser(response.data ?? const {});
    } on DioException catch (error) {
      throw mapDioException(error);
    } on FormatException {
      throw const ApiException('The service returned malformed data.');
    }
  }

  Future<List<T>> _getList<T>(
    String path,
    T Function(Map<String, dynamic>) parser, {
    Map<String, dynamic>? query,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        path,
        queryParameters: query,
      );
      return (response.data ?? const [])
          .whereType<Map>()
          .map((item) => parser(Map<String, dynamic>.from(item)))
          .toList();
    } on DioException catch (error) {
      throw mapDioException(error);
    } on FormatException {
      throw const ApiException('The service returned malformed data.');
    }
  }
}
