import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/travel_group.dart';

final groupPlannerProvider =
    NotifierProvider<GroupPlannerController, List<TravelGroup>>(
      GroupPlannerController.new,
    );

class GroupPlannerController extends Notifier<List<TravelGroup>> {
  @override
  List<TravelGroup> build() => [
    TravelGroup(
      id: 'ella-squad',
      name: 'Ella Squad',
      location: 'Ella, Sri Lanka',
      createdAt: DateTime(2026, 8, 20),
      members: const [
        GroupMember(
          name: 'Kasun',
          initial: 'K',
          mood: 'Excited',
          moodColor: Color(0xFF20BF6B),
          moodScore: .64,
        ),
        GroupMember(
          name: 'Nimal',
          initial: 'N',
          mood: 'Tired',
          moodColor: Color(0xFFFF6B26),
          moodScore: .86,
        ),
        GroupMember(
          name: 'You',
          initial: 'Y',
          mood: 'Happy',
          moodColor: Color(0xFF3F82F7),
          moodScore: .70,
        ),
        GroupMember(
          name: 'Tharushi',
          initial: 'T',
          mood: 'Tired',
          moodColor: Color(0xFFFF6B26),
          moodScore: .80,
        ),
      ],
    ),
    TravelGroup(
      id: 'galle-beach-crew',
      name: 'Galle Beach Crew',
      location: 'Galle, Sri Lanka',
      createdAt: DateTime(2026, 8, 22),
      emoji: '🌊',
      members: const [
        GroupMember(
          name: 'Kasun',
          initial: 'K',
          mood: 'Happy',
          moodColor: Color(0xFF20BF6B),
          moodScore: .82,
        ),
        GroupMember(
          name: 'Dinithi',
          initial: 'D',
          mood: 'Calm',
          moodColor: Color(0xFF3F82F7),
          moodScore: .72,
        ),
      ],
    ),
  ];

  TravelGroup addGroup({required String name, required String location}) {
    final group = TravelGroup(
      id: '${name.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-')}-${DateTime.now().millisecondsSinceEpoch}',
      name: name,
      location: location,
      createdAt: DateTime.now(),
      members: const [
        GroupMember(
          name: 'You',
          initial: 'Y',
          mood: 'Ready',
          moodColor: Color(0xFF20BF6B),
          moodScore: .85,
        ),
      ],
    );
    state = [...state, group];
    return group;
  }
}

final itineraryProvider = Provider<List<ItineraryDay>>((ref) {
  return const [
    ItineraryDay(
      day: 1,
      location: 'Ella',
      date: 'Aug 26, 2026 (Wed)',
      weather: 'Partly sunny, 24°C',
      activities: [
        ItineraryActivity(
          time: '8:00 AM',
          title: 'Arrive Ella',
          description: 'Check in at Ella Eco Lodge. Drop bags and freshen up.',
          icon: Icons.location_on_outlined,
        ),
        ItineraryActivity(
          time: '10:30 AM',
          title: "Little Adam's Peak",
          description: 'A gentle 3 km trail with panoramic Ella Gap views and ideal morning light.',
          icon: Icons.landscape_outlined,
          cost: 'LKR 200',
        ),
        ItineraryActivity(
          time: '1:00 PM',
          title: 'Lunch at Café Chill',
          description: 'Local favourites with vegetarian options.',
          icon: Icons.restaurant_outlined,
          cost: 'LKR 1,800',
        ),
      ],
    ),
    ItineraryDay(
      day: 2,
      location: 'Ella & Demodara',
      date: 'Aug 27, 2026 (Thu)',
      weather: 'Clear, 23°C',
      activities: [
        ItineraryActivity(
          time: '7:30 AM',
          title: 'Nine Arch Bridge',
          description:
              'Catch the morning train crossing and explore the forest trail.',
          icon: Icons.train_outlined,
        ),
        ItineraryActivity(
          time: '11:30 AM',
          title: 'Tea estate experience',
          description: 'Guided factory visit and tea tasting in the highlands.',
          icon: Icons.eco_outlined,
          cost: 'LKR 2,500',
        ),
      ],
    ),
    ItineraryDay(
      day: 3,
      location: 'Ravana Falls',
      date: 'Aug 28, 2026 (Fri)',
      weather: 'Cloudy, 22°C',
      activities: [
        ItineraryActivity(
          time: '9:00 AM',
          title: 'Ravana Falls',
          description: 'A relaxed waterfall stop before the return journey.',
          icon: Icons.water_drop_outlined,
        ),
      ],
    ),
  ];
});
