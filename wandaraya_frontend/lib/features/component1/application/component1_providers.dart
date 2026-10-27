import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/component1_api.dart';
import '../domain/component1_models.dart';
import '../domain/recommendation_models.dart';

final knowledgeBaseStatusProvider = FutureProvider<KnowledgeBaseStatus>(
  (ref) => ref.watch(component1ApiProvider).status(),
);
final attractionListProvider = FutureProvider<List<AttractionSummary>>(
  (ref) => ref.watch(component1ApiProvider).attractions(),
);
final categoriesProvider = FutureProvider<List<TaxonomyItem>>(
  (ref) => ref.watch(component1ApiProvider).categories(),
);
final districtsProvider = FutureProvider<List<TaxonomyItem>>(
  (ref) => ref.watch(component1ApiProvider).districts(),
);
final attractionDetailProvider = FutureProvider.family<AttractionDetail, int>(
  (ref, id) => ref.watch(component1ApiProvider).attraction(id),
);

final recommendationSessionProvider =
    NotifierProvider<RecommendationSessionController, RecommendationSession>(
      RecommendationSessionController.new,
    );

class RecommendationSession {
  const RecommendationSession({this.request, this.response});
  final TravelRecommendationRequest? request;
  final RecommendationResponse? response;
}

class RecommendationSessionController extends Notifier<RecommendationSession> {
  @override
  RecommendationSession build() => const RecommendationSession();

  void save(
    TravelRecommendationRequest request,
    RecommendationResponse response,
  ) {
    state = RecommendationSession(request: request, response: response);
  }

  void clear() => state = const RecommendationSession();
}

final savedPlaceIdsProvider = NotifierProvider<SavedPlaceIds, Set<int>>(
  SavedPlaceIds.new,
);

class SavedPlaceIds extends Notifier<Set<int>> {
  @override
  Set<int> build() => <int>{};

  void toggle(int id) {
    state = state.contains(id) ? ({...state}..remove(id)) : {...state, id};
  }
}
