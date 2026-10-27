import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../shared/widgets/wandaraya_brand.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  late final AnimationController _orbitController;
  late final AnimationController _entranceController;
  late final Animation<double> _fade;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _orbitController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat();
    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..forward();
    _fade = CurvedAnimation(parent: _entranceController, curve: Curves.easeOut);
    _scale = Tween<double>(begin: 0.88, end: 1).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOutBack),
    );
    _continueToApp();
  }

  void _continueToApp() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.go('/discover');
    });
  }

  @override
  void dispose() {
    _orbitController.dispose();
    _entranceController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Center(
          child: FadeTransition(
            opacity: _fade,
            child: ScaleTransition(
              scale: _scale,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 330,
                    height: 138,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        const WandarayaBrand(),
                        Positioned(
                          left: 117,
                          top: -12,
                          child: RotationTransition(
                            turns: _orbitController,
                            child: CustomPaint(
                              size: const Size.square(96),
                              painter: _OrbitDotsPainter(),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Explore Sri Lanka, intelligently.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: AppColors.textSecondary,
                      letterSpacing: 0.2,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OrbitDotsPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    const radii = [4.5, 3.5, 2.7];
    for (var index = 0; index < radii.length; index++) {
      final angle = (math.pi * 2 / radii.length) * index;
      final position = Offset(
        center.dx + math.cos(angle) * 43,
        center.dy + math.sin(angle) * 43,
      );
      canvas.drawCircle(
        position,
        radii[index],
        Paint()..color = AppColors.accent.withValues(alpha: 1 - index * 0.2),
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
