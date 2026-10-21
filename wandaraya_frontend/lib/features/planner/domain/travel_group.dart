import 'package:flutter/material.dart';

class TravelGroup {
  const TravelGroup({
    required this.id,
    required this.name,
    required this.location,
    required this.members,
    required this.createdAt,
    this.emoji = '🌿',
  });

  final String id;
  final String name;
  final String location;
  final List<GroupMember> members;
  final DateTime createdAt;
  final String emoji;
}

class GroupMember {
  const GroupMember({
    required this.name,
    required this.initial,
    required this.mood,
    required this.moodColor,
    required this.moodScore,
  });

  final String name;
  final String initial;
  final String mood;
  final Color moodColor;
  final double moodScore;
}

class ChatMessage {
  const ChatMessage({
    required this.sender,
    required this.message,
    required this.time,
    this.isCurrentUser = false,
    this.translation,
    this.tag,
  });

  final String sender;
  final String message;
  final String time;
  final bool isCurrentUser;
  final String? translation;
  final String? tag;
}

class ItineraryActivity {
  const ItineraryActivity({
    required this.time,
    required this.title,
    required this.description,
    required this.icon,
    this.cost,
  });

  final String time;
  final String title;
  final String description;
  final IconData icon;
  final String? cost;
}

class ItineraryDay {
  const ItineraryDay({
    required this.day,
    required this.location,
    required this.date,
    required this.weather,
    required this.activities,
  });

  final int day;
  final String location;
  final String date;
  final String weather;
  final List<ItineraryActivity> activities;
}
