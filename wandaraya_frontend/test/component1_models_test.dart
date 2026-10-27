import 'package:flutter_test/flutter_test.dart';
import 'package:wandaraya_frontend/features/component1/domain/recommendation_models.dart';

void main() {
  group('Component 1 API models', () {
    test(
      'request uses the explicit Colombo offset and excludes group emotion',
      () {
        final request = TravelRecommendationRequest(
          query: 'quiet nature near Ella',
          travelDateTime: DateTime(2026, 8, 26, 9, 30),
          configuration: RerankerConfiguration.r3,
          destinationDistrictId: 6,
          interests: const ['Nature'],
          groupSize: 4,
        );

        final json = request.toJson();
        expect(json['travel_datetime'], '2026-08-26T09:30:00+05:30');
        expect(json['configuration'], RerankerConfiguration.r3.apiValue);
        expect(json['contextual_metadata'], isEmpty);
        expect(json.toString(), isNot(contains('group_emotion')));
      },
    );

    test('nullable context evidence is preserved as unavailable evidence', () {
      final candidate = RankedAttraction.fromJson({
        'attraction_id': 17,
        'attraction_name': "Little Adam's Peak",
        'original_semantic_score': 0.81,
        'original_semantic_rank': 2,
        'final_experimental_context_score': 0.74,
        'experimental_rank': 1,
        'rank_movement': 1,
        'context_score': null,
        'evidence': {
          'weather': {
            'dimension': 'weather',
            'status': 'NOT_AVAILABLE',
            'score': null,
            'confidence': null,
            'explanation': 'Weather evidence was unavailable.',
            'limitations': ['Provider unavailable'],
            'missing_data_indicators': ['forecast'],
          },
        },
        'explanation': {
          'summary': 'Strong semantic match.',
          'missing_dimensions': ['weather'],
        },
        'limitations': ['Weather was not used'],
      });

      expect(candidate.contextScore, isNull);
      expect(candidate.evidence['weather']!.score, isNull);
      expect(candidate.evidence['weather']!.isAvailable, isFalse);
      expect(candidate.rankMovement, 1);
      expect(candidate.semanticScore, closeTo(0.81, 0.0001));
    });

    test(
      'agent clarification response parses without invented recommendations',
      () {
        final response = AgentResponse.fromJson({
          'session_id': 'demo-session',
          'graph_status': 'needs_clarification',
          'clarification_required': true,
          'clarification_question': 'Which district would you like to visit?',
          'human_readable_response': null,
          'recommendations': [],
          'nodes_executed': ['intent_parser', 'clarification'],
          'warnings': [],
        });

        expect(response.clarificationRequired, isTrue);
        expect(response.clarificationQuestion, contains('district'));
        expect(response.recommendations, isEmpty);
        expect(response.nodesExecuted, contains('clarification'));
      },
    );
  });
}
