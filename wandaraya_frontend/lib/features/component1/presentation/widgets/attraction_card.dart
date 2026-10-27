import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../domain/component1_models.dart';

class AttractionCard extends StatelessWidget {
  const AttractionCard({
    super.key,
    required this.attraction,
    required this.onTap,
    this.rank,
    this.trailing,
  });

  final AttractionSummary attraction;
  final VoidCallback onTap;
  final int? rank;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final category = attraction.categories.isEmpty
        ? 'Attraction'
        : attraction.categories.first;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            children: [
              Container(
                width: 72,
                height: 82,
                decoration: BoxDecoration(
                  color: AppColors.primaryDark,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Stack(
                  children: [
                    const Center(
                      child: Icon(
                        Icons.landscape_rounded,
                        color: Colors.white,
                        size: 32,
                      ),
                    ),
                    if (rank != null)
                      Positioned(
                        left: 7,
                        top: 7,
                        child: CircleAvatar(
                          radius: 12,
                          backgroundColor: AppColors.accent,
                          foregroundColor: AppColors.primaryDeep,
                          child: Text(
                            '$rank',
                            style: const TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      attraction.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      [
                        attraction.district ?? attraction.city,
                        category,
                      ].whereType<String>().join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                    if (attraction.semanticScore != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Semantic score ${attraction.semanticScore!.toStringAsFixed(3)}',
                        style: const TextStyle(
                          color: AppColors.primary,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              trailing ?? const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
      ),
    );
  }
}
