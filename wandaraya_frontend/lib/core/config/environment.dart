import 'package:flutter/foundation.dart';

class Environment {
  Environment._();

  static const _definedBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const researchOwner = String.fromEnvironment(
    'RESEARCH_OWNER',
    defaultValue: 'wandaraya-local-researcher',
  );

  static String get apiBaseUrl {
    if (_definedBaseUrl.isNotEmpty) return _definedBaseUrl;
    if (kIsWeb) return 'http://localhost:8000';
    return defaultTargetPlatform == TargetPlatform.android
        ? 'http://10.0.2.2:8000'
        : 'http://localhost:8000';
  }
}
