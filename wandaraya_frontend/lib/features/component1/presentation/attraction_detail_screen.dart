import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/async_states.dart';
import '../application/component1_providers.dart';
import '../domain/component1_models.dart';
import '../domain/recommendation_models.dart';

class AttractionDetailScreen extends ConsumerWidget {
  const AttractionDetailScreen({super.key, required this.attractionId});
  final int attractionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(attractionDetailProvider(attractionId));
    final session = ref.watch(recommendationSessionProvider);
    final ranked = session.response?.candidates
        .where((item) => item.attractionId == attractionId)
        .firstOrNull;
    final saved = ref.watch(savedPlaceIdsProvider).contains(attractionId);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Place details'),
        actions: [
          IconButton(
            tooltip: saved ? 'Remove from saved places' : 'Save place',
            onPressed: () =>
                ref.read(savedPlaceIdsProvider.notifier).toggle(attractionId),
            icon: Icon(
              saved ? Icons.bookmark_rounded : Icons.bookmark_border_rounded,
            ),
          ),
        ],
      ),
      body: detail.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(20),
          child: LoadingCards(count: 4),
        ),
        error: (error, _) => AppErrorState(
          message: error is ApiException
              ? error.message
              : 'Unable to load this attraction.',
          onRetry: () => ref.invalidate(attractionDetailProvider(attractionId)),
        ),
        data: (value) => _DetailsBody(detail: value, ranked: ranked),
      ),
    );
  }
}

class _DetailsBody extends StatelessWidget {
  const _DetailsBody({required this.detail, this.ranked});
  final AttractionDetail detail;
  final RankedAttraction? ranked;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
    children: [
      Container(
        height: 190,
        decoration: BoxDecoration(
          color: AppColors.primaryDark,
          borderRadius: BorderRadius.circular(24),
        ),
        child: const Center(
          child: Icon(Icons.landscape_rounded, color: Colors.white, size: 70),
        ),
      ),
      const SizedBox(height: 20),
      Text(
        detail.name,
        style: const TextStyle(
          fontSize: 27,
          fontWeight: FontWeight.w800,
          letterSpacing: -.5,
        ),
      ),
      const SizedBox(height: 7),
      Text(
        [
          detail.district ?? detail.city,
          ...detail.categories,
        ].whereType<String>().join(' · '),
        style: const TextStyle(color: AppColors.textSecondary),
      ),
      const SizedBox(height: 20),
      Text(
        'About this place',
        style: Theme.of(context).textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 8),
      Text(
        detail.description ??
            detail.enrichments
                .map((item) => item.description)
                .whereType<String>()
                .firstOrNull ??
            'No verified description is available.',
        style: const TextStyle(height: 1.55),
      ),
      if (ranked != null) ...[
        const SizedBox(height: 24),
        _SectionCard(
          icon: Icons.auto_awesome_rounded,
          title: 'Why this place?',
          child: Text(ranked!.explanation, style: const TextStyle(height: 1.5)),
        ),
        const SizedBox(height: 16),
        Text(
          'Context intelligence',
          style: Theme.of(context).textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 10),
        ...[
          'weather',
          'time_of_day',
          'holiday_event',
          'historical_seasonality',
        ].map(
          (dimension) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _EvidenceCard(
              dimension: dimension,
              evidence: ranked!.evidence[dimension],
            ),
          ),
        ),
      ],
      const SizedBox(height: 22),
      Text(
        'Practical information',
        style: Theme.of(context).textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 10),
      _InfoRow(
        icon: Icons.location_on_outlined,
        label: 'Address',
        value: detail.address ?? 'Not available',
      ),
      _InfoRow(
        icon: Icons.map_outlined,
        label: 'Coordinates',
        value: detail.latitude == null || detail.longitude == null
            ? 'Not available'
            : '${detail.latitude!.toStringAsFixed(5)}, ${detail.longitude!.toStringAsFixed(5)}',
      ),
      _InfoRow(
        icon: Icons.language_rounded,
        label: 'Website',
        value: detail.websiteUrl ?? 'Not available',
      ),
      if (detail.enrichments.isNotEmpty) ...[
        const SizedBox(height: 18),
        Text(
          'Sources',
          style: Theme.of(context).textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        ...detail.enrichments.map(
          (item) => ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.verified_outlined),
            title: Text(item.title ?? item.source ?? 'Verified enrichment'),
            subtitle: Text(item.source ?? 'Source not named'),
          ),
        ),
      ],
    ],
  );
}

class _EvidenceCard extends StatelessWidget {
  const _EvidenceCard({required this.dimension, this.evidence});
  final String dimension;
  final ContextEvidence? evidence;

  @override
  Widget build(BuildContext context) {
    final available = evidence?.isAvailable ?? false;
    return ExpansionTile(
      tilePadding: const EdgeInsets.symmetric(horizontal: 15),
      collapsedBackgroundColor: AppColors.surface,
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.divider),
      ),
      collapsedShape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.divider),
      ),
      leading: Icon(
        _icon(dimension),
        color: available ? AppColors.primary : AppColors.textSecondary,
      ),
      title: Text(
        _title(dimension),
        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
      ),
      subtitle: Text(
        available
            ? 'Evidence available${evidence?.score == null ? '' : ' · Score ${evidence!.score!.toStringAsFixed(3)}'}'
            : 'Evidence unavailable for this attraction.',
        style: const TextStyle(fontSize: 11),
      ),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                evidence?.explanation ?? 'No evidence record was returned.',
                style: const TextStyle(height: 1.45),
              ),
              const SizedBox(height: 8),
              Text(
                'Source: ${evidence?.source ?? 'Not available'}',
                style: const TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 11,
                ),
              ),
              if (evidence?.limitations.isNotEmpty ?? false)
                ...evidence!.limitations.map(
                  (item) => Text(
                    '• $item',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 11,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  IconData _icon(String value) => switch (value) {
    'weather' => Icons.cloud_outlined,
    'time_of_day' => Icons.schedule_rounded,
    'holiday_event' => Icons.event_outlined,
    _ => Icons.eco_outlined,
  };
  String _title(String value) => switch (value) {
    'weather' => 'Weather',
    'time_of_day' => 'Time of day',
    'holiday_event' => 'Holiday, Poya and events',
    _ => 'Historical seasonality',
  };
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.icon,
    required this.title,
    required this.child,
  });
  final IconData icon;
  final String title;
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(17),
    decoration: BoxDecoration(
      color: AppColors.surfaceMuted,
      borderRadius: BorderRadius.circular(18),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: AppColors.primary),
            const SizedBox(width: 8),
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
          ],
        ),
        const SizedBox(height: 10),
        child,
      ],
    ),
  );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });
  final IconData icon;
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: EdgeInsets.zero,
    leading: Icon(icon, color: AppColors.primary),
    title: Text(
      label,
      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
    ),
    subtitle: Text(value),
  );
}
