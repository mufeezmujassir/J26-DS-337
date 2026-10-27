import 'package:go_router/go_router.dart';

import '../features/auth/sign_in_screen.dart';
import '../features/auth/sign_up_screen.dart';
import '../features/component1/presentation/ai_assistant_screen.dart';
import '../features/component1/presentation/attraction_detail_screen.dart';
import '../features/component1/presentation/discover_screen.dart';
import '../features/component1/presentation/recommendations_screen.dart';
import '../features/component1/presentation/research_insights_screen.dart';
import '../features/component1/presentation/saved_places_screen.dart';
import '../features/component1/presentation/settings_screen.dart';
import '../features/component1/presentation/travel_preferences_screen.dart';
import '../features/home/home_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/planner/presentation/group_chat_screen.dart';
import '../features/planner/presentation/group_planner_screen.dart';
import '../features/planner/presentation/itinerary_screen.dart';
import '../features/splash/splash_screen.dart';

class AppRouter {
  AppRouter._();

  static final GoRouter router = GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        name: 'splash',
        builder: (_, _) => const SplashScreen(),
      ),
      GoRoute(
        path: '/discover',
        name: 'discover',
        builder: (_, _) => const DiscoverScreen(),
      ),
      GoRoute(
        path: '/preferences',
        name: 'preferences',
        builder: (_, _) => const TravelPreferencesScreen(),
      ),
      GoRoute(
        path: '/assistant',
        name: 'assistant',
        builder: (_, _) => const AiAssistantScreen(),
      ),
      GoRoute(
        path: '/recommendations',
        name: 'recommendations',
        builder: (_, _) => const RecommendationsScreen(),
      ),
      GoRoute(
        path: '/attractions/:id',
        name: 'attraction-details',
        builder: (_, state) => AttractionDetailScreen(
          attractionId: int.parse(state.pathParameters['id']!),
        ),
      ),
      GoRoute(
        path: '/saved',
        name: 'saved',
        builder: (_, _) => const SavedPlacesScreen(),
      ),
      GoRoute(
        path: '/settings',
        name: 'settings',
        builder: (_, _) => const SettingsScreen(),
      ),
      GoRoute(
        path: '/research',
        name: 'research',
        builder: (_, _) => const ResearchInsightsScreen(),
      ),
      // Retained legacy presentation routes while Component 1 migration is completed.
      GoRoute(path: '/onboarding', builder: (_, _) => const OnboardingScreen()),
      GoRoute(path: '/sign-in', builder: (_, _) => const SignInScreen()),
      GoRoute(path: '/sign-up', builder: (_, _) => const SignUpScreen()),
      GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
      GoRoute(
        path: '/groups',
        builder: (_, _) => const GroupPlannerScreen(),
        routes: [
          GoRoute(
            path: ':groupId',
            builder: (_, state) =>
                GroupChatScreen(groupId: state.pathParameters['groupId']!),
          ),
        ],
      ),
      GoRoute(path: '/itinerary', builder: (_, _) => const ItineraryScreen()),
    ],
  );
}
