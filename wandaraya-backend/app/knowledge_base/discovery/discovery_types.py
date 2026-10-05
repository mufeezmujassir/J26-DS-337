
PRIMARY_DISCOVERY_TYPES = [

    # General tourism
    "tourist_attraction",

    # Culture / Heritage / Archaeology
    "cultural_landmark",
    "historical_place",
    "historical_landmark",
    "monument",
    "museum",

    # Nature / Scenic
    "national_park",
    "nature_preserve",
    "scenic_spot",
    "mountain_peak",
    "beach",

    # Adventure
    "hiking_area",

    # Wildlife
    "wildlife_park",
    "wildlife_refuge",

    # Religious / Spiritual
    "buddhist_temple",
    "hindu_temple",
    "church",
    "mosque",

    # Nature / Recreation
    "botanical_garden",
]




SECONDARY_DISCOVERY_TYPES = [

    # Nature
    "park",
    "city_park",
    "garden",
    "observation_deck",
    "lake",
    "river",
    "island",
    "woods",

    # Marine
    "marina",
    "fishing_pier",

    # Adventure
    "adventure_sports_center",
    "cycling_park",
    "off_roading_area",
    "campground",
    "picnic_ground",

    # Wildlife / Family
    "aquarium",
    "zoo",

    # Culture
    "cultural_center",
    "art_gallery",
    "art_museum",
    "history_museum",

    # Visitor information
    "visitor_center",
    "tourist_information_center",
]



EXPERIENCE_DISCOVERY_TYPES = [

    # Agriculture / Plantation
    "farm",
    "farmstay",
    "tea_house",
    "tea_store",

    # Wellness
    "wellness_center",
    "spa",
    "yoga_studio",

    # Shopping / Local Experience
    "market",
    "farmers_market",
    "flea_market",
    "gift_shop",

    # Recreation / Entertainment
    "amusement_park",
    "water_park",
    "event_venue",
    "amphitheatre",
    "performing_arts_theater",
    "live_music_venue",

    # Education
    "planetarium",
]



SUPPORTING_DISCOVERY_TYPES = [
    "bridge",
    "train_station",
    "ferry_terminal",
]




FOOD_EXPERIENCE_TYPES = [
    "sri_lankan_restaurant",
]




ALL_DISCOVERY_TYPES = list(
    dict.fromkeys(
        PRIMARY_DISCOVERY_TYPES
        + SECONDARY_DISCOVERY_TYPES
        + EXPERIENCE_DISCOVERY_TYPES
    )
)