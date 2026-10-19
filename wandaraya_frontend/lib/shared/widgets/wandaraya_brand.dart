import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

class WandarayaBrand extends StatelessWidget {
  const WandarayaBrand({
    super.key,
    this.compact = false,
    this.foregroundColor = AppColors.primary,
    this.markColor,
    this.iconColor = Colors.white,
  });

  final bool compact;
  final Color foregroundColor;
  final Color? markColor;
  final Color iconColor;

  @override
  Widget build(BuildContext context) {
    final markSize = compact ? 42.0 : 72.0;
    final mark = Container(
      width: markSize,
      height: markSize,
      decoration: BoxDecoration(
        color: markColor ?? foregroundColor,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: foregroundColor.withValues(alpha: 0.22),
            blurRadius: compact ? 12 : 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(
            Icons.explore_rounded,
            size: compact ? 28 : 46,
            color: iconColor,
          ),
          Positioned(
            right: compact ? 3 : 6,
            top: compact ? 3 : 6,
            child: Container(
              width: compact ? 9 : 13,
              height: compact ? 9 : 13,
              decoration: const BoxDecoration(
                color: AppColors.accent,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ],
      ),
    );
    final wordmark = Text(
      'WANDARAYA',
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
        color: foregroundColor,
        fontSize: compact ? 19 : 28,
        fontWeight: FontWeight.w800,
        letterSpacing: compact ? 1.8 : 3.2,
      ),
    );

    if (compact) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [mark, const SizedBox(width: 12), wordmark],
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [mark, const SizedBox(height: 16), wordmark],
    );
  }
}
