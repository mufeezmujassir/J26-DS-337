import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  static const _pages = [
    _OnboardingPageData(
      image: 'assets/images/onboarding_sigiriya.png',
      eyebrow: 'DISCOVER THE ISLAND',
      title: 'Sri Lanka,\nmade personal.',
      description: 'Find remarkable places matched to your interests, pace, and travel style.',
    ),
    _OnboardingPageData(
      image: 'assets/images/onboarding_tea_country.png',
      eyebrow: 'PLAN WITH CONFIDENCE',
      title: 'Every journey,\nbeautifully simple.',
      description: 'Build smarter routes and sustainable adventures with your AI travel companion.',
    ),
  ];

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _next() {
    if (_currentPage == _pages.length - 1) {
      context.go('/sign-in');
      return;
    }
    _pageController.nextPage(
      duration: const Duration(milliseconds: 520),
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.primaryDeep,
      body: Stack(
        children: [
          PageView.builder(
            controller: _pageController,
            itemCount: _pages.length,
            onPageChanged: (value) => setState(() => _currentPage = value),
            itemBuilder: (context, index) =>
                _OnboardingPage(key: ValueKey(index), data: _pages[index]),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: () => context.go('/sign-in'),
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.white,
                      ),
                      child: const Text(
                        'Skip',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                  const Spacer(),
                  Row(
                    children: [
                      ...List.generate(
                        _pages.length,
                        (index) => AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                          width: _currentPage == index ? 28 : 8,
                          height: 8,
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(
                            color: _currentPage == index
                                ? AppColors.accent
                                : Colors.white.withValues(alpha: 0.45),
                            borderRadius: BorderRadius.circular(99),
                          ),
                        ),
                      ),
                      const Spacer(),
                      Semantics(
                        button: true,
                        label: _currentPage == _pages.length - 1
                            ? 'Start exploring'
                            : 'Next page',
                        child: InkWell(
                          onTap: _next,
                          borderRadius: BorderRadius.circular(18),
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 300),
                            height: 58,
                            padding: const EdgeInsets.symmetric(horizontal: 22),
                            decoration: BoxDecoration(
                              color: AppColors.accent,
                              borderRadius: BorderRadius.circular(18),
                              boxShadow: const [
                                BoxShadow(
                                  color: Color(0x3D000000),
                                  blurRadius: 18,
                                  offset: Offset(0, 8),
                                ),
                              ],
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                AnimatedSwitcher(
                                  duration: const Duration(milliseconds: 250),
                                  child: Text(
                                    _currentPage == _pages.length - 1
                                        ? 'Explore now'
                                        : 'Next',
                                    key: ValueKey(_currentPage),
                                    style: const TextStyle(
                                      color: AppColors.primaryDeep,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 9),
                                const Icon(
                                  Icons.arrow_forward_rounded,
                                  color: AppColors.primaryDeep,
                                  size: 20,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OnboardingPage extends StatelessWidget {
  const _OnboardingPage({super.key, required this.data});

  final _OnboardingPageData data;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Image.asset(data.image, fit: BoxFit.cover),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Color(0x33000000),
                Color(0x05000000),
                Color(0xC90B332A),
                Color(0xF20B332A),
              ],
              stops: [0, 0.4, 0.72, 1],
            ),
          ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 112),
            child: Align(
              alignment: Alignment.bottomLeft,
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: 1),
                duration: const Duration(milliseconds: 850),
                curve: Curves.easeOutCubic,
                builder: (context, value, child) => Opacity(
                  opacity: value,
                  child: Transform.translate(
                    offset: Offset(0, 28 * (1 - value)),
                    child: child,
                  ),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.eyebrow,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      data.title,
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                        color: Colors.white,
                        height: 1.08,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -1.2,
                      ),
                    ),
                    const SizedBox(height: 16),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 390),
                      child: Text(
                        data.description,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.78),
                          height: 1.55,
                          fontSize: 15,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _OnboardingPageData {
  const _OnboardingPageData({
    required this.image,
    required this.eyebrow,
    required this.title,
    required this.description,
  });

  final String image;
  final String eyebrow;
  final String title;
  final String description;
}
