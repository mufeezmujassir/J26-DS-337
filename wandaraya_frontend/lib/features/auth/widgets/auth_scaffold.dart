import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/widgets/wandaraya_brand.dart';

class AuthScaffold extends StatelessWidget {
  const AuthScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.child,
    this.onBack,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.primaryDark,
      body: Stack(
        children: [
          Positioned.fill(
            bottom: null,
            child: SizedBox(
              height: 250,
              child: CustomPaint(
                painter: _TravelPatternPainter(),
                child: SafeArea(
                  bottom: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            if (onBack != null)
                              IconButton.filled(
                                onPressed: onBack,
                                style: IconButton.styleFrom(
                                  backgroundColor: Colors.white.withValues(
                                    alpha: 0.13,
                                  ),
                                  foregroundColor: Colors.white,
                                ),
                                icon: const Icon(Icons.arrow_back_rounded),
                              )
                            else
                              const SizedBox(width: 48),
                            const Spacer(),
                            const WandarayaBrand(
                              compact: true,
                              foregroundColor: Colors.white,
                              markColor: AppColors.accent,
                              iconColor: AppColors.primaryDeep,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(top: 158),
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: 1),
                duration: const Duration(milliseconds: 650),
                curve: Curves.easeOutCubic,
                builder: (context, value, content) => Transform.translate(
                  offset: Offset(0, 42 * (1 - value)),
                  child: Opacity(opacity: value, child: content),
                ),
                child: Container(
                  constraints: BoxConstraints(
                    minHeight: MediaQuery.sizeOf(context).height - 158,
                  ),
                  padding: EdgeInsets.fromLTRB(
                    24,
                    30,
                    24,
                    28 + MediaQuery.paddingOf(context).bottom,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.background,
                    borderRadius: BorderRadius.vertical(
                      top: Radius.circular(34),
                    ),
                  ),
                  child: Center(
                    heightFactor: 1,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 480),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            title,
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.headlineSmall
                                ?.copyWith(
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.5,
                                ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            subtitle,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: AppColors.textSecondary,
                              height: 1.45,
                            ),
                          ),
                          const SizedBox(height: 28),
                          child,
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AuthDivider extends StatelessWidget {
  const AuthDivider({super.key, this.label = 'or continue with'});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Expanded(child: Divider(color: AppColors.divider)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
            ),
          ),
        ),
        const Expanded(child: Divider(color: AppColors.divider)),
      ],
    );
  }
}

class SocialAuthButton extends StatelessWidget {
  const SocialAuthButton({
    super.key,
    required this.label,
    required this.leading,
    required this.onPressed,
  });

  final String label;
  final Widget leading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 54,
      child: OutlinedButton.icon(
        onPressed: onPressed,
        icon: leading,
        label: Text(label),
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textPrimary,
          backgroundColor: AppColors.surface,
          side: const BorderSide(color: AppColors.divider),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
    );
  }
}

class _TravelPatternPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()
      ..color = AppColors.accent.withValues(alpha: 0.13)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final dot = Paint()..color = AppColors.accent.withValues(alpha: 0.22);
    final path = Path()
      ..moveTo(-20, size.height * 0.75)
      ..cubicTo(
        size.width * 0.2,
        size.height * 0.38,
        size.width * 0.48,
        size.height * 0.92,
        size.width * 0.72,
        size.height * 0.42,
      )
      ..quadraticBezierTo(
        size.width * 0.9,
        size.height * 0.12,
        size.width + 30,
        size.height * 0.5,
      );
    canvas.drawPath(path, line);
    canvas.drawCircle(Offset(size.width * 0.17, size.height * 0.58), 5, dot);
    canvas.drawCircle(Offset(size.width * 0.72, size.height * 0.42), 7, dot);
    canvas.drawCircle(Offset(size.width * 0.9, size.height * 0.26), 3.5, dot);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
