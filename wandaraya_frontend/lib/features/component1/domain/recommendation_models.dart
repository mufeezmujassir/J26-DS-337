enum RerankerConfiguration {
  r0('R0_SEMANTIC_BASELINE', 'R0 — Semantic baseline'),
  r1('R1_AVAILABLE_CONTEXT_EQUAL_WEIGHT', 'R1 — Equal available context'),
  r2('R2_EVIDENCE_QUALITY_AWARE', 'R2 — Evidence quality aware'),
  r3(
    'R3_WEATHER_SEASONALITY_REDUNDANCY_CONTROLLED',
    'R3 — Climate redundancy controlled',
  );

  const RerankerConfiguration(this.apiValue, this.label);
  final String apiValue;
  final String label;

  static RerankerConfiguration parse(String value) =>
      values.firstWhere((item) => item.apiValue == value, orElse: () => r3);
}

class TravelRecommendationRequest {
  const TravelRecommendationRequest({
    required this.query,
    required this.travelDateTime,
    required this.configuration,
    this.destinationDistrictId,
    this.requestedActivities = const [],
    this.interests = const [],
    this.groupSize = 1,
    this.durationMinutes,
    this.additionalPreferences,
  });

  final String query;
  final DateTime travelDateTime;
  final RerankerConfiguration configuration;
  final int? destinationDistrictId;
  final List<String> requestedActivities;
  final List<String> interests;
  final int groupSize;
  final int? durationMinutes;
  final String? additionalPreferences;

  Map<String, dynamic> toJson() => {
    'query': query,
    'destination_district_id': destinationDistrictId,
    'travel_datetime': _colomboIso(travelDateTime),
    'requested_activities': requestedActivities,
    'interests': interests,
    'user_preferences': {
      'group_size': groupSize,
      if (additionalPreferences?.isNotEmpty ?? false)
        'additional_preferences': additionalPreferences,
    },
    'group_preferences': <String, dynamic>{},
    'constraints': <String, dynamic>{},
    'contextual_metadata': <String, dynamic>{},
    'limit': 20,
    'candidate_pool_size': 50,
    'visit_duration_minutes': durationMinutes ?? 60,
    'configuration': configuration.apiValue,
    'experimental_evaluation_mode': true,
  };
}

class ContextEvidence {
  const ContextEvidence({
    required this.dimension,
    required this.status,
    required this.explanation,
    required this.limitations,
    required this.missingIndicators,
    this.score,
    this.confidence,
    this.source,
    this.evaluatedAt,
    this.fallbackUsed = false,
    this.fallbackReason,
  });

  factory ContextEvidence.fromJson(Map<String, dynamic> json) =>
      ContextEvidence(
        dimension: json['dimension'] as String? ?? 'unknown',
        status: json['status'] as String? ?? 'NOT_AVAILABLE',
        explanation:
            json['explanation'] as String? ??
            'Evidence unavailable for this attraction.',
        limitations: _stringList(json['limitations']),
        missingIndicators: _stringList(json['missing_data_indicators']),
        score: (json['score'] as num?)?.toDouble(),
        confidence: (json['confidence'] as num?)?.toDouble(),
        source: json['source'] as String?,
        evaluatedAt: DateTime.tryParse(json['evaluated_at'] as String? ?? ''),
        fallbackUsed: json['fallback_used'] as bool? ?? false,
        fallbackReason: json['fallback_reason'] as String?,
      );

  final String dimension;
  final String status;
  final String explanation;
  final List<String> limitations;
  final List<String> missingIndicators;
  final double? score;
  final double? confidence;
  final String? source;
  final DateTime? evaluatedAt;
  final bool fallbackUsed;
  final String? fallbackReason;

  bool get isAvailable =>
      status == 'AVAILABLE' || status == 'PARTIALLY_AVAILABLE';
}

class RankedAttraction {
  const RankedAttraction({
    required this.attractionId,
    required this.name,
    required this.semanticScore,
    required this.semanticRank,
    required this.finalScore,
    required this.experimentalRank,
    required this.rankMovement,
    required this.evidence,
    required this.explanation,
    required this.missingDimensions,
    required this.limitations,
    this.description,
    this.descriptionSource,
    this.city,
    this.districtName,
    this.address,
    this.rating,
    this.reviewCount,
    this.phoneNumber,
    this.websiteUrl,
    this.categories = const [],
    this.activities = const [],
    this.contextScore,
  });

  factory RankedAttraction.fromJson(Map<String, dynamic> json) {
    final explanation = json['explanation'] as Map? ?? const {};
    final evidenceJson = json['evidence'] as Map? ?? const {};
    return RankedAttraction(
      attractionId: json['attraction_id'] as int,
      name: json['attraction_name'] as String,
      semanticScore: (json['original_semantic_score'] as num).toDouble(),
      semanticRank: json['original_semantic_rank'] as int,
      finalScore: (json['final_experimental_context_score'] as num).toDouble(),
      experimentalRank: json['experimental_rank'] as int,
      rankMovement: json['rank_movement'] as int,
      contextScore: (json['context_score'] as num?)?.toDouble(),
      evidence: evidenceJson.map(
        (key, value) => MapEntry(
          key.toString(),
          ContextEvidence.fromJson(Map<String, dynamic>.from(value as Map)),
        ),
      ),
      explanation:
          explanation['summary'] as String? ?? 'No explanation was returned.',
      missingDimensions: _stringList(explanation['missing_dimensions']),
      limitations: _stringList(json['limitations']),
      description: json['description'] as String?,
      descriptionSource: json['description_source'] as String?,
      city: json['city'] as String?,
      districtName: json['district_name'] as String?,
      address: json['address'] as String?,
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: json['review_count'] as int?,
      phoneNumber: json['phone_number'] as String?,
      websiteUrl: json['website_url'] as String?,
      categories: _stringList(json['categories']),
      activities: _stringList(json['activities']),
    );
  }

  final int attractionId;
  final String name;
  final double semanticScore;
  final int semanticRank;
  final double finalScore;
  final int experimentalRank;
  final int rankMovement;
  final double? contextScore;
  final Map<String, ContextEvidence> evidence;
  final String explanation;
  final List<String> missingDimensions;
  final List<String> limitations;
  final String? description;
  final String? descriptionSource;
  final String? city;
  final String? districtName;
  final String? address;
  final double? rating;
  final int? reviewCount;
  final String? phoneNumber;
  final String? websiteUrl;
  final List<String> categories;
  final List<String> activities;
}

class RecommendationResponse {
  const RecommendationResponse({
    required this.query,
    required this.travelDateTime,
    required this.configuration,
    required this.candidates,
    required this.originalOrder,
    required this.experimentalOrder,
    required this.productionOrder,
    required this.limitations,
    required this.errors,
    required this.latencyMs,
  });

  factory RecommendationResponse.fromJson(Map<String, dynamic> json) =>
      RecommendationResponse(
        query: json['query'] as String,
        travelDateTime: DateTime.parse(json['travel_datetime'] as String),
        configuration: RerankerConfiguration.parse(
          json['configuration'] as String,
        ),
        candidates: (json['candidates'] as List? ?? const [])
            .whereType<Map>()
            .map(
              (item) =>
                  RankedAttraction.fromJson(Map<String, dynamic>.from(item)),
            )
            .toList(),
        originalOrder: _intList(json['original_candidate_order']),
        experimentalOrder: _intList(json['experimental_candidate_order']),
        productionOrder: _intList(json['production_candidate_order']),
        limitations: _stringList(json['limitations']),
        errors: (json['errors'] as List? ?? const [])
            .whereType<Map>()
            .map(Map<String, dynamic>.from)
            .toList(),
        latencyMs: ((json['latency'] as Map?)?['end_to_end_ms'] as num?)
            ?.toDouble(),
      );

  final String query;
  final DateTime travelDateTime;
  final RerankerConfiguration configuration;
  final List<RankedAttraction> candidates;
  final List<int> originalOrder;
  final List<int> experimentalOrder;
  final List<int> productionOrder;
  final List<String> limitations;
  final List<Map<String, dynamic>> errors;
  final double? latencyMs;
}

class AgentResponse {
  const AgentResponse({
    required this.sessionId,
    required this.status,
    required this.clarificationRequired,
    required this.recommendations,
    required this.itinerary,
    required this.notRecommended,
    required this.nodesExecuted,
    required this.warnings,
    this.clarificationQuestion,
    this.humanResponse,
  });

  factory AgentResponse.fromJson(Map<String, dynamic> json) => AgentResponse(
    sessionId: json['session_id'] as String,
    status: json['graph_status'] as String,
    clarificationRequired: json['clarification_required'] as bool? ?? false,
    clarificationQuestion: json['clarification_question'] as String?,
    humanResponse: json['human_readable_response'] as String?,
    recommendations: (json['recommendations'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) => RankedAttraction.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList(),
    itinerary: (json['itinerary'] as List? ?? const [])
        .whereType<Map>()
        .map((item) => ItineraryStop.fromJson(Map<String, dynamic>.from(item)))
        .toList(),
    notRecommended: (json['not_recommended'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) =>
              NotRecommendedPlace.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList(),
    nodesExecuted: _stringList(json['nodes_executed']),
    warnings: _stringList(json['warnings']),
  );

  final String sessionId;
  final String status;
  final bool clarificationRequired;
  final String? clarificationQuestion;
  final String? humanResponse;
  final List<RankedAttraction> recommendations;
  final List<ItineraryStop> itinerary;
  final List<NotRecommendedPlace> notRecommended;
  final List<String> nodesExecuted;
  final List<String> warnings;
}

class NotRecommendedPlace {
  const NotRecommendedPlace({
    required this.attractionId,
    required this.attractionName,
    required this.reason,
    required this.weatherSummary,
    this.location,
  });

  factory NotRecommendedPlace.fromJson(Map<String, dynamic> json) =>
      NotRecommendedPlace(
        attractionId: json['attraction_id'] as int,
        attractionName: json['attraction_name'] as String,
        location: json['location'] as String?,
        reason: json['reason'] as String,
        weatherSummary: json['weather_summary'] as String,
      );

  final int attractionId;
  final String attractionName;
  final String? location;
  final String reason;
  final String weatherSummary;
}

class ItineraryStop {
  const ItineraryStop({
    required this.order,
    required this.visitDate,
    required this.startTime,
    required this.endTime,
    required this.attractionId,
    required this.attractionName,
    required this.reason,
    required this.transferMinutes,
    this.location,
    this.description,
    this.expectedBehavior,
    this.transferNote,
  });

  factory ItineraryStop.fromJson(Map<String, dynamic> json) => ItineraryStop(
    order: json['order'] as int,
    visitDate: json['visit_date'] as String,
    startTime: json['start_time'] as String,
    endTime: json['end_time'] as String,
    attractionId: json['attraction_id'] as int,
    attractionName: json['attraction_name'] as String,
    location: json['location'] as String?,
    description: json['description'] as String?,
    expectedBehavior: json['expected_behavior'] as String?,
    reason: json['reason'] as String,
    transferMinutes: json['transfer_from_previous_minutes'] as int? ?? 0,
    transferNote: json['transfer_note'] as String?,
  );

  final int order;
  final String visitDate;
  final String startTime;
  final String endTime;
  final int attractionId;
  final String attractionName;
  final String? location;
  final String? description;
  final String? expectedBehavior;
  final String reason;
  final int transferMinutes;
  final String? transferNote;
}

List<String> _stringList(Object? value) =>
    (value as List? ?? const []).whereType<String>().toList(growable: false);
List<int> _intList(Object? value) =>
    (value as List? ?? const []).whereType<int>().toList(growable: false);

String _colomboIso(DateTime value) {
  String two(int number) => number.toString().padLeft(2, '0');
  return '${value.year.toString().padLeft(4, '0')}-${two(value.month)}-${two(value.day)}T${two(value.hour)}:${two(value.minute)}:00+05:30';
}
