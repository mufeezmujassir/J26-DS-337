import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/async_states.dart';
import '../application/component1_providers.dart';
import '../domain/recommendation_models.dart';

class ResearchInsightsScreen extends ConsumerWidget {
  const ResearchInsightsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(knowledgeBaseStatusProvider);
    final response = ref.watch(recommendationSessionProvider).response;
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Research insights'),
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Ranking'),
              Tab(text: 'Context'),
              Tab(text: 'Pipeline'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _Overview(status: status, response: response),
            _Ranking(response: response),
            _Context(response: response),
            const _Pipeline(),
          ],
        ),
      ),
    );
  }
}

class _Overview extends StatelessWidget {
  const _Overview({required this.status, this.response});
  final AsyncValue<dynamic> status;
  final RecommendationResponse? response;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      const _Notice(),
      const SizedBox(height: 18),
      Text(
        'Knowledge base',
        style: Theme.of(context).textTheme.titleLarge
            ?.copyWith(fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 12),
      status.when(
        loading: () => const LoadingCards(count: 2),
        error: (error, _) => AppErrorState(
          message: error is ApiException
              ? error.message
              : 'Knowledge-base status is unavailable.',
          onRetry: () {},
        ),
        data: (value) => GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 1.5,
          children: [
            _Metric(label: 'Attractions', value: '${value.activeAttractions}'),
            _Metric(
              label: 'District mapped',
              value: '${value.mappedAttractions}',
            ),
            _Metric(label: 'Categories', value: '${value.categories}'),
            _Metric(label: 'Activities', value: '${value.activities}'),
            _Metric(label: 'Embedding', value: '${value.embeddingDimension}D'),
            _Metric(
              label: 'Qdrant points',
              value: value.qdrantPoints?.toString() ?? 'Unavailable',
            ),
          ],
        ),
      ),
      const SizedBox(height: 20),
      const ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(
          Icons.psychology_alt_outlined,
          color: AppColors.textSecondary,
        ),
        title: Text(
          'Group Emotion — Future Integration',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Text(
          'Not integrated into Component 1 ranking or presented as an active context score.',
        ),
      ),
      if (response != null) ...[
        const SizedBox(height: 10),
        _Metric(
          label: 'Last request latency',
          value: response!.latencyMs == null
              ? 'Not returned'
              : '${response!.latencyMs!.toStringAsFixed(0)} ms',
        ),
      ],
    ],
  );
}

class _Ranking extends StatelessWidget {
  const _Ranking({this.response});
  final RecommendationResponse? response;

  @override
  Widget build(BuildContext context) {
    if (response == null) {
      return const EmptyState(
        title: 'No controlled comparison',
        message: 'Run a context-aware recommendation before opening ranking diagnostics.',
      );
    }
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const _Notice(),
        const SizedBox(height: 16),
        Text(
          response!.configuration.label,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 12),
        ...response!.candidates.map(
          (candidate) => Card(
            margin: const EdgeInsets.only(bottom: 10),
            child: Padding(
              padding: const EdgeInsets.all(15),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    candidate.name,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _Rank(
                          label: 'Semantic',
                          value: candidate.semanticRank,
                        ),
                      ),
                      const Icon(
                        Icons.arrow_forward_rounded,
                        color: AppColors.textSecondary,
                      ),
                      Expanded(
                        child: _Rank(
                          label: 'Experimental',
                          value: candidate.experimentalRank,
                        ),
                      ),
                      Text(
                        '${candidate.rankMovement > 0 ? '+' : ''}${candidate.rankMovement}',
                        style: const TextStyle(
                          color: AppColors.primary,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Available dimensions: ${candidate.evidence.values.where((item) => item.isAvailable).length} · Missing: ${candidate.missingDimensions.join(', ').isEmpty ? 'none reported' : candidate.missingDimensions.join(', ')}',
                    style: const TextStyle(
                      fontSize: 10,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const Text(
          'Rank movement alone does not demonstrate improved recommendation accuracy.',
          style: TextStyle(color: AppColors.textSecondary, fontSize: 11),
        ),
      ],
    );
  }
}

class _Context extends StatelessWidget {
  const _Context({this.response});
  final RecommendationResponse? response;
  @override
  Widget build(BuildContext context) {
    final candidate = response?.candidates.firstOrNull;
    if (candidate == null) {
      return const EmptyState(
        title: 'No context evidence',
        message: 'Run a recommendation to inspect backend-returned evidence.',
      );
    }
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(
          candidate.name,
          style: Theme.of(context).textTheme.titleLarge
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 14),
        ...[
          'weather',
          'time_of_day',
          'holiday_event',
          'historical_seasonality',
        ].map((key) {
          final item = candidate.evidence[key];
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    key.replaceAll('_', ' ').toUpperCase(),
                    style: const TextStyle(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w800,
                      fontSize: 11,
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    item?.isAvailable == true
                        ? 'Score ${item!.score?.toStringAsFixed(3) ?? 'not returned'}'
                        : 'Evidence unavailable for this attraction.',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    item?.explanation ?? 'The backend returned no evidence object for this dimension.',
                    style: const TextStyle(height: 1.45),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    'Source: ${item?.source ?? 'Not available'}',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 10,
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }
}

class _Pipeline extends StatelessWidget {
  const _Pipeline();
  static const stages = [
    (
      'User travel request',
      'Validated request fields and explicit Asia/Colombo travel time.',
    ),
    (
      'LangGraph intent processing',
      'Deterministic or opt-in structured extraction; research endpoint only.',
    ),
    ('BGE query embedding', 'BAAI/bge-large-en-v1.5 semantic representation.'),
    (
      'Qdrant semantic search',
      'Candidate retrieval; similarity is not a calibrated probability.',
    ),
    (
      'PostgreSQL hydration',
      'Verified attraction metadata, categories and activities.',
    ),
    (
      'Four context adapters',
      'Weather, time of day, holiday/event and historical seasonality.',
    ),
    (
      'Unified context evidence',
      'Availability, provenance, limitations and nullable scores.',
    ),
    (
      'R0–R3 experimental reranker',
      'Research comparison only; production order remains unchanged.',
    ),
    (
      'Evidence-based explanation',
      'Positive factors, missing dimensions and limitations.',
    ),
    (
      'Ranked attraction results',
      'Experimental output clearly labeled as unvalidated.',
    ),
  ];
  @override
  Widget build(BuildContext context) => ListView.separated(
    padding: const EdgeInsets.all(20),
    itemCount: stages.length,
    separatorBuilder: (_, _) => const Center(
      child: Icon(Icons.arrow_downward_rounded, color: AppColors.accent),
    ),
    itemBuilder: (context, index) {
      final stage = stages[index];
      return ExpansionTile(
        collapsedBackgroundColor: AppColors.surface,
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: const BorderSide(color: AppColors.divider),
        ),
        collapsedShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: const BorderSide(color: AppColors.divider),
        ),
        leading: CircleAvatar(
          backgroundColor: AppColors.primaryDark,
          foregroundColor: Colors.white,
          child: Text('${index + 1}'),
        ),
        title: Text(
          stage.$1,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Text(
              stage.$2,
              style: const TextStyle(
                color: AppColors.textSecondary,
                height: 1.45,
              ),
            ),
          ),
        ],
      );
    },
  );
}

class _Notice extends StatelessWidget {
  const _Notice();
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF3D6),
      borderRadius: BorderRadius.circular(16),
    ),
    child: const Text(
      'RESEARCH MODE · Experimental outputs are not production-validated. Protected APIs still enforce backend authorization.',
      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, height: 1.4),
    ),
  );
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: AppColors.divider),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          value,
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
        ),
      ],
    ),
  );
}

class _Rank extends StatelessWidget {
  const _Rank({required this.label, required this.value});
  final String label;
  final int value;
  @override
  Widget build(BuildContext context) => Column(
    children: [
      Text(
        '#$value',
        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
      ),
      Text(
        label,
        style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
      ),
    ],
  );
}
