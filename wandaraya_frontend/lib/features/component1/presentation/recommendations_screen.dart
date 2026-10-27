import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/async_states.dart';
import '../../../shared/widgets/app_bottom_navigation.dart';
import '../application/component1_providers.dart';
import '../domain/recommendation_models.dart';

class RecommendationsScreen extends ConsumerWidget {
  const RecommendationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(recommendationSessionProvider);
    final response = session.response;
    if (response == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Recommendations')),
        bottomNavigationBar: const AppBottomNavigation(selectedIndex: 2),
        body: Center(
          child: EmptyState(
            title: 'No recommendation session',
            message: 'Complete the smart travel form to request real context-aware results.',
          ),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => context.push('/preferences'),
          icon: const Icon(Icons.tune_rounded),
          label: const Text('Set preferences'),
        ),
      );
    }

    return Scaffold(
      bottomNavigationBar: const AppBottomNavigation(selectedIndex: 2),
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(child: _ResultsHeader(response: response)),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 30),
            sliver: SliverList.list(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${response.candidates.length} ranked places',
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ),
                    TextButton.icon(
                      onPressed: () => context.push('/research'),
                      icon: const Icon(Icons.science_outlined, size: 18),
                      label: const Text('Research insights'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                if (response.candidates.isEmpty)
                  const EmptyState(
                    title: 'No results returned',
                    message: 'The backend completed the request but returned no ranked attractions.',
                  )
                else
                  ...response.candidates.map(
                    (candidate) => _RecommendationCard(
                      candidate: candidate,
                      onTap: () => context.push(
                        '/attractions/${candidate.attractionId}',
                      ),
                    ),
                  ),
                if (response.limitations.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  ExpansionTile(
                    title: const Text(
                      'Research limitations',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                    children: response.limitations
                        .map(
                          (item) => ListTile(
                            leading: const Icon(Icons.info_outline_rounded),
                            title: Text(item),
                          ),
                        )
                        .toList(),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ResultsHeader extends StatelessWidget {
  const _ResultsHeader({required this.response});
  final RecommendationResponse response;

  @override
  Widget build(BuildContext context) => Container(
    padding: EdgeInsets.fromLTRB(
      20,
      MediaQuery.paddingOf(context).top + 20,
      20,
      24,
    ),
    decoration: const BoxDecoration(
      color: AppColors.primaryDark,
      borderRadius: BorderRadius.vertical(bottom: Radius.circular(30)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            IconButton(
              onPressed: () =>
                  context.canPop() ? context.pop() : context.go('/discover'),
              color: Colors.white,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            const SizedBox(width: 4),
            const Expanded(
              child: Text(
                'Recommended for you',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          response.query,
          style: const TextStyle(color: Colors.white, height: 1.4),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 7,
          children: [
            _HeaderPill(
              label: DateFormat('dd MMM yyyy, HH:mm')
                  .format(response.travelDateTime),
            ),
            _HeaderPill(label: response.configuration.label),
            const _HeaderPill(label: 'Experimental · not production-validated'),
          ],
        ),
      ],
    ),
  );
}

class _HeaderPill extends StatelessWidget {
  const _HeaderPill({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .12),
      borderRadius: BorderRadius.circular(99),
    ),
    child: Text(
      label,
      style: const TextStyle(color: Colors.white70, fontSize: 10),
    ),
  );
}

class _RecommendationCard extends StatelessWidget {
  const _RecommendationCard({required this.candidate, required this.onTap});
  final RankedAttraction candidate;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 14),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.primaryDeep,
                  child: Text(
                    '#${candidate.experimentalRank}',
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Text(
                    candidate.name,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                const Icon(Icons.chevron_right_rounded),
              ],
            ),
            const SizedBox(height: 15),
            if (candidate.description?.isNotEmpty ?? false) ...[
              Text(
                candidate.description!,
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  height: 1.45,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 12),
            ],
            if (candidate.city != null || candidate.districtName != null) ...[
              Row(
                children: [
                  const Icon(Icons.location_on_outlined, size: 16),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(
                      [candidate.city, candidate.districtName]
                          .whereType<String>()
                          .where((value) => value.isNotEmpty)
                          .join(', '),
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
            ],
            if (candidate.rating != null) ...[
              Text(
                'Visitor rating: ${candidate.rating!.toStringAsFixed(1)}/5${candidate.reviewCount == null ? '' : ' · ${candidate.reviewCount} reviews'}',
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
            ],
            if (candidate.categories.isNotEmpty ||
                candidate.activities.isNotEmpty) ...[
              Wrap(
                spacing: 7,
                runSpacing: 7,
                children: [
                  ...candidate.categories.map(
                    (value) => Chip(
                      label: Text(value),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                  ...candidate.activities.map(
                    (value) => Chip(
                      avatar: const Icon(
                        Icons.local_activity_outlined,
                        size: 15,
                      ),
                      label: Text(value),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
            ],
            _ScoreLine(
              label: 'Semantic score',
              value: candidate.semanticScore,
              note: 'retrieval score',
            ),
            const SizedBox(height: 9),
            _ScoreLine(
              label: 'Experimental final score',
              value: candidate.finalScore,
              note: 'not a probability',
            ),
            const SizedBox(height: 13),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: candidate.evidence.entries.map((entry) {
                final available = entry.value.isAvailable;
                return Chip(
                  avatar: Icon(
                    available ? Icons.check_circle_outline : Icons.help_outline,
                    size: 15,
                  ),
                  label: Text(
                    '${_friendly(entry.key)} · ${available ? 'Available' : 'Unavailable'}',
                  ),
                  visualDensity: VisualDensity.compact,
                );
              }).toList(),
            ),
            const SizedBox(height: 12),
            Text(
              candidate.explanation,
              style: const TextStyle(
                color: AppColors.textSecondary,
                height: 1.45,
                fontSize: 12,
              ),
            ),
            if (candidate.rankMovement != 0) ...[
              const SizedBox(height: 10),
              Text(
                'Rank movement: ${candidate.rankMovement > 0 ? '+' : ''}${candidate.rankMovement}',
                style: const TextStyle(
                  color: AppColors.primary,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ],
        ),
      ),
    ),
  );
}

class _ScoreLine extends StatelessWidget {
  const _ScoreLine({
    required this.label,
    required this.value,
    required this.note,
  });
  final String label;
  final double value;
  final String note;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Row(
        children: [
          Expanded(child: Text(label, style: const TextStyle(fontSize: 11))),
          Text(
            '${value.toStringAsFixed(3)} · $note',
            style: const TextStyle(
              fontSize: 10,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
      const SizedBox(height: 5),
      LinearProgressIndicator(
        value: value.clamp(0, 1),
        minHeight: 6,
        borderRadius: BorderRadius.circular(99),
        backgroundColor: AppColors.surfaceMuted,
      ),
    ],
  );
}

String _friendly(String key) => key
    .split('_')
    .map((word) => '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');
