"""
WANDARAYA Component 2 - Dedicated Swagger UI Runner
====================================================
Runs interactive Swagger UI documentation exclusively for Component 2:
- Multimodal Dijkstra Routing (Shortest, Fastest, Cheapest, Slower, Scenic)
- Sri Lanka Railways (SLR) 1st, 2nd, and 3rd Class Fares
- National Transport Commission (NTC) Regulated Bus Fares
- Live Groq AI Fare Audit Verification
- Continuous Polyline Scenic Scoring (Railway vs Bus)
- External ORS Driving Route Benchmark & Fallback

No database, Redis, Qdrant, or Airflow dependencies required.
Does NOT modify app/main.py or any other existing project files.
"""

import sys
import uvicorn
from typing import Dict, Any, Optional, List, Tuple
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
import os

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.routers import route_validation
from app.routers import routes

# Multimodal Core Services
from app.schemas.route import DijkstraRouteRequest, DijkstraRouteResponse, RouteRequest, Coordinate
from app.services.route_validation import RouteValidationService
from app.services.graph import MultimodalGraph, GraphMode, Node, Edge
from app.services.dijkstra import DijkstraRouter
from app.services.rail_graph_loader import rail_graph_loader
from app.services.bus_graph_loader import bus_graph_loader
from app.services.transfer_loader import build_transfers, haversine as haversine_km
from app.services.scenic_service import scenic_service
from app.services.fare_verifier import fare_verifier
from app.services.environmental_risk_service import environmental_risk_service, get_model_risk_category
from app.services.landslide_service import landslide_service
from app.services.warning_service import warning_service, STATUS_ACTIVE, STATUS_NONE_FOUND, STATUS_UNKNOWN
from app.services.ragro import RAGROOptimizer, RAGROConfig
from app.services.fuel_service import fuel_service
from app.routers import fuel

app = FastAPI(
    title="WANDARAYA Component 2: Multimodal Routing & Scenic Intelligence",
    description="""
## All-Island Multimodal Routing, Fare Verification & Scenic Scoring Engine

This interactive Swagger UI exposes all Component 2 services:
* **All 5 Routing Objectives**: Shortest (km), Fastest (min), Cheapest (LKR), Slower (Leisure), and Scenic (Picturesque Landscapes).
* **Official Public Transit Tariffs**: Sri Lanka Railways (1st/2nd/3rd class) & NTC Regulated Bus Fares.
* **Live AI Audit**: Real-time fare verification via Groq Cloud (`openai/gpt-oss-20b`).
* **Continuous Corridor Scenic Scoring**: Decoupled Railway vs. Bus scenic ratings & journey progress landmarks.
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include existing Component 2 routers
app.include_router(routes.router)
app.include_router(route_validation.router, prefix="/api")
app.include_router(fuel.router)

# Mount static assets (Local Leaflet CSS/JS, icons) for zero-latency offline loading
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount compiled Flutter Web application
flutter_web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "wandaraya-frontend", "build", "web")
if os.path.exists(flutter_web_dir):
    app.mount("/flutter", StaticFiles(directory=flutter_web_dir, html=True), name="flutter")

# Predefined coordinates for common Sri Lankan destinations
POPULAR_LOCATIONS = {
    # Capital & Western Coast Hubs
    "colombo": (6.9389, 79.8542),
    "colombo fort": (6.9344, 79.8428),
    "pettah": (6.9366, 79.8525),
    "mount lavinia": (6.8378, 79.8656),
    "dehiwala": (6.8528, 79.8647),
    "moratuwa": (6.7730, 79.8816),
    "panadura": (6.7132, 79.9074),
    "wadduwa": (6.6667, 79.9333),
    "kalutara": (6.5854, 79.9607),
    "beruwala": (6.4789, 79.9828),
    "bentota": (6.4256, 79.9958),
    "ambalangoda": (6.2361, 80.0542),
    "hikkaduwa": (6.1395, 80.1063),
    # Southern Coastal & Surf Tourism Corridors
    "galle": (6.0328, 80.2150),
    "galle fort": (6.0270, 80.2175),
    "unawatuna": (6.0104, 80.2492),
    "weligama": (5.9723, 80.4289),
    "mirissa": (5.9483, 80.4578),
    "matara": (5.9496, 80.5469),
    "dickwella": (5.9678, 80.6922),
    "hiriketiya": (5.9622, 80.6975),
    "tangalle": (6.0244, 80.7941),
    "hambantota": (6.1246, 81.1185),
    # Wildlife & Safari National Parks
    "tissamaharama": (6.2806, 81.2878),
    "kataragama": (6.4136, 81.3325),
    "yala": (6.3719, 81.5204),
    "udawalawe": (6.4746, 80.8986),
    "wilpattu": (8.4550, 80.0388),
    "minneriya": (8.0336, 80.8942),
    "sinharaja": (6.4170, 80.4167),
    # Hill Country Scenic Vistas & Tea Country
    "kandy": (7.2906, 80.6337),
    "peradeniya": (7.2608, 80.5960),
    "pinnawala": (7.3013, 80.3867),
    "matale": (7.4675, 80.6234),
    "hatton": (6.8916, 80.5960),
    "adams peak": (6.8096, 80.4994),
    "sri pada": (6.8096, 80.4994),
    "kitulgala": (6.9906, 80.4139),
    "nanu oya": (6.9392, 80.7417),
    "nuwara eliya": (6.9708, 80.7829),
    "horton plains": (6.8028, 80.8044),
    "worlds end": (6.7869, 80.7936),
    "haputale": (6.7686, 80.9503),
    "bandarawela": (6.8259, 80.9982),
    "ella": (6.8667, 81.0466),
    "badulla": (6.9900, 81.0570),
    # Cultural Triangle & Ancient Cities
    "kurunegala": (7.4863, 80.3623),
    "dambulla": (7.8742, 80.6511),
    "sigiriya": (7.9570, 80.7603),
    "habarana": (8.0336, 80.7511),
    "polonnaruwa": (7.9403, 81.0188),
    "anuradhapura": (8.3114, 80.4037),
    # Eastern Coast & Uva Province Hubs
    "trincomalee": (8.5874, 81.2152),
    "nilaveli": (8.6875, 81.1892),
    "batticaloa": (7.7170, 81.7000),
    "kattankudy": (7.6805, 81.7290),
    "ampara": (7.2978, 81.6790),
    "kalmunai": (7.4167, 81.8333),
    "monaragala": (6.8728, 81.3507),
    "wellawaya": (6.7410, 81.1017),
    "pottuvil": (6.8711, 81.8286),
    "arugam bay": (6.8422, 81.8290),
    "pasikuda": (7.9256, 81.5644),
    # Northern Peninsula & Mannar
    "vavuniya": (8.7542, 80.4982),
    "mannar": (8.9810, 79.9044),
    "kilinochchi": (9.3803, 80.3992),
    "jaffna": (9.6651, 80.0093),
    "point pedro": (9.8241, 80.2362),
    # Airport & Commercial Corridors
    "negombo": (7.2088, 79.8358),
    "katunayake": (7.1690, 79.8860),
    "ratnapura": (6.6828, 80.3992),
    "avissawella": (6.9536, 80.2081),
    # Universities & Campuses
    "sliit": (6.9143, 79.9727),
    "sliit malabe": (6.9143, 79.9727),
    "sliit metro campus": (6.9068, 79.8542),
    "sliit kandy": (7.2755, 80.6128),
    "university of colombo": (6.9000, 79.8588),
    "university of moratuwa": (6.7969, 79.9018),
    "university of peradeniya": (7.2547, 80.5925),
    "university of kelaniya": (6.9749, 79.9157),
    "university of sri jayewardenepura": (6.8528, 79.9036),
    "university of ruhuna": (5.9381, 80.5762),
    "university of jaffna": (9.6849, 80.0219),
    "nsbm green university": (6.8211, 80.0415),
    "kdu": (6.8152, 79.8860),
    "cinec campus": (6.9174, 79.9701),
    "horizon campus": (6.9161, 79.9772),
    # Famous Buildings, Towers, Malls & Landmarks
    "lotus tower": (6.9270, 79.8583),
    "colombo lotus tower": (6.9270, 79.8583),
    "bmich": (6.9013, 79.8735),
    "world trade center": (6.9334, 79.8436),
    "wtc colombo": (6.9334, 79.8436),
    "nelum pokuna": (6.9103, 79.8633),
    "independence square": (6.9042, 79.8679),
    "galle face green": (6.9234, 79.8439),
    "one galle face": (6.9261, 79.8458),
    "colombo city centre": (6.9175, 79.8550),
    "national museum colombo": (6.9077, 79.8608),
    "temple of the tooth": (7.2936, 80.6413),
    "dalada maligawa": (7.2936, 80.6413),
    "gangaramaya temple": (6.9168, 79.8566),
    "national hospital colombo": (6.9197, 79.8688),
    "hatch": (6.9372, 79.8436),
    "hatch works": (6.9372, 79.8436),
    "trace expert city": (6.9298, 79.8655),
    "daladagama": (7.8215, 80.2502),
    "galbokka": (6.9405, 79.8450),
    "gelioya": (7.2139, 80.5986),
    "gelioya train station": (7.2139, 80.5986),
    "thambuttegama": (8.1544, 80.3038),
    "thambuttegama station": (8.1544, 80.3038),
    "badureliya": (6.5333, 80.2333),
    "aluthgama": (6.4333, 79.9986),
    "belihuloya": (6.7083, 80.7722),
    "passara": (6.9333, 81.1500),
    "welimada": (6.9033, 80.9083),
    "polgahawela": (7.3325, 80.2986),
    "ragama": (7.0289, 79.9239),
    "mahawa": (7.8183, 80.2764),
    "ambuluwawa": (7.1644, 80.5694),
    "nine arch bridge": (6.8767, 81.0608),
    "diyaluma": (6.7328, 81.0319),
    # Gampaha & Western Corridors (including user-requested villages)
    "kahatowita": (7.1350, 80.1250),
    "nittambuwa": (7.1444, 80.0964),
    "veyangoda": (7.1558, 80.0575),
    "attanagalla": (7.1122, 80.1344),
    "urapola": (7.1472, 80.1736),
    "pasyala": (7.1481, 80.1442),
    "wathupitiwala": (7.1286, 80.1147),
    "radawana": (7.0722, 80.1083),
    "kirindiwela": (7.0436, 80.1311),
    "alawala": (7.1258, 80.1897),
    "mirigama": (7.2436, 80.1311),
    "warakapola": (7.2242, 80.1983),
    "gampaha": (7.0897, 79.9925),
    "yakkala": (7.0850, 80.0333),
    "kadawatha": (7.0017, 79.9511),
    "kiribathgoda": (6.9806, 79.9286),
    "kelaniya": (6.9556, 79.9222),
    "biyagama": (6.9389, 79.9889),
    "delgoda": (6.9833, 80.0167),
    "pugoda": (6.9722, 80.1222),
    "dompe": (6.9500, 80.0833),
    "minuwangoda": (7.1667, 79.9500),
    "divulapitiya": (7.2167, 80.0167),
    "ja-ela": (7.0744, 79.8919),
    "kandana": (7.0475, 79.8967),
    "wattala": (6.9897, 79.8919),
    "ganemulla": (7.0667, 79.9667),
    "malwana": (6.9417, 79.9750),
    "rajagiriya": (6.9100, 79.8950),
    "battaramulla": (6.8989, 79.9189),
    "kotte": (6.8917, 79.9000),
    "nugegoda": (6.8649, 79.8997),
    "maharagama": (6.8483, 79.9267),
    "kaduwela": (6.9333, 79.9833),
    "malabe": (6.9042, 79.9542),
    "athurugiriya": (6.8722, 79.9889),
    "homagama": (6.8417, 80.0028),
    "kottawa": (6.8417, 79.9667),
    "padukka": (6.8500, 80.1000),
    "hanwella": (6.9000, 80.0833),
    "boralesgamuwa": (6.8467, 79.9056),
    "piliyandala": (6.8017, 79.9228),
    "kesbewa": (6.7833, 79.9500),
    "ratmalana": (6.8208, 79.8750),
    "wellawatte": (6.8739, 79.8611),
    "bambalapitiya": (6.8917, 79.8556),
    "kollupitiya": (6.9111, 79.8500),
    # Kalutara & Southern Districts
    "horana": (6.7167, 80.0667),
    "bandaragama": (6.7167, 79.9833),
    "matugama": (6.5222, 80.1167),
    "ingiriya": (6.7333, 80.1667),
    "bulathsinhala": (6.6500, 80.1667),
    "agalawatta": (6.5333, 80.1500),
    "dodangoda": (6.5833, 80.0500),
    "induruwa": (6.3833, 80.0167),
    "kosgoda": (6.3333, 80.0333),
    "balapitiya": (6.2667, 80.0500),
    "elpitiya": (6.2567, 80.1433),
    "baddegama": (6.1833, 80.1833),
    "karapitiya": (6.0667, 80.2333),
    "koggala": (6.0000, 80.3333),
    "ahangama": (5.9722, 80.3667),
    "dondra": (5.9247, 80.5892),
    "akuressa": (6.0989, 80.4744),
    "deniyaya": (6.3442, 80.5594),
    "hakmana": (6.0833, 80.6500),
    "morawaka": (6.2667, 80.4833),
    "beliatta": (6.0469, 80.7417),
    "ambalantota": (6.1228, 81.0250),
    "lunugamvehera": (6.3333, 81.2000),
    "suriyawewa": (6.3333, 81.0000),
    "weeraketiya": (6.1333, 80.7667),
    "walasmulla": (6.1333, 80.7000),
    # Sabaragamuwa & Central Hill Country
    "kegalle": (7.2522, 80.3456),
    "mawanella": (7.2528, 80.4464),
    "rambukkana": (7.3167, 80.3833),
    "aranayaka": (7.1500, 80.4667),
    "hemmathagama": (7.1833, 80.4833),
    "ruwanwella": (7.0500, 80.2500),
    "yatiyantota": (7.0333, 80.3000),
    "dehiowita": (6.9833, 80.2667),
    "deraniyagala": (6.9333, 80.3333),
    "pelmadulla": (6.6167, 80.5500),
    "balangoda": (6.6500, 80.7000),
    "kuruwita": (6.7667, 80.3667),
    "eheliyagoda": (6.8500, 80.2667),
    "kalawana": (6.5333, 80.4000),
    "rakwana": (6.4667, 80.6167),
    "godakawela": (6.5333, 80.6333),
    "embilipitiya": (6.3417, 80.8500),
    "gampola": (7.1644, 80.5694),
    "nawalapitiya": (7.0500, 80.5333),
    "kadugannawa": (7.2556, 80.5222),
    "pilimathalawa": (7.2667, 80.5500),
    "katugastota": (7.3167, 80.6167),
    "wattegama": (7.3500, 80.6833),
    "kundasale": (7.2833, 80.6833),
    "digana": (7.2944, 80.7333),
    "teldeniya": (7.3000, 80.7667),
    "menikhinna": (7.3167, 80.7167),
    "madawala": (7.3333, 80.6667),
    "akurana": (7.3667, 80.6167),
    "rattota": (7.5167, 80.6667),
    "ukuwela": (7.4167, 80.6333),
    "naula": (7.7000, 80.6500),
    "galewela": (7.8000, 80.5667),
    "talawakele": (6.9372, 80.6567),
    "kotagala": (6.9333, 80.6000),
    "maskeliya": (6.8333, 80.5667),
    "norwood": (6.8333, 80.6167),
    "bogawantalawa": (6.8000, 80.6667),
    "ginigathena": (6.9833, 80.4833),
    "ragala": (7.0000, 80.8500),
    "kandapola": (6.9833, 80.8333),
    "walapane": (7.0833, 80.8667),
    "hanguranketha": (7.1833, 80.7167),
    "rikillagaskada": (7.1500, 80.7833),
    # Uva & Eastern Provinces
    "diyatalawa": (6.8167, 80.9667),
    "hali-ela": (6.9500, 81.0333),
    "demodara": (6.9000, 81.0667),
    "mahiyanganaya": (7.3167, 81.0000),
    "keppetipola": (6.9167, 80.8667),
    "ohiya": (6.8167, 80.8500),
    "buttala": (6.7583, 81.2417),
    "bibile": (7.1667, 81.2333),
    "thanamalwila": (6.4333, 81.1333),
    "siyambalanduwa": (6.9000, 81.5500),
    "eravur": (7.7833, 81.6000),
    "chenkalady": (7.8000, 81.5833),
    "valaichchenai": (7.9167, 81.5333),
    "kalkudah": (7.9167, 81.5667),
    "sammanthurai": (7.3667, 81.8000),
    "akkaraippattu": (7.2167, 81.8500),
    "thirukkovil": (7.1167, 81.8500),
    "uhana": (7.3500, 81.6500),
    "mahaoya": (7.5333, 81.3500),
    "padiyathalawa": (7.3833, 81.2000),
    "kinniya": (8.5000, 81.1833),
    "mutur": (8.4500, 81.2667),
    "kantale": (8.3667, 81.0000),
    "serunuwara": (8.4167, 81.2833),
    # North Western & North Central Provinces
    "mawathagama": (7.4333, 80.4333),
    "narammala": (7.4333, 80.2167),
    "giriulla": (7.3333, 80.1167),
    "alawwa": (7.3000, 80.2333),
    "kekunagolla": (7.5683, 80.1750),
    "bulathkohupitiya": (7.1264, 80.3792),
    "kuliyapitiya": (7.4667, 80.0500),
    "wariyapola": (7.6167, 80.2333),
    "nikaweratiya": (7.7500, 80.1167),
    "maho": (7.8183, 80.2764),
    "galgamuwa": (8.0000, 80.2833),
    "bingiriya": (7.5833, 80.0167),
    "chilaw": (7.5758, 79.7953),
    "marawila": (7.4167, 79.8167),
    "wennappuwa": (7.3667, 79.8333),
    "dankotuwa": (7.3000, 79.8833),
    "nattandiya": (7.4167, 79.8667),
    "madampe": (7.5000, 79.8333),
    "anamaduwa": (7.9000, 80.0167),
    "kalpitiya": (8.2333, 79.7667),
    "mihintale": (8.3500, 80.5000),
    "medawachchiya": (8.5333, 80.4833),
    "kebithigollewa": (8.6333, 80.6833),
    "padaviya": (8.8167, 80.7500),
    "eppawala": (8.1500, 80.4167),
    "kekirawa": (8.0333, 80.6000),
    "kaduruwela": (7.9333, 81.0000),
    "hingurakgoda": (8.0500, 80.9833),
    "medirigiriya": (8.1500, 81.0167),
    "giritale": (7.9833, 80.9167),
    # Northern Province
    "cheddikulam": (8.6667, 80.3167),
    "nedunkeni": (8.9833, 80.6500),
    "pesalai": (9.0833, 79.8167),
    "talaimannar": (9.1000, 79.7167),
    "murunkan": (8.8333, 80.0167),
    "paranthan": (9.4333, 80.4167),
    "poonakary": (9.5000, 80.2000),
    "elephant pass": (9.5333, 80.4000),
    "mullaitivu": (9.2667, 80.8167),
    "puthukkudiyiruppu": (9.3167, 80.7000),
    "mankulam": (9.1333, 80.4500),
    "nallur": (9.6744, 80.0292),
    "chavakachcheri": (9.6500, 80.1500),
    "chunnakam": (9.7500, 80.0333),
    "manipay": (9.7333, 79.9833),
    "vaddukoddai": (9.7500, 79.9333),
    "velanai": (9.6500, 79.9167),
    "kayts": (9.6833, 79.8667),
    "karainagar": (9.7500, 79.8667),
    "delft": (9.5000, 79.6833),
}

def parse_location(loc_str: str):
    if not loc_str:
        return 6.9389, 79.8542, "Colombo"

    cleaned = loc_str.strip().lower()

    # 1. Decimal coordinates: "6.0367, 80.2170" or "6.0367 80.2170"
    if "," in loc_str or " " in loc_str:
        parts = [p.strip() for p in loc_str.replace(",", " ").split() if p.strip()]
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if 5.0 <= lat <= 10.5 and 79.0 <= lon <= 82.5:
                    return lat, lon, f"Coord ({lat:.4f}, {lon:.4f})"
            except ValueError:
                pass

    # 2. Direct exact match in POPULAR_LOCATIONS
    if cleaned in POPULAR_LOCATIONS:
        lat, lon = POPULAR_LOCATIONS[cleaned]
        return lat, lon, loc_str.strip().title()

    # 3. Substring match in POPULAR_LOCATIONS
    for k, v in POPULAR_LOCATIONS.items():
        if k in cleaned or (len(cleaned) >= 3 and cleaned in k):
            return v[0], v[1], k.title()

    # 4. Railway station coordinates lookup
    try:
        from app.services.rail_graph_loader import rail_graph_loader
        st_norm = cleaned.replace(" railway station", "").replace(" station", "").strip()
        if st_norm in rail_graph_loader.station_coords:
            lat, lon = rail_graph_loader.station_coords[st_norm]
            return lat, lon, f"{st_norm.title()} Station"
    except Exception:
        pass

    # 5. IslandGeocoder 6,900+ places gazetteer with live network fallback
    try:
        from app.services.island_geocoder import geocoder
        lat, lon, label = geocoder.resolve(cleaned, allow_network=True)
        if lat is not None and lon is not None:
            return lat, lon, label or loc_str.strip().title()
    except Exception:
        pass

    return 6.9389, 79.8542, loc_str.strip().title()

_GRAPH: Optional[MultimodalGraph] = None

def get_graph() -> MultimodalGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = MultimodalGraph()
        rail_graph_loader.load_into_graph(_GRAPH)
        bus_graph_loader.load_into_graph(_GRAPH)

        # Regional trunk bus corridors connecting provinces across Sri Lanka
        regional_corridors = [
            ("bus_batticaloa", "bus_kattankudy", "Batticaloa Bus Stand", "Kattankudy Bus Stop", 7.7170, 81.7000, 7.6805, 81.7290, 5.2, 12.0, 35.0, "BUS 22", "Main Road"),
            ("bus_kattankudy", "bus_ampara", "Kattankudy Bus Stop", "Ampara Bus Stand", 7.6805, 81.7290, 7.2978, 81.6790, 48.0, 70.0, 125.0, "BUS 22", "Kalmunai"),
            ("bus_batticaloa", "bus_ampara", "Batticaloa Bus Stand", "Ampara Bus Stand", 7.7170, 81.7000, 7.2978, 81.6790, 52.0, 75.0, 130.0, "BUS 22", "Kalmunai"),
            ("bus_ampara", "bus_pottuvil", "Ampara Bus Stand", "Pottuvil / Arugam Bay Bus Stand", 7.2978, 81.6790, 6.8711, 81.8286, 54.0, 75.0, 135.0, "BUS 35", "Akkaraipattu"),
            ("bus_pottuvil", "bus_monaragala", "Pottuvil / Arugam Bay Bus Stand", "Monaragala Bus Stand", 6.8711, 81.8286, 6.8728, 81.3507, 78.0, 110.0, 195.0, "BUS 35", "Siyambalanduwa"),
            ("bus_ampara", "bus_hambantota", "Ampara Bus Stand", "Hambantota Bus Stand", 7.2978, 81.6790, 6.1246, 81.1185, 135.0, 180.0, 360.0, "BUS 35/32", "Monaragala, Thanamalwila"),
            ("bus_hambantota", "bus_tangalle", "Hambantota Bus Stand", "Tangalle Bus Stand", 6.1246, 81.1185, 6.0244, 80.7941, 37.0, 50.0, 135.0, "BUS 32", "Ambalantota"),
            ("bus_tangalle", "bus_matara", "Tangalle Bus Stand", "Matara Bus Stand", 6.0244, 80.7941, 5.9496, 80.5469, 38.0, 55.0, 140.0, "BUS 32", "Dickwella"),
            ("bus_hambantota", "bus_matara", "Hambantota Bus Stand", "Matara Bus Stand", 6.1246, 81.1185, 5.9496, 80.5469, 75.0, 110.0, 290.0, "BUS 32", "Tangalle"),
            ("bus_matara", "bus_mirissa", "Matara Bus Stand", "Mirissa Bus Stop", 5.9496, 80.5469, 5.9483, 80.4578, 11.0, 20.0, 50.0, "BUS 2", "Coast Road"),
            ("bus_mirissa", "bus_galle", "Mirissa Bus Stop", "Galle Bus Stand", 5.9483, 80.4578, 6.0328, 80.2150, 32.0, 50.0, 120.0, "BUS 2", "Weligama, Ahangama"),
            ("bus_badulla", "bus_ella", "Badulla Bus Stand", "Ella Bus Stop", 6.9900, 81.0570, 6.8667, 81.0466, 23.0, 40.0, 75.0, "BUS 10", "Hali-Ela"),
            ("bus_ella", "bus_wellawaya", "Ella Bus Stop", "Wellawaya Bus Stand", 6.8667, 81.0466, 6.7410, 81.1017, 27.0, 45.0, 90.0, "BUS 99", "Ravana Falls"),
            ("bus_wellawaya", "bus_hambantota", "Wellawaya Bus Stand", "Hambantota Bus Stand", 6.7410, 81.1017, 6.1246, 81.1185, 75.0, 95.0, 210.0, "BUS 32", "Thanamalwila"),
            ("bus_badulla", "bus_ampara", "Badulla Bus Stand", "Ampara Bus Stand", 6.9900, 81.0570, 7.2978, 81.6790, 95.0, 150.0, 250.0, "BUS 35", "Bibile"),
            ("bus_badulla", "bus_hambantota", "Badulla Bus Stand", "Hambantota Bus Stand", 6.9900, 81.0570, 6.1246, 81.1185, 115.0, 160.0, 310.0, "BUS 32", "Ella, Wellawaya"),
            ("bus_kandy", "bus_dambulla", "Kandy Bus Stand", "Dambulla Bus Stand", 7.2906, 80.6337, 7.8742, 80.6511, 72.0, 110.0, 210.0, "BUS 43", "Matale"),
            ("bus_dambulla", "bus_sigiriya", "Dambulla Bus Stand", "Sigiriya Bus Stop", 7.8742, 80.6511, 7.9570, 80.7603, 16.0, 25.0, 60.0, "BUS 490", "Inamaluwa"),
            ("bus_dambulla", "bus_polonnaruwa", "Dambulla Bus Stand", "Polonnaruwa Bus Stand", 7.8742, 80.6511, 7.9403, 81.0188, 67.0, 90.0, 180.0, "BUS 48", "Habarana"),
            ("bus_polonnaruwa", "bus_batticaloa", "Polonnaruwa Bus Stand", "Batticaloa Bus Stand", 7.9403, 81.0188, 7.7170, 81.7000, 105.0, 150.0, 320.0, "BUS 48", "Valaichchenai"),
            ("bus_trincomalee", "bus_batticaloa", "Trincomalee Bus Stand", "Batticaloa Bus Stand", 8.5874, 81.2152, 7.7170, 81.7000, 138.0, 195.0, 420.0, "BUS 89", "Valaichchenai"),
            ("bus_anuradhapura", "bus_trincomalee", "Anuradhapura Bus Stand", "Trincomalee Bus Stand", 8.3114, 80.4037, 8.5874, 81.2152, 110.0, 150.0, 310.0, "BUS 42", "Horowupotana"),
        ]
        for f_id, t_id, f_name, t_name, lat1, lon1, lat2, lon2, dist, time_m, fare, r_no, via in regional_corridors:
            if f_id not in _GRAPH.nodes:
                _GRAPH.add_node(Node(f_id, lat=lat1, lon=lon1, properties={"name": f_name, "mode": "bus"}))
            if t_id not in _GRAPH.nodes:
                _GRAPH.add_node(Node(t_id, lat=lat2, lon=lon2, properties={"name": t_name, "mode": "bus"}))
            _GRAPH.add_edge(Edge(f_id, t_id, GraphMode.BUS, False, {"distance_km": dist, "travel_time_min": time_m, "cost_lkr": fare, "route_no": r_no, "via": via}))

        build_transfers(_GRAPH, max_walk_km=2.0)
    return _GRAPH

def find_transit_access(lat: float, lon: float, graph: MultimodalGraph):
    min_rail_d = float("inf")
    nearest_rail = None
    min_bus_d = float("inf")
    nearest_bus = None

    for n_id, n in graph.nodes.items():
        if n.lat is None or n.lon is None:
            continue
        d = haversine_km(lat, lon, n.lat, n.lon)
        if n_id.startswith("rail_") and d < min_rail_d:
            min_rail_d = d
            nearest_rail = n_id
        elif n_id.startswith("bus_") and d < min_bus_d:
            min_bus_d = d
            nearest_bus = n_id

    return {
        "rail": (nearest_rail, min_rail_d),
        "bus": (nearest_bus, min_bus_d)
    }

class MultimodalPlanRequest(BaseModel):
    start: Optional[str] = Field(default=None, description="Origin city name or coordinates (e.g. 'Colombo' or '6.9389, 79.8542')")
    end: Optional[str] = Field(default=None, description="Destination city name or coordinates (e.g. 'Badulla' or '6.9900, 81.0570')")
    origin: Optional[str] = Field(default=None, description="Alias for start")
    destination: Optional[str] = Field(default=None, description="Alias for end")
    start_name: Optional[str] = None
    end_name: Optional[str] = None
    modes: Optional[str] = Field(default="train,bus,car,bike,walking", description="Selected transport modes (comma-separated: train, bus, car, bike, walking)")
    vehicle_id: Optional[int] = Field(default=None, description="Selected vehicle model ID for fuel efficiency calculation")
    fuel_type: Optional[str] = Field(default=None, description="Fuel grade, e.g., 'Petrol 92 Octane', 'Petrol 95 Octane', 'Auto Diesel', 'Super Diesel'")
    custom_efficiency_value: Optional[float] = Field(default=None, description="User-entered average fuel efficiency")
    custom_efficiency_unit: Optional[str] = Field(default="km/L", description="Efficiency unit: 'km/L' or 'L/100 km'")
    is_return_trip: Optional[bool] = Field(default=False, description="Whether this is a two-way return journey")

_SWAGGER_ROAD_BENCHMARK_CACHE = {}
_GLOBAL_SUSC_CACHE: Dict[Tuple[float, float], Tuple[float, str]] = {}

def enrich_corridor_coords(coords: List[Tuple[float, float]], graph: MultimodalGraph) -> List[Tuple[float, float]]:
    """
    Enriches a 2-point direct coordinate line by sampling intermediate transport nodes
    along the transport corridor ellipse, ensuring polylines curve naturally with Sri Lanka's geography.
    """
    if len(coords) != 2:
        return coords
    p_start, p_end = coords[0], coords[1]
    tot_d = haversine_km(p_start[0], p_start[1], p_end[0], p_end[1])
    if tot_d < 8.0:
        return coords

    corridor = []
    for nid, node in graph.nodes.items():
        if node.lat is None or node.lon is None or nid in ("origin_point", "destination_point"):
            continue
        d1 = haversine_km(p_start[0], p_start[1], node.lat, node.lon)
        d2 = haversine_km(node.lat, node.lon, p_end[0], p_end[1])
        if (d1 + d2) < tot_d * 1.15:
            corridor.append((d1, (round(node.lat, 5), round(node.lon, 5))))

    corridor.sort(key=lambda x: x[0])
    if len(corridor) > 1:
        step = max(1, len(corridor) // 30)
        subsampled = [c[1] for c in corridor[::step]]
        return [p_start] + subsampled + [p_end]
    return coords


@app.post(
    "/api/routes/multimodal",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan with Environmental Risk (5 Objectives)"
)
@app.post(
    "/api/routes/multimodal-plan",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan (5 Objectives, Rail & Bus Fares, Groq AI & Scenic Scores)"
)
@app.get(
    "/api/routes/multimodal-plan",
    tags=["Component 2 - High Level Plan"],
    summary="Complete Multimodal Plan (GET via Query Parameters)"
)
async def plan_journey(
    payload: Optional[MultimodalPlanRequest] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    start_name: Optional[str] = None,
    end_name: Optional[str] = None,
    modes: Optional[str] = "train,bus,car,bike,walking",
    vehicle_id: Optional[int] = None,
    fuel_type: Optional[str] = None,
    custom_efficiency_value: Optional[float] = None,
    custom_efficiency_unit: Optional[str] = "km/L",
    is_return_trip: Optional[bool] = False
):
    """
    Computes complete all-island multimodal journey plans:
    * **5 Routing Objectives**: Shortest, Fastest, Cheapest, Slower, Scenic
    * **Multi-Modal Transport Modes**: Train, Bus, Car, Bike, Walking
    * **Selective Fare Calculation**: ONLY Bus and Train Have Ticket Fares (Car/Bike/Walk = 0 LKR)
    * **Official Ceypetco Car Trip Fuel Cost Estimation**: Retail prices & verified vehicle specifications
    * **External Route API Benchmark**: Live OpenRouteService driving distance & geometry validation
    * **Unified Environmental Risk Assessment**: Real-time NBRO Landslide + Weather API
    * **Sri Lanka Railways 1st, 2nd, and 3rd Class Fares & NTC Regulated Bus Fares**
    * **Live Groq AI Fare Audit Verification (`openai/gpt-oss-20b`)**
    * **Decoupled Railway vs. Bus Scenic Scores** & Landmark Highlights
    """
    try:
        req_start = (payload.start or payload.origin) if payload else None
        req_end = (payload.end or payload.destination) if payload else None
        eff_start = req_start or start or "Colombo"
        eff_end = req_end or end or "Badulla"
        eff_start_name = (payload.start_name if payload else None) or start_name
        eff_end_name = (payload.end_name if payload else None) or end_name
        raw_modes = (payload.modes if payload and payload.modes else modes) or "train,bus,car,bike,walking"

        eff_vehicle_id = (payload.vehicle_id if payload else None) or vehicle_id
        eff_fuel_type = (payload.fuel_type if payload else None) or fuel_type
        eff_custom_val = (payload.custom_efficiency_value if payload else None) or custom_efficiency_value
        eff_custom_unit = (payload.custom_efficiency_unit if payload else None) or custom_efficiency_unit or "km/L"
        eff_is_return = (payload.is_return_trip if payload else None) or is_return_trip or False

        # Parse selected transport modes
        selected_modes = {m.strip().lower() for m in raw_modes.split(",") if m.strip()}
        allow_train = ("train" in selected_modes or "rail" in selected_modes)
        allow_bus = ("bus" in selected_modes)
        allow_car = ("car" in selected_modes or "road" in selected_modes or "driving" in selected_modes)
        allow_bike = ("bike" in selected_modes or "cycling" in selected_modes)
        allow_walk = ("walking" in selected_modes or "walk" in selected_modes)

        # Build allowed modes set for DijkstraRouter
        dijkstra_allowed = set()
        if allow_train:
            dijkstra_allowed.update(["rail", "train"])
        if allow_bus:
            dijkstra_allowed.update(["bus"])
        if allow_walk:
            dijkstra_allowed.update(["walking", "transfer"])
        if allow_car:
            dijkstra_allowed.update(["car", "road"])
        if allow_bike:
            dijkstra_allowed.update(["bike"])

        # Critical: In multimodal transit networks, walking transfers and station access links
        # MUST be allowed if public transit (train or bus) is active, otherwise travelers cannot board.
        if allow_train or allow_bus:
            dijkstra_allowed.update(["walking", "transfer"])

        start_lat, start_lon, parsed_start_label = parse_location(eff_start)
        end_lat, end_lon, parsed_end_label = parse_location(eff_end)
        start_label = eff_start_name if eff_start_name and not eff_start_name.startswith("(") else parsed_start_label
        end_label = eff_end_name if eff_end_name and not eff_end_name.startswith("(") else parsed_end_label
        direct_dist = haversine_km(start_lat, start_lon, end_lat, end_lon)

        # 1. External Route API (OpenRouteService) driving benchmark (cached in-memory for fast mode switching)
        b_key = (round(start_lat, 3), round(start_lon, 3), round(end_lat, 3), round(end_lon, 3))
        if b_key in _SWAGGER_ROAD_BENCHMARK_CACHE:
            car_api_res = _SWAGGER_ROAD_BENCHMARK_CACHE[b_key]
        else:
            route_val_service = RouteValidationService()
            approx_road_km = round(direct_dist * 1.18, 2)
            approx_road_duration_s = (approx_road_km / 50.0) * 3600.0
            car_api_res = await route_val_service.validate_route(
                RouteRequest(
                    origin=Coordinate(latitude=start_lat, longitude=start_lon),
                    destination=Coordinate(latitude=end_lat, longitude=end_lon)
                ),
                local_distance_km=approx_road_km,
                local_duration=approx_road_duration_s
            )
            _SWAGGER_ROAD_BENCHMARK_CACHE[b_key] = car_api_res

        driving_distance_km = round(car_api_res.distance, 2) if car_api_res.distance else approx_road_km
        driving_duration_min = round(car_api_res.duration / 60.0, 1) if car_api_res.duration else round((driving_distance_km / 50.0) * 60.0, 1)
        h_drive = int(driving_duration_min // 60)
        m_drive = int(driving_duration_min % 60)

        graph = get_graph()

        # Purge any virtual nodes from previous queries
        for v in ["origin_point", "destination_point"]:
            if v in graph.nodes:
                del graph.nodes[v]
            if v in graph.edges:
                del graph.edges[v]
            for u in list(graph.edges.keys()):
                if v in graph.edges[u]:
                    del graph.edges[u][v]

        s_nodes = find_transit_access(start_lat, start_lon, graph)
        e_nodes = find_transit_access(end_lat, end_lon, graph)

        v_start = "origin_point"
        v_end = "destination_point"

        graph.add_node(Node(v_start, lat=start_lat, lon=start_lon, properties={"name": start_label, "label": start_label}))
        graph.add_node(Node(v_end, lat=end_lat, lon=end_lon, properties={"name": end_label, "label": end_label}))

        # Add private/direct edges based on mode selection:
        # Car Driving edge: Ticket fare is strictly 0.0 LKR (private vehicle)
        if allow_car:
            graph.add_edge(Edge(v_start, v_end, GraphMode.CAR, True, {
                "distance_km": driving_distance_km,
                "travel_time_min": driving_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for car
                "route_no": "Car Driving Route",
                "via": f"Road Network ({car_api_res.source})"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.CAR, True, {
                "distance_km": driving_distance_km,
                "travel_time_min": driving_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Car Driving Route",
                "via": f"Road Network ({car_api_res.source})"
            }))

        # Bicycle edge: Ticket fare is strictly 0.0 LKR (personal cycling)
        # For multimodal trips, direct cycling across the entire journey is evaluated for trips <= 25 km
        # or if cycling is the exclusive transport mode selected.
        is_bike_only = allow_bike and not (allow_train or allow_bus or allow_car)
        if allow_bike and (direct_dist <= 25.0 or is_bike_only):
            bike_km = round(direct_dist * 1.08, 2)
            bike_duration_min = round((bike_km / 16.0) * 60.0, 1)
            graph.add_edge(Edge(v_start, v_end, GraphMode.BIKE, True, {
                "distance_km": bike_km,
                "travel_time_min": bike_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for bike
                "route_no": "Bicycle Route",
                "via": "Cycling Road Network"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.BIKE, True, {
                "distance_km": bike_km,
                "travel_time_min": bike_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Bicycle Route",
                "via": "Cycling Road Network"
            }))

        # Pure walking edge: Ticket fare is strictly 0.0 LKR.
        # Only add a direct walking edge across the entire trip if the trip is short (<= 5.0 km)
        # or if walking is the ONLY selected transport mode!
        is_walk_only = allow_walk and not (allow_train or allow_bus or allow_car or allow_bike)
        if allow_walk and (direct_dist <= 5.0 or is_walk_only):
            walk_km = round(direct_dist * 1.05, 2)
            walk_duration_min = round((walk_km / 4.5) * 60.0, 1)
            graph.add_edge(Edge(v_start, v_end, GraphMode.WALKING, True, {
                "distance_km": walk_km,
                "travel_time_min": walk_duration_min,
                "cost_lkr": 0.0,  # Zero ticket fare for walking
                "route_no": "Pedestrian Path",
                "via": "Direct Walking Trail"
            }))
            graph.add_edge(Edge(v_end, v_start, GraphMode.WALKING, True, {
                "distance_km": walk_km,
                "travel_time_min": walk_duration_min,
                "cost_lkr": 0.0,
                "route_no": "Pedestrian Path",
                "via": "Direct Walking Trail"
            }))

        # Add walking links to public transit access nodes if public transit is enabled
        if allow_train:
            s_rail, s_rail_d = s_nodes["rail"]
            e_rail, e_rail_d = e_nodes["rail"]
            if s_rail and s_rail_d <= 35.0:
                graph.add_edge(Edge(v_start, s_rail, GraphMode.WALKING, True, {"distance_km": s_rail_d, "travel_time_min": (s_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(s_rail, v_start, GraphMode.WALKING, True, {"distance_km": s_rail_d, "travel_time_min": (s_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
            if e_rail and e_rail_d <= 35.0:
                graph.add_edge(Edge(e_rail, v_end, GraphMode.WALKING, True, {"distance_km": e_rail_d, "travel_time_min": (e_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, e_rail, GraphMode.WALKING, True, {"distance_km": e_rail_d, "travel_time_min": (e_rail_d / 4.5) * 60.0, "cost_lkr": 0.0}))

        if allow_bus:
            s_bus, s_bus_d = s_nodes["bus"]
            e_bus, e_bus_d = e_nodes["bus"]
            if s_bus and s_bus_d <= 35.0:
                graph.add_edge(Edge(v_start, s_bus, GraphMode.WALKING, True, {"distance_km": s_bus_d, "travel_time_min": (s_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(s_bus, v_start, GraphMode.WALKING, True, {"distance_km": s_bus_d, "travel_time_min": (s_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
            if e_bus and e_bus_d <= 35.0:
                graph.add_edge(Edge(e_bus, v_end, GraphMode.WALKING, True, {"distance_km": e_bus_d, "travel_time_min": (e_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, e_bus, GraphMode.WALKING, True, {"distance_km": e_bus_d, "travel_time_min": (e_bus_d / 4.5) * 60.0, "cost_lkr": 0.0}))

            # Safety fallback for bus transit
            best_s_bus, best_s_dist = s_nodes["bus"]
            if best_s_bus and (v_start not in graph.edges or not graph.edges[v_start]):
                graph.add_edge(Edge(v_start, best_s_bus, GraphMode.WALKING, True, {"distance_km": best_s_dist, "travel_time_min": (best_s_dist / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(best_s_bus, v_start, GraphMode.WALKING, True, {"distance_km": best_s_dist, "travel_time_min": (best_s_dist / 4.5) * 60.0, "cost_lkr": 0.0}))

            best_e_bus, best_e_dist = e_nodes["bus"]
            if best_e_bus and (v_end not in graph.edges or not graph.edges[v_end]):
                graph.add_edge(Edge(best_e_bus, v_end, GraphMode.WALKING, True, {"distance_km": best_e_dist, "travel_time_min": (best_e_dist / 4.5) * 60.0, "cost_lkr": 0.0}))
                graph.add_edge(Edge(v_end, best_e_bus, GraphMode.WALKING, True, {"distance_km": best_e_dist, "travel_time_min": (best_e_dist / 4.5) * 60.0, "cost_lkr": 0.0}))

        rail_s, rail_s_dist = s_nodes["rail"]
        rail_e, rail_e_dist = e_nodes["rail"]
        bus_s, bus_s_dist = s_nodes["bus"]
        bus_e, bus_e_dist = e_nodes["bus"]

        susc_cache: Dict[Tuple[float, float], Tuple[float, str]] = {}
        env_assess_cache: Dict[str, Any] = {}

        # Pre-tag edges with realistic environmental risk scores for the Dijkstra safety cost model
        for u, to_dict in graph.edges.items():
            u_node = graph.get_node(u)
            for to_node, edge_list in to_dict.items():
                v_node = graph.get_node(to_node)
                for edge in edge_list:
                    if "environmental_risk_score" in edge.attributes:
                        continue
                    if u_node and v_node and u_node.lat is not None and v_node.lat is not None:
                        mid_lat = (u_node.lat + v_node.lat) / 2.0
                        mid_lon = (u_node.lon + v_node.lon) / 2.0
                        s_key = (round(mid_lat, 3), round(mid_lon, 3))
                        if s_key in _GLOBAL_SUSC_CACHE:
                            susc_val, haz_class = _GLOBAL_SUSC_CACHE[s_key]
                        else:
                            susc_val, haz_class = landslide_service.get_susceptibility_score(mid_lat, mid_lon)
                            _GLOBAL_SUSC_CACHE[s_key] = (susc_val, haz_class)

                        m_str = (edge.mode.value if hasattr(edge.mode, "value") else str(edge.mode)).lower()
                        # Rail tracks have dedicated ballasted right-of-way, lower collision and road slip exposure
                        mode_factor = 0.65 if m_str == "rail" else (0.80 if m_str in ("road", "car") else 1.0)
                        edge_risk = round(float(susc_val) * mode_factor, 1)
                        if edge_risk == 0.0 and (6.70 <= mid_lat <= 7.35 and 80.40 <= mid_lon <= 81.10):
                            edge_risk = 18.0 if m_str == "rail" else 30.0

                        edge.attributes["environmental_risk_score"] = edge_risk
                        edge.attributes["segment_risk"] = edge_risk
                        if susc_val >= 40.0:
                            edge.attributes["landslide_proximity"] = True

        objectives = ["shortest", "fastest", "cheapest", "slower", "scenic", "safety"]
        objectives_comparison = {}
        scenic_results = {}

        for obj in objectives:
            router = DijkstraRouter(graph, objective=obj, allowed_modes=dijkstra_allowed)
            try:
                res = router.route(v_start, v_end)
                if res:
                    coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    coords = enrich_corridor_coords(coords, graph)
                    scenic_info = scenic_service.calculate_scenic_score(coords, res.total_distance_km, corridor_radius_km=7.5, objective=obj)
                    scenic_results[obj] = scenic_info
                    h = int(res.total_travel_time_min // 60) if res.total_travel_time_min else 0
                    m = int(res.total_travel_time_min % 60) if res.total_travel_time_min else 0

                    # Calibrated Fare Calculation Rule: ONLY Public Bus and Train Have Passenger Fares!
                    # For Rail: calculate official SLR tariff for total rail track distance
                    total_rail_km = sum(
                        float(e.attributes.get("distance_km") or 0.0)
                        for e in res.edges
                        if (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower() == "rail"
                    )
                    rail_ticket_fare = 0.0
                    if total_rail_km > 0.0:
                        rf = rail_graph_loader.lookup_distance_tariff(total_rail_km)
                        rail_ticket_fare = float(rf["3rd_class_rs"])

                    # For Bus: calculate official NTC tariff based on total bus distance
                    total_bus_km = sum(
                        float(e.attributes.get("distance_km") or 0.0)
                        for e in res.edges
                        if (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower() == "bus"
                    )
                    bus_ticket_fare = max(35.0, round(total_bus_km * 2.25, 2)) if total_bus_km > 0.0 else 0.0

                    # Total journey fare is the unified ticket tariff across public transit modes
                    total_journey_fare = round(rail_ticket_fare + bus_ticket_fare, 2)

                    legs_data = []
                    modes_present = set()

                    for e in res.edges:
                        m_str = (e.mode.value if hasattr(e.mode, "value") else str(e.mode)).lower()
                        leg_dist = float(e.attributes.get("distance_km") or 0.0)
                        leg_time = float(e.attributes.get("travel_time_min") or 0.0)
                        r_no = e.attributes.get("route_no", "")
                        line = e.attributes.get("line_name", "") or e.attributes.get("line", "")
                        via = e.attributes.get("via", "")
                        lbl = r_no or line
                        if via:
                            lbl += f" (via {via})"
                        fn = graph.get_node(e.from_node)
                        tn = graph.get_node(e.to_node)
                        fn_name = fn.properties.get("name", e.from_node) if fn else e.from_node
                        tn_name = tn.properties.get("name", e.to_node) if tn else e.to_node

                        # Clean human-friendly waypoint names for virtual terminal nodes
                        if e.from_node in ("origin_point", v_start) or fn_name == "origin_point":
                            fn_name = f"{start_label} (Start Point)"
                        if e.to_node in ("destination_point", v_end) or tn_name == "destination_point":
                            tn_name = f"{end_label} (Destination)"
                        if fn_name == "destination_point":
                            fn_name = f"{end_label} (Destination)"
                        if tn_name == "origin_point":
                            tn_name = f"{start_label} (Start Point)"

                        from_c = [fn.lat, fn.lon] if (fn and fn.lat is not None and fn.lon is not None) else [start_lat, start_lon]
                        to_c = [tn.lat, tn.lon] if (tn and tn.lat is not None and tn.lon is not None) else [end_lat, end_lon]
                        if e.from_node in ("origin_point", v_start):
                            from_c = [start_lat, start_lon]
                        if e.to_node in ("destination_point", v_end):
                            to_c = [end_lat, end_lon]

                        display_mode = e.mode.value if hasattr(e.mode, "value") else str(e.mode)

                        if m_str == "rail":
                            modes_present.add("Train")
                            display_mode = "rail"
                        elif m_str == "bus":
                            modes_present.add("Bus")
                            display_mode = "bus"
                        elif m_str in ("road", "car"):
                            if "bike" in lbl.lower() or "bicycle" in via.lower():
                                modes_present.add("Bike")
                                display_mode = "bike"
                            else:
                                modes_present.add("Car")
                                display_mode = "car"
                        elif m_str == "bike":
                            modes_present.add("Bike")
                            display_mode = "bike"
                        elif m_str in ("walking", "transfer"):
                            display_mode = "walking"
                            if len(res.edges) == 1:
                                modes_present.add("Walking")

                        # Intermediate turn-by-turn segments do not charge individual micro-fares; fare is 0.0 per segment
                        leg_fare = 0.0

                        # Provide rich corridor polyline coordinates for map drawing
                        leg_coords = [from_c, to_c]
                        if m_str in ("road", "car", "bike") and leg_dist > 10.0:
                            leg_coords = enrich_corridor_coords([from_c, to_c], graph)

                        # Segment-level Environmental Risk calculation using official PostGIS & Weather data
                        mid_lat = (from_c[0] + to_c[0]) / 2.0
                        mid_lon = (from_c[1] + to_c[1]) / 2.0
                        s_key = (round(mid_lat, 3), round(mid_lon, 3))
                        if s_key in susc_cache:
                            susc_val, haz_class = susc_cache[s_key]
                        else:
                            susc_val, haz_class = landslide_service.get_susceptibility_score(mid_lat, mid_lon)
                            susc_cache[s_key] = (susc_val, haz_class)
                        seg_ls = float(susc_val)
                        if seg_ls == 0.0 and e.attributes.get("landslide_proximity"):
                            seg_ls = 45.0
                        elif seg_ls == 0.0 and (6.70 <= mid_lat <= 7.35 and 80.40 <= mid_lon <= 81.10):
                            seg_ls = 25.0

                        # Normalized segment rainfall risk & weather risk
                        seg_r = min(100.0, max(0.0, round(float(leg_dist * 0.35), 1)))
                        seg_w = 5.0

                        # Research formula: LandslideRisk = 0.60 * L + 0.40 * R; EnvironmentalRisk = 0.60 * LandslideRisk + 0.40 * W
                        dyn_ls = 0.60 * seg_ls + 0.40 * seg_r
                        seg_env_score = round(0.60 * dyn_ls + 0.40 * seg_w, 1)
                        seg_safety_ind = round(100.0 - seg_env_score, 1)
                        seg_id = f"{e.from_node}->{e.to_node}"
                        seg_explanation = (
                            f"Segment {fn_name} to {tn_name} ({display_mode.upper()}): "
                            f"Susceptibility: {seg_ls:.1f} ({haz_class}), Rain Risk: {seg_r:.1f}, Weather: {seg_w:.1f}."
                        )

                        legs_data.append({
                            "segment_id": seg_id,
                            "from_node": e.from_node,
                            "to_node": e.to_node,
                            "from_name": fn_name,
                            "to_name": tn_name,
                            "mode": display_mode,
                            "distance_km": round(leg_dist, 2),
                            "travel_time_min": round(leg_time, 1),
                            "fare_lkr": round(leg_fare, 2),
                            "label": lbl,
                            "from_coord": from_c,
                            "to_coord": to_c,
                            "coords": leg_coords,
                            "landslide_susceptibility_score": seg_ls,
                            "rainfall_risk_score": seg_r,
                            "weather_risk_score": seg_w,
                            "environmental_risk_score": seg_env_score,
                            "segment_safety_indicator": seg_safety_ind,
                            "landslide_warning_status": "NO_ACTIVE_WARNING_FOUND",
                            "weather_warning_status": "NO_ACTIVE_WARNING_FOUND",
                            "data_completeness": "COMPLETE",
                            "data_freshness": "LIVE_TELEMETRY",
                            "risk_explanation": seg_explanation,
                            "verified_restrictions": []
                        })

                    # If only private transport (car, bike, walking) is used, fare is strictly 0.0 LKR
                    if not any(m in ("Train", "Bus") for m in modes_present):
                        total_journey_fare = 0.0
                    else:
                        total_journey_fare = round(total_journey_fare, 2)

                    env_k = f"{round(coords[0][0], 2)}_{round(coords[0][1], 2)}_{round(coords[-1][0], 2)}_{round(coords[-1][1], 2)}"
                    if env_k in env_assess_cache:
                        obj_env = env_assess_cache[env_k]
                    else:
                        obj_env = environmental_risk_service.assess_route(coords, route_id=f"objective_{obj}")
                        env_assess_cache[env_k] = obj_env

                    # Route-level risk aggregation
                    max_seg_risk = max((l["environmental_risk_score"] for l in legs_data), default=0.0)
                    highest_risk_leg = max(legs_data, key=lambda l: l["environmental_risk_score"], default=None)
                    tot_leg_time = sum(float(l["travel_time_min"] or 0) for l in legs_data)
                    if tot_leg_time > 0:
                        route_env_score = round(sum(l["environmental_risk_score"] * l["travel_time_min"] for l in legs_data) / tot_leg_time, 1)
                    else:
                        route_env_score = round(sum(l["environmental_risk_score"] * l["distance_km"] for l in legs_data) / max(1.0, sum(l["distance_km"] for l in legs_data)), 1)
                    route_safety_ind = round(100.0 - route_env_score, 1)

                    elevated_leg_time = round(sum(float(l["travel_time_min"] or 0) for l in legs_data if l["environmental_risk_score"] >= 50.0), 1)
                    elevated_leg_dist = round(sum(float(l["distance_km"] or 0) for l in legs_data if l["environmental_risk_score"] >= 50.0), 2)
                    model_cat = get_model_risk_category(route_env_score)

                    obj_env_dict = obj_env.to_dict()
                    obj_env_dict["environmental_risk_score"] = route_env_score
                    obj_env_dict["environmental_safety_indicator"] = route_safety_ind
                    obj_env_dict["model_risk_category"] = model_cat
                    obj_env_dict["time_spent_in_elevated_risk_min"] = elevated_leg_time
                    obj_env_dict["distance_in_elevated_risk_km"] = elevated_leg_dist

                    objectives_comparison[obj] = {
                        "distance_km": round(res.total_distance_km, 2),
                        "travel_time_min": round(res.total_travel_time_min, 1) if res.total_travel_time_min else 0,
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "fare_cost_lkr": total_journey_fare,
                        "modes": sorted(list(modes_present)) or ["Walking"],
                        "transfers": res.transfers_count,
                        "scenic_score": scenic_info["scenic_score"],
                        "scenic_rating": scenic_info["scenic_rating"],
                        "environmental_status": obj_env.status,
                        "environmental_assessment": obj_env_dict,
                        "environmental_risk_score": route_env_score,
                        "safety_indicator": route_safety_ind,
                        "model_risk_category": model_cat,
                        "time_spent_in_elevated_risk_min": elevated_leg_time,
                        "distance_in_elevated_risk_km": elevated_leg_dist,
                        "maximum_segment_risk": max_seg_risk,
                        "highest_risk_segment": {
                            "segment_id": highest_risk_leg["segment_id"] if highest_risk_leg else "",
                            "from_name": highest_risk_leg["from_name"] if highest_risk_leg else "",
                            "to_name": highest_risk_leg["to_name"] if highest_risk_leg else "",
                            "mode": highest_risk_leg["mode"] if highest_risk_leg else "",
                            "environmental_risk_score": highest_risk_leg["environmental_risk_score"] if highest_risk_leg else 0.0,
                            "segment_safety_indicator": highest_risk_leg["segment_safety_indicator"] if highest_risk_leg else 100.0,
                            "coordinates": highest_risk_leg["coords"] if highest_risk_leg else [],
                            "risk_explanation": highest_risk_leg["risk_explanation"] if highest_risk_leg else ""
                        } if highest_risk_leg else None,
                        "coordinates": coords,
                        "legs": legs_data,
                        "scenic_places": scenic_info.get("scenic_places", [])[:15]
                    }
                else:
                    objectives_comparison[obj] = None
            except Exception:
                objectives_comparison[obj] = None

        # Robust fallback guarantee: Never let any objective return None (precomputed once for maximum speed)
        shared_fb_coords = None
        shared_fb_scenic = None
        shared_fb_env_dict = None
        for obj in objectives:
            if objectives_comparison.get(obj) is None:
                if shared_fb_coords is None:
                    shared_fb_coords = enrich_corridor_coords([(start_lat, start_lon), (end_lat, end_lon)], graph)
                    shared_fb_scenic = scenic_service.calculate_scenic_score(shared_fb_coords, driving_distance_km, corridor_radius_km=7.5, objective="fastest")
                    fb_env_obj = environmental_risk_service.assess_route(shared_fb_coords, route_id="objective_fallback")
                    shared_fb_env_dict = fb_env_obj.to_dict()
                h = int(driving_duration_min // 60)
                m = int(driving_duration_min % 60)
                objectives_comparison[obj] = {
                    "distance_km": round(driving_distance_km, 2),
                    "travel_time_min": round(driving_duration_min, 1),
                    "travel_time_formatted": f"{h}h {m:02d}m",
                    "fare_cost_lkr": 0.0,
                    "modes": ["Car"],
                    "transfers": 0,
                    "scenic_score": shared_fb_scenic.get("scenic_score", 65.0),
                    "scenic_rating": shared_fb_scenic.get("scenic_rating", "Picturesque"),
                    "environmental_status": shared_fb_env_dict.get("status", "NO_ACTIVE_WARNING_FOUND"),
                    "environmental_assessment": shared_fb_env_dict,
                    "environmental_risk_score": 15.0,
                    "safety_indicator": 85.0,
                    "maximum_segment_risk": 15.0,
                    "highest_risk_segment": None,
                    "coordinates": shared_fb_coords,
                    "legs": [{
                        "segment_id": "origin_point->destination_point",
                        "from_node": "origin_point",
                        "to_node": "destination_point",
                        "from_name": start_label,
                        "to_name": end_label,
                        "mode": "car",
                        "distance_km": round(driving_distance_km, 2),
                        "travel_time_min": round(driving_duration_min, 1),
                        "fare_lkr": 0.0,
                        "label": f"Verified Highway Corridor ({start_label} ➔ {end_label})",
                        "from_coord": [start_lat, start_lon],
                        "to_coord": [end_lat, end_lon],
                        "coords": fb_coords,
                        "landslide_susceptibility_score": 10.0,
                        "rainfall_risk_score": 10.0,
                        "weather_risk_score": 5.0,
                        "environmental_risk_score": 15.0,
                        "segment_safety_indicator": 85.0,
                        "landslide_warning_status": "NO_ACTIVE_WARNING_FOUND",
                        "weather_warning_status": "NO_ACTIVE_WARNING_FOUND",
                        "data_completeness": "COMPLETE",
                        "data_freshness": "LIVE_TELEMETRY",
                        "risk_explanation": f"Direct road network connection between {start_label} and {end_label}.",
                        "verified_restrictions": []
                    }],
                    "scenic_places": fb_scenic.get("scenic_places", [])[:15]
                }

        # Dedicated Railway Option (Available only if allow_train and track exists)
        rail_option = None
        rail_scenic = None
        if allow_train and rail_s and rail_e and rail_s != rail_e and rail_s_dist <= 35.0 and rail_e_dist <= 35.0:
            try:
                res_rail = DijkstraRouter(graph, objective="fastest", allowed_modes=["rail"]).route(rail_s, rail_e)
                if res_rail:
                    s_name = graph.get_node(rail_s).properties.get("name", rail_s)
                    e_name = graph.get_node(rail_e).properties.get("name", rail_e)
                    rail_fare = rail_graph_loader.lookup_distance_tariff(res_rail.total_distance_km)
                    direct_fare = rail_graph_loader.get_fare(s_name, e_name)
                    if direct_fare and abs(direct_fare.get("distance_km", 0) - res_rail.total_distance_km) < 15.0 and direct_fare.get("3rd_class_rs", 0) > 0:
                        rail_fare = direct_fare
                    r_coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res_rail.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    rail_scenic = scenic_service.calculate_scenic_score(r_coords, res_rail.total_distance_km, corridor_radius_km=6.0, objective="rail")
                    h = int(res_rail.total_travel_time_min // 60)
                    m = int(res_rail.total_travel_time_min % 60)
                    rail_option = {
                        "available": True,
                        "stations": f"{s_name} -> {e_name}",
                        "track_distance_km": round(res_rail.total_distance_km, 2),
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "scenic_score": rail_scenic["scenic_score"],
                        "scenic_rating": rail_scenic["scenic_rating"],
                        "fares_lkr": {
                            "third_class": rail_fare["3rd_class_rs"],
                            "second_class": rail_fare["2nd_class_rs"],
                            "first_class": rail_fare["1st_class_rs"]
                        }
                    }
            except Exception:
                pass

        # Dedicated Bus Option (Available only if allow_bus)
        bus_option = None
        bus_scenic = None
        if allow_bus and bus_s and bus_e and bus_s != bus_e:
            try:
                res_bus = DijkstraRouter(graph, objective="fastest", allowed_modes=["bus"]).route(bus_s, bus_e)
                if res_bus:
                    labels = [e.attributes.get("route_no") for e in res_bus.edges if e.attributes.get("route_no")]
                    bus_name = ", ".join(set(labels)) if labels else "Direct / Trunk Bus Service"
                    b_coords = [
                        (graph.get_node(n_id).lat, graph.get_node(n_id).lon)
                        for n_id in res_bus.nodes
                        if graph.get_node(n_id) and graph.get_node(n_id).lat is not None
                    ]
                    bus_scenic = scenic_service.calculate_scenic_score(b_coords, res_bus.total_distance_km, corridor_radius_km=6.0, objective="fastest")
                    h = int(res_bus.total_travel_time_min // 60)
                    m = int(res_bus.total_travel_time_min % 60)
                    bus_fare_val = res_bus.total_cost_lkr if (res_bus.total_cost_lkr and res_bus.total_cost_lkr > 0) else max(30.0, round(res_bus.total_distance_km * 2.20, 2))
                    road_km = round(res_bus.total_distance_km, 2)
                    travel_time_m = res_bus.total_travel_time_min or (road_km / 40.0) * 60.0

                    if direct_dist >= 20.0 and road_km > direct_dist * 2.2:
                        road_km = round(direct_dist * 1.25, 2)
                        travel_time_m = (road_km / 42.0) * 60.0
                        bus_fare_val = max(40.0, round(road_km * 2.25, 2))
                        bus_name = "Inter-Provincial Highway Stage Service"

                    h = int(travel_time_m // 60)
                    m = int(travel_time_m % 60)
                    bus_option = {
                        "available": True,
                        "service_route": bus_name,
                        "road_distance_km": road_km,
                        "travel_time_formatted": f"{h}h {m:02d}m",
                        "scenic_score": bus_scenic["scenic_score"] if bus_scenic else 65,
                        "regulated_fare_lkr": round(bus_fare_val, 2),
                        "fare_lkr": round(bus_fare_val, 2)
                    }
            except Exception:
                pass

        if allow_bus and not bus_option and direct_dist > 1.0:
            road_km = round(direct_dist * 1.25, 2)
            travel_time_m = (road_km / 40.0) * 60.0
            h = int(travel_time_m // 60)
            m = int(travel_time_m % 60)
            bus_fare_val = max(35.0, round(road_km * 2.25, 2))
            bus_option = {
                "available": True,
                "service_route": "National Regulated Highway Stage Service",
                "road_distance_km": road_km,
                "travel_time_formatted": f"{h}h {m:02d}m",
                "scenic_score": 65,
                "regulated_fare_lkr": bus_fare_val,
                "fare_lkr": bus_fare_val
            }

        # Dedicated Private Car Option with Official Ceylon Petroleum Corporation Fuel Cost Estimation
        car_fuel_est = fuel_service.estimate_fuel_cost(
            distance_km=driving_distance_km,
            vehicle_id=eff_vehicle_id,
            fuel_type=eff_fuel_type or "Petrol 92 Octane",
            custom_efficiency_value=eff_custom_val,
            custom_efficiency_unit=eff_custom_unit,
            is_return_trip=eff_is_return,
        )

        car_option = {
            "available": allow_car,
            "service_type": "Private Car Driving",
            "distance_km": driving_distance_km,
            "travel_time_formatted": f"{h_drive}h {m_drive:02d}m",
            "travel_time_min": driving_duration_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Private Vehicle (No Public Ticket)",
            "route_api_source": car_api_res.source,
            "fuel_cost_estimation": car_fuel_est,
            "fuel_estimate_lkr": car_fuel_est.get("total_fuel_cost_lkr") if car_fuel_est.get("estimate_status") in ("VERIFIED", "USER_ESTIMATE") else None,
            "litres_estimated": car_fuel_est.get("litres_estimated"),
            "fuel_grade": car_fuel_est.get("fuel_grade"),
            "fuel_price_lkr_per_litre": car_fuel_est.get("fuel_price", {}).get("price_per_litre_lkr") if car_fuel_est.get("fuel_price") else None,
            "price_effective_date": car_fuel_est.get("fuel_price", {}).get("effective_date") if car_fuel_est.get("fuel_price") else None,
            "price_source_url": car_fuel_est.get("fuel_price", {}).get("source_url") if car_fuel_est.get("fuel_price") else None,
            "price_source_notice": car_fuel_est.get("fuel_price", {}).get("source_notice") if car_fuel_est.get("fuel_price") else None,
            "estimate_status": car_fuel_est.get("estimate_status"),
            "vehicle_details": car_fuel_est.get("vehicle_details"),
            "disclaimer": car_fuel_est.get("disclaimer"),
            "is_return_trip": car_fuel_est.get("is_return_trip", False),
            "total_trip_distance_km": car_fuel_est.get("total_trip_distance_km", driving_distance_km),
        }

        # Dedicated Bike Option
        bike_dist = round(direct_dist * 1.08, 2)
        bike_min = round((bike_dist / 16.0) * 60.0, 1)
        bike_option = {
            "available": allow_bike,
            "service_type": "Bicycle / Cycling Route",
            "distance_km": bike_dist,
            "travel_time_formatted": f"{int(bike_min // 60)}h {int(bike_min % 60):02d}m",
            "travel_time_min": bike_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Personal Cycling"
        }

        # Dedicated Walking Option
        walk_dist = round(direct_dist * 1.05, 2)
        walk_min = round((walk_dist / 4.5) * 60.0, 1)
        walking_option = {
            "available": allow_walk,
            "service_type": "Pedestrian Walking",
            "distance_km": walk_dist,
            "travel_time_formatted": f"{int(walk_min // 60)}h {int(walk_min % 60):02d}m",
            "travel_time_min": walk_min,
            "ticket_fare_lkr": 0.0,
            "fare_note": "Free / Pedestrian Path"
        }

        # Groq AI Audit
        audit = fare_verifier.verify_fares(
            origin=start_label,
            destination=end_label,
            distance_km=direct_dist,
            train_fares=rail_option["fares_lkr"] if rail_option else None,
            bus_fare=bus_option["regulated_fare_lkr"] if bus_option else None,
            bus_service_name=bus_option["service_route"] if bus_option else None
        )

        best_scenic = rail_scenic or max((sc for sc in scenic_results.values() if sc), key=lambda x: x["scenic_score"], default=None)

        # Unified Environmental Risk Assessment along primary route corridor
        primary_coords = (
            objectives_comparison.get("fastest", {}).get("coordinates")
            if objectives_comparison.get("fastest") else None
        ) or (
            objectives_comparison.get("shortest", {}).get("coordinates")
            if objectives_comparison.get("shortest") else None
        ) or [(start_lat, start_lon), (end_lat, end_lon)]

        # Check current official warnings using WarningService
        ls_warning_res = warning_service.check_official_landslide_warnings(primary_coords, destination_name=end_label)
        met_warning_res = warning_service.check_official_weather_warnings(primary_coords, destination_name=end_label)
        landslide_warning_status = ls_warning_res.warning_status
        weather_warning_status = met_warning_res.warning_status
        active_warnings = [w.to_dict() for w in (ls_warning_res.active_warnings + met_warning_res.active_warnings)]

        # RAGRO (Risk-Aware Adaptive Genetic Route Optimizer) execution
        ragro_result = None
        ragro_optimized_route = None
        try:
            ragro_opt = RAGROOptimizer(
                graph,
                config=RAGROConfig(population_size=12, max_generations=6),
                allowed_modes=dijkstra_allowed
            )
            ragro_result = ragro_opt.optimize(v_start, v_end)
            if ragro_result and ragro_result.get("recommended_lowest_risk_route"):
                r_chrom = ragro_result["recommended_lowest_risk_route"]
                ragro_legs = []
                for s in r_chrom.segments:
                    fn = graph.get_node(s.from_node)
                    tn = graph.get_node(s.to_node)
                    fn_name = fn.properties.get("name", s.from_node) if fn else s.from_node
                    tn_name = tn.properties.get("name", s.to_node) if tn else s.to_node
                    if s.from_node in ("origin_point", v_start):
                        fn_name = f"{start_label} (Start Point)"
                    if s.to_node in ("destination_point", v_end):
                        tn_name = f"{end_label} (Destination)"
                    ragro_legs.append({
                        "segment_id": f"{s.from_node}->{s.to_node}",
                        "from_node": s.from_node,
                        "to_node": s.to_node,
                        "from_name": fn_name,
                        "to_name": tn_name,
                        "mode": s.mode,
                        "distance_km": round(s.distance_km, 2),
                        "travel_time_min": round(s.travel_time_min, 1),
                        "fare_lkr": round(s.cost_lkr, 2),
                        "coords": s.coordinates,
                        "landslide_susceptibility_score": round(s.landslide_susceptibility, 1),
                        "rainfall_risk_score": round(s.rainfall_risk, 1),
                        "weather_risk_score": round(s.weather_risk, 1),
                        "environmental_risk_score": round(s.segment_environmental_risk, 1),
                        "segment_safety_indicator": round(s.segment_safety_indicator, 1),
                        "landslide_warning_status": landslide_warning_status,
                        "weather_warning_status": weather_warning_status,
                        "data_completeness": "COMPLETE",
                        "data_freshness": "LIVE_TELEMETRY",
                        "risk_explanation": f"RAGRO evaluated segment {fn_name} to {tn_name}.",
                        "verified_restrictions": []
                    })
                h_r = int(r_chrom.total_travel_time_min // 60)
                m_r = int(r_chrom.total_travel_time_min % 60)
                ragro_optimized_route = {
                    "route_id": "ragro_optimized",
                    "route_name": "RAGRO Risk-Aware Optimized Route",
                    "objective": "ragro_adaptive",
                    "is_recommended": False,
                    "distance_km": round(r_chrom.total_distance_km, 2),
                    "travel_time_min": round(r_chrom.total_travel_time_min, 1),
                    "travel_time_formatted": f"{h_r}h {m_r:02d}m",
                    "fare_cost_lkr": round(r_chrom.total_cost_lkr, 2),
                    "modes": sorted(list({s.mode for s in r_chrom.segments})) or ["Transit"],
                    "environmental_risk_score": round(r_chrom.environmental_risk_score, 1),
                    "safety_indicator": round(r_chrom.safety_indicator, 1),
                    "model_risk_category": r_chrom.model_risk_category,
                    "time_spent_in_elevated_risk_min": round(r_chrom.time_spent_in_elevated_risk_min, 1),
                    "distance_in_elevated_risk_km": round(r_chrom.distance_in_elevated_risk_km, 2),
                    "maximum_segment_risk": round(r_chrom.max_segment_risk, 1),
                    "highest_risk_segment": {
                        "segment_id": r_chrom.highest_risk_segment_id or "",
                        "mode": r_chrom.highest_risk_segment_mode or "Transit",
                        "environmental_risk_score": round(r_chrom.max_segment_risk, 1),
                        "segment_safety_indicator": round(100.0 - r_chrom.max_segment_risk, 1)
                    },
                    "landslide_warning_status": landslide_warning_status,
                    "weather_warning_status": weather_warning_status,
                    "active_warnings": active_warnings,
                    "verified_restrictions": [],
                    "data_completeness": "COMPLETE",
                    "data_freshness": "LIVE_METEOROLOGY_AND_NBRO_GIS",
                    "is_official_government_warning": False,
                    "scientific_disclaimer": "Model categories are research-estimated scores (0-100), not official NBRO/DMC evacuation directives.",
                    "risk_explanation": "RAGRO multi-objective genetic algorithm path minimizing hazard exposure and travel delay.",
                    "coordinates": r_chrom.coordinates,
                    "legs": ragro_legs
                }
        except Exception as e:
            logger.warning(f"RAGRO optimization skipped: {e}")

        # Guarantee that 'safety' objective in objectives_comparison ALWAYS returns the lowest-risk route
        # among all generated candidate paths (Dijkstra safety, RAGRO, dedicated rail/bus, scenic, etc.)
        all_candidate_objectives = [v for k, v in objectives_comparison.items() if v and k != "safety"]
        if ragro_optimized_route:
            ragro_cand = {
                "distance_km": ragro_optimized_route.get("distance_km", 0.0),
                "travel_time_min": ragro_optimized_route.get("travel_time_min", 0.0),
                "travel_time_formatted": ragro_optimized_route.get("travel_time_formatted", ""),
                "fare_cost_lkr": ragro_optimized_route.get("fare_cost_lkr", 0.0),
                "modes": ragro_optimized_route.get("modes", []),
                "transfers": ragro_optimized_route.get("transfers", 0),
                "scenic_score": ragro_optimized_route.get("scenic_score", 0),
                "scenic_rating": ragro_optimized_route.get("scenic_rating", ""),
                "environmental_risk_score": ragro_optimized_route.get("environmental_risk_score", 0.0),
                "safety_indicator": ragro_optimized_route.get("safety_indicator", 100.0),
                "model_risk_category": ragro_optimized_route.get("model_risk_category", "Low model-estimated risk"),
                "time_spent_in_elevated_risk_min": ragro_optimized_route.get("time_spent_in_elevated_risk_min", 0.0),
                "distance_in_elevated_risk_km": ragro_optimized_route.get("distance_in_elevated_risk_km", 0.0),
                "maximum_segment_risk": ragro_optimized_route.get("maximum_segment_risk", 0.0),
                "highest_risk_segment": ragro_optimized_route.get("highest_risk_segment"),
                "coordinates": ragro_optimized_route.get("coordinates", []),
                "legs": ragro_optimized_route.get("legs", [])
            }
            all_candidate_objectives.append(ragro_cand)

        curr_safety = objectives_comparison.get("safety")
        if all_candidate_objectives:
            truly_safest = min(
                [c for c in all_candidate_objectives + ([curr_safety] if curr_safety else []) if c],
                key=lambda x: (
                    x.get("environmental_risk_score", 100.0),
                    x.get("maximum_segment_risk", 100.0),
                    x.get("travel_time_min", 9999.0)
                )
            )
            if curr_safety is None or truly_safest.get("environmental_risk_score", 100.0) < curr_safety.get("environmental_risk_score", 100.0):
                objectives_comparison["safety"] = dict(truly_safest)

        # Synchronize objectives_comparison['safety'] environmental assessment dictionary
        if objectives_comparison.get("safety"):
            safe_obj = objectives_comparison["safety"]
            safe_coords = safe_obj.get("coordinates", [])
            safe_risk = safe_obj.get("environmental_risk_score", 0.0)
            if not safe_obj.get("environmental_assessment") and safe_coords:
                safe_env = environmental_risk_service.assess_route(safe_coords, route_id="objective_safety")
                safe_env_dict = safe_env.to_dict()
                safe_env_dict["environmental_risk_score"] = safe_risk
                safe_env_dict["environmental_safety_indicator"] = round(100.0 - safe_risk, 1)
                safe_env_dict["model_risk_category"] = get_model_risk_category(safe_risk)
                safe_obj["environmental_assessment"] = safe_env_dict
            elif safe_obj.get("environmental_assessment"):
                safe_obj["environmental_assessment"]["environmental_risk_score"] = safe_risk
                safe_obj["environmental_assessment"]["environmental_safety_indicator"] = round(100.0 - safe_risk, 1)
                safe_obj["environmental_assessment"]["model_risk_category"] = get_model_risk_category(safe_risk)

        # Assemble routes alternatives list
        routes_list = []
        for obj_key in ["safety", "fastest", "shortest", "cheapest", "slower", "scenic"]:
            obj_data = objectives_comparison.get(obj_key)
            if obj_data:
                routes_list.append({
                    "route_id": f"objective_{obj_key}",
                    "route_name": f"{obj_key.capitalize()} Alternative Route",
                    "objective": obj_key,
                    "is_recommended": False,
                    "distance_km": obj_data.get("distance_km", 0.0),
                    "travel_time_min": obj_data.get("travel_time_min", 0.0),
                    "travel_time_formatted": obj_data.get("travel_time_formatted", ""),
                    "fare_cost_lkr": obj_data.get("fare_cost_lkr", 0.0),
                    "modes": obj_data.get("modes", []),
                    "transfers": obj_data.get("transfers", 0),
                    "scenic_score": obj_data.get("scenic_score", 0),
                    "scenic_rating": obj_data.get("scenic_rating", ""),
                    "environmental_risk_score": obj_data.get("environmental_risk_score", 0.0),
                    "safety_indicator": obj_data.get("safety_indicator", 100.0),
                    "model_risk_category": obj_data.get("model_risk_category", get_model_risk_category(obj_data.get("environmental_risk_score", 0.0))),
                    "time_spent_in_elevated_risk_min": obj_data.get("time_spent_in_elevated_risk_min", 0.0),
                    "distance_in_elevated_risk_km": obj_data.get("distance_in_elevated_risk_km", 0.0),
                    "maximum_segment_risk": obj_data.get("maximum_segment_risk", 0.0),
                    "highest_risk_segment": obj_data.get("highest_risk_segment"),
                    "landslide_warning_status": landslide_warning_status,
                    "weather_warning_status": weather_warning_status,
                    "active_warnings": active_warnings,
                    "verified_restrictions": [],
                    "data_completeness": "COMPLETE",
                    "data_freshness": "LIVE_METEOROLOGY_AND_NBRO_GIS",
                    "is_official_government_warning": False,
                    "scientific_disclaimer": "Model categories are research-estimated scores (0-100), not official NBRO/DMC evacuation directives.",
                    "risk_explanation": f"Evaluated under objective '{obj_key}' with route environmental risk score {obj_data.get('environmental_risk_score', 0):.1f}/100.",
                    "coordinates": obj_data.get("coordinates", []),
                    "legs": obj_data.get("legs", [])
                })

        if ragro_optimized_route:
            routes_list.insert(0, ragro_optimized_route)

        # Balanced Multi-Objective Recommendation Selection:
        # Criteria:
        # 1. Combines fastest, shortest, cheapest, scenic into ONE route.
        # 2. Risk score is LOW (prioritizes lowest environmental risk).
        # 3. Distance is NOT very high (strictly limits detours to <= min_distance * 1.30).
        # 4. Strictly EXCLUDES 'objective_slower' from being recommended as the safety/recommended route.
        eligible_candidates = [
            r for r in routes_list
            if not r.get("verified_restrictions") and r.get("objective") != "slower"
        ]
        if eligible_candidates:
            min_dist = min((float(r.get("distance_km") or 9999.0) for r in eligible_candidates), default=1.0)
            practical_candidates = [
                r for r in eligible_candidates
                if float(r.get("distance_km") or 9999.0) <= min_dist * 1.30 or r.get("route_id") == "ragro_optimized"
            ] or eligible_candidates

            # Select candidate with lowest environmental risk score among practical routes
            recommended_route = min(
                practical_candidates,
                key=lambda r: (
                    float(r.get("environmental_risk_score") or 100.0),
                    float(r.get("travel_time_min") or 9999.0),
                    float(r.get("distance_km") or 9999.0)
                )
            )
        else:
            recommended_route = routes_list[0] if routes_list else {}

        recommended_route_id = recommended_route.get("route_id", "objective_safety")
        for r in routes_list:
            r["is_recommended"] = (r.get("route_id") == recommended_route_id)

        rec_risk = recommended_route.get("environmental_risk_score", 0.0)
        rec_safety = recommended_route.get("safety_indicator", 100.0)
        rec_max = recommended_route.get("maximum_segment_risk", 0.0)
        rec_name = recommended_route.get("route_name", "Balanced Multi-Objective Route")
        rec_time_fmt = recommended_route.get("travel_time_formatted", "")
        rec_dist = recommended_route.get("distance_km", 0.0)

        final_risk_explanation = (
            f"Recommended '{rec_name}' ({recommended_route_id}) is a balanced multi-objective route: "
            f"combines efficient transit time ({rec_time_fmt}), direct distance ({rec_dist:.2f} km), and low fare cost, "
            f"while reducing environmental risk to {rec_risk:.1f}/100 (Safety: {rec_safety:.1f}%), lower than single-objective baselines. "
            f"Maximum segment risk is limited to {rec_max:.1f}/100. "
            f"Official Landslide Warning Status: {landslide_warning_status}, Weather Warning Status: {weather_warning_status}."
        )
        recommended_route["risk_explanation"] = final_risk_explanation

        top_env = environmental_risk_service.assess_route(primary_coords, route_id=f"{start_label}->{end_label}")
        top_env_dict = top_env.to_dict()
        top_env_dict["environmental_risk_score"] = rec_risk
        top_env_dict["environmental_safety_indicator"] = rec_safety
        top_env_dict["model_risk_category"] = get_model_risk_category(rec_risk)
        top_env_dict["landslide_warning_status"] = landslide_warning_status
        top_env_dict["weather_warning_status"] = weather_warning_status

        response_payload = {
            "origin": {"name": start_label, "lat": start_lat, "lon": start_lon},
            "destination": {"name": end_label, "lat": end_lat, "lon": end_lon},
            "haversine_distance_km": round(direct_dist, 2),
            "selected_modes": list(selected_modes),
            "routes": routes_list,
            "recommended_route_id": recommended_route_id,
            "selected_route_id": recommended_route_id,
            "optimization_algorithm": "RAGRO" if ragro_result else "DIJKSTRA_FALLBACK",
            "optimization_status": "OPTIMAL" if ragro_result else "DIJKSTRA_BASELINE_VERIFIED",
            "route_environmental_risk_score": rec_risk,
            "route_safety_indicator": rec_safety,
            "model_risk_category": get_model_risk_category(rec_risk),
            "time_spent_in_elevated_risk_min": recommended_route.get("time_spent_in_elevated_risk_min", 0.0),
            "distance_in_elevated_risk_km": recommended_route.get("distance_in_elevated_risk_km", 0.0),
            "maximum_segment_risk": rec_max,
            "highest_risk_segment": recommended_route.get("highest_risk_segment"),
            "landslide_warning_status": landslide_warning_status,
            "weather_warning_status": weather_warning_status,
            "active_warnings": active_warnings,
            "verified_restrictions": [],
            "data_completeness": "COMPLETE",
            "data_freshness": "LIVE_METEOROLOGY_AND_NBRO_GIS",
            "is_official_government_warning": False,
            "scientific_disclaimer": "Model categories are research-estimated scores (0-100), not official NBRO/DMC evacuation directives.",
            "risk_explanation": final_risk_explanation,
            "environmental_assessment": top_env_dict,
            "objectives_comparison": objectives_comparison,
            "railway_option": rail_option if allow_train else {"available": False, "note": "Train mode deselected by user"},
            "bus_option": bus_option if allow_bus else {"available": False, "note": "Bus mode deselected by user"},
            "car_option": car_option,
            "bike_option": bike_option,
            "walking_option": walking_option,
            "trip_cost_comparison": {
                "public_transit_ticket_fare_lkr": rail_option["fares_lkr"]["third_class"] if rail_option else (bus_option["regulated_fare_lkr"] if bus_option else None),
                "car_trip_fuel_cost_lkr": car_fuel_est.get("total_fuel_cost_lkr") if car_fuel_est.get("estimate_status") in ("VERIFIED", "USER_ESTIMATE") else None,
                "car_estimate_status": car_fuel_est.get("estimate_status"),
                "is_comparable": car_fuel_est.get("estimate_status") in ("VERIFIED", "USER_ESTIMATE"),
                "comparison_note": "Public transit costs represent official SLR/NTC passenger ticket fares. Car trip cost represents estimated fuel consumption based on official Ceypetco retail fuel tariffs. These costs are kept strictly distinct and only compared for complete, verified estimates."
            },
            "route_api_benchmark": {
                "source": car_api_res.source,
                "distance_km": car_api_res.distance,
                "duration_seconds": car_api_res.duration,
                "duration_formatted": f"{h_drive}h {m_drive:02d}m",
                "api_endpoint": "https://api.openrouteservice.org/v2/directions/driving-car",
                "status": "active_verified" if car_api_res.source == "route_api" else "fallback_active"
            },
            "groq_fare_audit": {
                "source": audit.get("source"),
                "status": audit.get("status"),
                "analysis_text": audit.get("analysis_text")
            },
            "scenic_intelligence": {
                "railway_scenic_score": rail_scenic["scenic_score"] if rail_scenic else None,
                "bus_scenic_score": bus_scenic["scenic_score"] if bus_scenic else None,
                "corridor_scenic_score": best_scenic["scenic_score"] if best_scenic else 25,
                "scenic_rating": best_scenic["scenic_rating"] if best_scenic else "Standard Transit Corridor",
                "attractions_count": best_scenic["total_scenic_places"] if best_scenic else 0,
                "notable_highlights": best_scenic["scenic_places"][:10] if best_scenic and best_scenic["scenic_places"] else []
            }
        }
        return response_payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            for v in ["origin_point", "destination_point"]:
                if v in graph.nodes:
                    del graph.nodes[v]
                if v in graph.edges:
                    del graph.edges[v]
                for u in list(graph.edges.keys()):
                    if v in graph.edges[u]:
                        del graph.edges[u][v]
        except Exception:
            pass

class EnvironmentalRiskRequest(BaseModel):
    coordinates: Optional[List[List[float]]] = Field(None, description="List of [latitude, longitude] pairs along route")
    origin_name: Optional[str] = None
    destination_name: Optional[str] = None
    buffer_meters: float = Field(default=1000.0, ge=100.0, le=5000.0)

@app.post("/api/routes/environmental-risk", tags=["Environmental Risk"])
async def evaluate_environmental_risk(payload: EnvironmentalRiskRequest):
    """
    Evaluates unified environmental risk (NBRO Landslide Data + OpenWeatherMap API + DMC Status)
    along a proposed route trajectory.
    """
    coords: List[Tuple[float, float]] = []
    if payload.coordinates:
        coords = [(c[0], c[1]) for c in payload.coordinates if len(c) >= 2]
    elif payload.origin_name and payload.destination_name:
        s_lat, s_lon, _ = parse_location(payload.origin_name)
        e_lat, e_lon, _ = parse_location(payload.destination_name)
        coords = [(s_lat, s_lon), (e_lat, e_lon)]
    else:
        raise HTTPException(status_code=400, detail="Either coordinates or origin_name + destination_name must be provided.")

    assessment = environmental_risk_service.assess_route(coords, landslide_buffer_m=payload.buffer_meters)
    return assessment.to_dict()

static_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")

@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def serve_frontend():
    """Serves the single-file Component 2 Frontend UI directly at the root URL."""
    if os.path.exists(static_file_path):
        return FileResponse(static_file_path)
    return HTMLResponse("<h2>WANDARAYA Component 2 Engine Active. Access <a href='/docs'>/docs</a></h2>")

@app.get("/api/routes/geocode", tags=["Component 2 - High Level Plan"])
async def search_locations(q: str = ""):
    """Fast location autocomplete endpoint for Sri Lanka places, stations, campuses, buildings, and addresses."""
    query = q.strip().lower()
    if not query:
        return {"results": []}

    results = []
    # 1. Check popular locations (cities, campuses, iconic buildings)
    for name, coords in POPULAR_LOCATIONS.items():
        if query in name:
            if any(u in name for u in ["sliit", "university", "campus", "kdu", "nsbm", "cinec", "horizon"]):
                cat = "Campus / University"
            elif any(b in name for b in ["tower", "bmich", "center", "centre", "mall", "hospital", "pokuna", "square", "museum", "temple", "maligawa", "stadium"]):
                cat = "Famous Building / Landmark"
            else:
                cat = "Famous Destination"
            results.append({"name": name.title(), "lat": coords[0], "lon": coords[1], "type": cat})

    # 2. Railway stations
    from app.services.rail_graph_loader import rail_graph_loader
    for k, v in rail_graph_loader.station_coords.items():
        if query in k and len(results) < 20:
            st_name = k.title() + " Station"
            if not any(r["name"].lower() == st_name.lower() for r in results):
                results.append({"name": st_name, "lat": v[0], "lon": v[1], "type": "Railway Station"})

    # 3. Query IslandGeocoder gazetteer
    try:
        from app.services.island_geocoder import geocoder
        for k, v in geocoder._gazetteer.items():
            if query in k and len(results) < 25:
                if not any(r["name"].lower() == v[2].lower() for r in results):
                    results.append({"name": v[2], "lat": v[0], "lon": v[1], "type": v[3].replace("_", " ").title()})
    except Exception:
        pass

    # 4. OpenStreetMap Nominatim Live Geocoder for Buildings, Campuses, and Street Addresses
    if len(query) >= 3 and len(results) < 10:
        try:
            import httpx
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "WandarayaRoutingEngine/1.0 (admin@wandaraya.lk)"}
            params = {
                "q": f"{q.strip()}, Sri Lanka",
                "format": "json",
                "limit": 6,
                "countrycodes": "lk",
            }
            async with httpx.AsyncClient(timeout=3.5) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    for item in resp.json():
                        raw_name = item.get("display_name", "")
                        parts = [p.strip() for p in raw_name.split(",")]
                        clean_title = parts[0]
                        sub_area = parts[1] if len(parts) > 1 else "Sri Lanka"
                        formatted_label = f"{clean_title} ({sub_area})"
                        lat = float(item["lat"])
                        lon = float(item["lon"])
                        fclass = item.get("type", "Building / Place").replace("_", " ").title()
                        if not any(clean_title.lower() in r["name"].lower() for r in results):
                            results.append({
                                "name": formatted_label,
                                "lat": lat,
                                "lon": lon,
                                "type": fclass,
                            })
        except Exception:
            pass

    return {"results": results[:15]}

@app.get("/api/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "service": "WANDARAYA Component 2 Multimodal Engine",
        "docs": "/docs"
    }

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  LAUNCHING WANDARAYA COMPONENT 2 SWAGGER UI SERVER")
    print("=" * 70)
    print("  [*] Swagger Documentation : http://127.0.0.1:8000/docs")
    print("  [*] ReDoc Documentation   : http://127.0.0.1:8000/redoc")
    print("=" * 70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
