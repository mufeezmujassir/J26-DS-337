class AttractionSummary {
  const AttractionSummary({
    required this.id,
    required this.name,
    required this.categories,
    required this.activities,
    this.districtId,
    this.district,
    this.city,
    this.latitude,
    this.longitude,
    this.rating,
    this.semanticScore,
  });

  factory AttractionSummary.fromJson(Map<String, dynamic> json) =>
      AttractionSummary(
        id: json['id'] as int,
        name: json['name'] as String,
        districtId: json['district_id'] as int?,
        district: json['district'] as String?,
        city: json['city'] as String?,
        latitude: (json['latitude'] as num?)?.toDouble(),
        longitude: (json['longitude'] as num?)?.toDouble(),
        rating: (json['rating'] as num?)?.toDouble(),
        categories: _strings(json['categories']),
        activities: _strings(json['activities']),
        semanticScore: (json['semantic_score'] as num?)?.toDouble(),
      );

  final int id;
  final String name;
  final int? districtId;
  final String? district;
  final String? city;
  final double? latitude;
  final double? longitude;
  final double? rating;
  final List<String> categories;
  final List<String> activities;
  final double? semanticScore;
}

class AttractionDetail extends AttractionSummary {
  const AttractionDetail({
    required super.id,
    required super.name,
    required super.categories,
    required super.activities,
    required this.isActive,
    super.districtId,
    super.district,
    super.city,
    super.latitude,
    super.longitude,
    super.rating,
    this.address,
    this.websiteUrl,
    this.description,
    this.updatedAt,
    this.enrichments = const [],
  });

  factory AttractionDetail.fromJson(Map<String, dynamic> json) {
    final summary = AttractionSummary.fromJson(json);
    return AttractionDetail(
      id: summary.id,
      name: summary.name,
      categories: summary.categories,
      activities: summary.activities,
      districtId: summary.districtId,
      district: summary.district,
      city: summary.city,
      latitude: summary.latitude,
      longitude: summary.longitude,
      rating: summary.rating,
      isActive: json['is_active'] as bool? ?? false,
      address: json['address'] as String?,
      websiteUrl: json['website_url'] as String?,
      description: json['description'] as String?,
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? ''),
      enrichments: (json['enrichments'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                AttractionEnrichment.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }

  final bool isActive;
  final String? address;
  final String? websiteUrl;
  final String? description;
  final DateTime? updatedAt;
  final List<AttractionEnrichment> enrichments;
}

class AttractionEnrichment {
  const AttractionEnrichment({
    this.title,
    this.description,
    this.source,
    this.sourceUrl,
  });

  factory AttractionEnrichment.fromJson(Map<String, dynamic> json) =>
      AttractionEnrichment(
        title: json['title'] as String?,
        description: json['description'] as String?,
        source: json['source'] as String?,
        sourceUrl: json['source_url'] as String?,
      );

  final String? title;
  final String? description;
  final String? source;
  final String? sourceUrl;
}

class TaxonomyItem {
  const TaxonomyItem({
    required this.id,
    required this.name,
    this.subtitle,
    this.count = 0,
  });

  factory TaxonomyItem.category(Map<String, dynamic> json) => TaxonomyItem(
    id: json['id'] as int,
    name: json['name'] as String,
    subtitle: json['description'] as String?,
    count: json['active_attraction_count'] as int? ?? 0,
  );

  factory TaxonomyItem.district(Map<String, dynamic> json) => TaxonomyItem(
    id: json['id'] as int,
    name: json['name'] as String,
    subtitle: json['province'] as String?,
    count: json['active_attraction_count'] as int? ?? 0,
  );

  final int id;
  final String name;
  final String? subtitle;
  final int count;
}

class KnowledgeBaseStatus {
  const KnowledgeBaseStatus({
    required this.activeAttractions,
    required this.mappedAttractions,
    required this.categories,
    required this.activities,
    required this.embeddingModel,
    required this.embeddingDimension,
    required this.qdrantCollectionExists,
    this.qdrantPoints,
  });

  factory KnowledgeBaseStatus.fromJson(Map<String, dynamic> json) =>
      KnowledgeBaseStatus(
        activeAttractions: json['active_attractions'] as int,
        mappedAttractions: json['mapped_attractions'] as int,
        categories: json['categories'] as int,
        activities: json['activities'] as int,
        embeddingModel: json['embedding_model'] as String,
        embeddingDimension: json['embedding_dimension'] as int,
        qdrantCollectionExists: json['qdrant_collection_exists'] as bool,
        qdrantPoints: json['qdrant_points'] as int?,
      );

  final int activeAttractions;
  final int mappedAttractions;
  final int categories;
  final int activities;
  final String embeddingModel;
  final int embeddingDimension;
  final bool qdrantCollectionExists;
  final int? qdrantPoints;
}

List<String> _strings(Object? value) =>
    (value as List? ?? const []).whereType<String>().toList(growable: false);
