# WANDARAYA — Component 2: Complete Architectural Specification & Feature Guide

> **Component Title**: Environmental-Risk-Aware Multimodal Route Optimization, Public Transit Tariffs (NTC/SLR), Fuel Cost Intelligence & Dynamic Hazard Warning System  
> **Author**: Research Team (J26-DS-337)  
> **Date**: October 2026  
> **Repository Path**: `wandaraya-backend/`

---

## 1. Executive Summary: What Component 2 Did & Why It Was Built

### 1.1 The Real-World Problem in Sri Lanka (Why We Built It)
Standard commercial navigation tools (such as Google Maps or Waze) plan routes primarily based on two parameters: **shortest physical distance** or **fastest travel time under normal traffic**. 

In Sri Lanka, this single-objective approach creates life-threatening situations for tourists and local commuters:
1. **Severe Geological & Monsoon Hazards**: The Central Highlands (Badulla, Nuwara Eliya, Kandy, Kegalle, Ratnapura) experience severe rainfall-triggered landslides, cut-slope failures, and rockfalls during the South-West and North-East monsoons. A route that is 10 minutes faster may cut straight through an active landslide corridor with an unstable saturated slope.
2. **Fragmented Public Transit Options**: Travelers cannot easily compare public transportation with private driving. Public bus routes under the National Transport Commission (NTC) operate under a stage-based fare system, while Sri Lanka Railways (SLR) operates on distance-tiered ticket brackets. Commuters lack a unified platform that calculates exact, regulated ticket costs.
3. **Private Vehicle Fuel Uncertainty**: Tourists hiring self-drive cars or private vans face volatile fuel prices and mountainous terrain that significantly increases fuel consumption compared to manufacturer laboratory figures.
4. **Extreme Safety Detours**: Naive hazard avoidance algorithms frequently recommend absurd 5-to-8-hour detours around entire mountain ranges just to avoid a low-risk slope, which no human driver would accept.

### 1.2 What We Built (The Solution)
**Component 2 of WANDARAYA** is an intelligent decision-support platform that unites:
* **Multimodal Graph Routing**: Walking, bicycle, public bus, passenger train, and private car routing on a single topological graph with realistic transfer penalties.
* **All 6 Routing Objectives**: Shortest, Fastest, Cheapest, Slower (Leisure), Scenic, and Safety-Aware.
* **RAGRO (Risk-Aware Adaptive Genetic Route Optimizer)**: An evolutionary genetic algorithm that navigates road closures and extreme weather by balancing safety against practical travel time.
* **Official Government Tariffs**: NTC regulated bus stage fares, SLR 1st/2nd/3rd class train fares, and Ceylon Petroleum Corporation (Ceypetco) retail fuel tariffs with vehicle consumption modeling.
* **Live Environmental Hazard Engine**: Spatial intersection with 194,016 NBRO hazard zones, 20,438 historical landslide points, and real-time rainfall telemetry from Open-Meteo.
* **Balanced Guardrails**: A strict $\le 130\%$ distance constraint that prevents impractical detours, alongside exclusion of slow leisure routes from safest recommendations.

---

## 2. System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   USER INTERFACES & CLIENTS                                      │
│     Flutter Web App (`/flutter`)               Dedicated Interactive Swagger UI (`/docs`)         │
└─────────────────────────────────┬──────────────────────────────────┬─────────────────────────────┘
                                  │                                  │
                                  ▼                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             FASTAPI BACKEND SERVICE (`scripts/run_swagger.py`)                  │
│                                                                                                  │
│   ┌────────────────────────────────────────┐    ┌────────────────────────────────────────────┐   │
│   │     MULTIMODAL GRAPH ROUTING           │    │       RAGRO GENETIC OPTIMIZER              │   │
│   │  • DijkstraRouter (6 Objectives)       │    │  • Population Crossover & Mutation         │   │
│   │  • Rail, Bus, Car, Bike, Walk          │    │  • Jaccard Diversity Adaptation            │   │
│   │  • Modal Transfer Penalties (5-10m)    │    │  • ≤ 130% Distance Bounding Constraint     │   │
│   └───────────────────┬────────────────────┘    └─────────────────────┬──────────────────────┘   │
│                       │                                               │                          │
│   ┌───────────────────▼────────────────────┐    ┌─────────────────────▼──────────────────────┐   │
│   │     ECONOMIC & TARIFF ENGINES          │    │       ENVIRONMENTAL HAZARD ENGINE          │   │
│   │  • SLR Railway Fare Loader (1/2/3 cl)  │    │  • NBRO 1:50,000 LHZM Zonation (194k pts)  │   │
│   │  • NTC Regulated Bus Stage Tariffs     │    │  • Scipy cKDTree Spatial Index (<0.5 ms)   │   │
│   │  • Ceypetco Vehicle Fuel Costing       │    │  • Open-Meteo Live Rainfall Telemetry      │   │
│   │  • Groq AI LLM Fare Verification       │    │  • WarningService (NBRO / DOM Bulletins)   │   │
│   └───────────────────┬────────────────────┘    └─────────────────────┬──────────────────────┘   │
│                       │                                               │                          │
│   ┌───────────────────▼───────────────────────────────────────────────▼──────────────────────┐   │
│   │                 MULTI-OBJECTIVE BALANCED RECOMMENDATION SELECTION                        │   │
│   │   • Top-to-Bottom Risk Score Synchronization (12.0/100 Risk ➔ 88.0% Safety)              │   │
│   │   • Exclusion of `objective_slower` from Recommended Safety Routes                       │   │
│   │   • Side-by-Side Fare vs Fuel Comparison (`trip_cost_comparison`)                        │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Feature & Sub-Feature Breakdown

---

### Feature 1: Multimodal Graph Pathfinding (Dijkstra Core)

#### Sub-Feature 1.1: All 6 Routing Objectives
* **What it does**: Computes 6 distinct routing alternatives between any valid origin and destination in Sri Lanka: `shortest` (km), `fastest` (min), `cheapest` (LKR), `slower` (scenic rural), `scenic` (landscape quality), and `safety` (minimum hazard).
* **How it works**: Uses `DijkstraRouter` with dynamic edge weight cost functions:
  $$C_{\text{shortest}}(e) = \text{Distance}(e)$$
  $$C_{\text{fastest}}(e) = \text{TravelTime}(e) + \text{TransferPenalty}(u, m)$$
  $$C_{\text{cheapest}}(e) = \text{FareLKR}(e)$$
  $$C_{\text{safety}}(e) = \text{TravelTime}(e) \times \left(1.0 + \frac{\text{EnvironmentalRisk}(e)}{25.0}\right)$$
  $$C_{\text{scenic}}(e) = \frac{\text{Distance}(e)}{\text{ScenicScore}(e) + 1.0}$$
* **Why use it**: Different travelers have conflicting priorities: business commuters need speed, backpackers need low cost, tourists want scenery, and families during monsoon season require safety.
* **Implementation Location**:
  * [app/services/dijkstra.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/dijkstra.py)
  * [scripts/run_swagger.py:L654-L885](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L654-L885)

#### Sub-Feature 1.2: Multi-Modal Graph Traversal & Network Construction
* **What it does**: Represents roads, bus lines, railway tracks, cycling paths, and walking links in a single unified graph `MultimodalGraph`.
* **How it works**: Nodes represent physical intersections, bus stops, and railway stations. Edges carry mode attributes (`GraphMode.RAIL`, `GraphMode.BUS`, `GraphMode.CAR`, `GraphMode.BIKE`, `GraphMode.WALKING`).
* **Why use it**: Realistic journey planning requires switching between modes (e.g., walking 400m to Kandy Railway Station, taking the train to Nanu Oya, and taking a local bus to Nuwara Eliya town).
* **Implementation Location**:
  * [app/services/graph.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/graph.py)
  * [scripts/run_swagger.py:L503-L622](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L503-L622)

#### Sub-Feature 1.3: Realistic Modal Transfer Delays
* **What it does**: Adds transfer penalties whenever consecutive edges change transport modes.
* **How it works**: Injects $+5.0\text{ minutes}$ for bus-to-bus transfers (waiting at bus stand) and $+10.0\text{ minutes}$ for bus-to-rail transfers (ticket buying, platform navigation).
* **Why use it**: Prevents the algorithm from suggesting impractical routes that involve 10 micro-switches between different buses to save 200 meters.
* **Implementation Location**:
  * [app/services/transfer_loader.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/transfer_loader.py)
  * [app/services/dijkstra.py:L115-L135](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/dijkstra.py#L115-L135)

#### Sub-Feature 1.4: Dynamic Virtual Terminal Access Connectors
* **What it does**: Dynamically connects arbitrary origin and destination GPS coordinates to the nearest valid transit network stops within 35 km.
* **How it works**: Generates virtual nodes `"origin_point"` and `"destination_point"`, snaps them to road/bus/rail nodes via Haversine distance, and cleans up these virtual nodes after query completion to avoid graph pollution.
* **Why use it**: Users select landmarks or hotel coordinates, not topological graph node IDs.
* **Implementation Location**:
  * [scripts/run_swagger.py:L505-L523](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L505-L523)

---

### Feature 2: RAGRO Multi-Objective Genetic Optimizer

#### Sub-Feature 2.1: Chromosome Representation & Population Seeding
* **What it does**: Formulates candidate routes as chromosomes $\mathcal{C} = [v_0, v_1, \dots, v_k]$ and seeds the initial population ($N=16$).
* **How it works**: Seeds with Pareto-optimal Dijkstra baselines (`shortest`, `fastest`, `cheapest`, `scenic`, `safety`) plus stochastic localized sub-path perturbations.
* **Why use it**: Pure random paths in a massive transportation network produce invalid disconnected routes; seeding with Dijkstra baselines ensures rapid convergence.
* **Implementation Location**:
  * [app/services/ragro.py:L76-L123](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L76-L123)
  * [app/services/ragro.py:L268-L305](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L268-L305)

#### Sub-Feature 2.2: Shared-Node Topological Crossover
* **What it does**: Breeds two parent route chromosomes to create valid offspring.
* **How it works**: Finds common intermediate intersection nodes $\mathcal{I} = (P_1 \cap P_2) \setminus \{v_{\text{start}}, v_{\text{end}}\}$. Picks a split node $v_{\text{cross}} \in \mathcal{I}$ and splices the prefix of $P_1$ with the suffix of $P_2$.
* **Why use it**: Guarantees that the resulting child path remains mathematically continuous without broken topological jumps.
* **Implementation Location**:
  * [app/services/ragro.py:L532-L558](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L532-L558)

#### Sub-Feature 2.3: Sub-Path Detour Mutation
* **What it does**: Introduces novel genetic diversity by rerouting intermediate segments.
* **How it works**: Selects two random nodes $v_a, v_b$ on chromosome $\mathcal{C}$ and finds an alternative sub-path between them using different edge modes.
* **Why use it**: Enables escaping local minima when standard corridors are obstructed by landslides or road closures.
* **Implementation Location**:
  * [app/services/ragro.py:L560-L600](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L560-L600)

#### Sub-Feature 2.4: Adaptive Jaccard Edge Diversity Scaling
* **What it does**: Dynamically adjusts crossover ($p_c$) and mutation ($p_m$) probabilities.
* **How it works**: Calculates Jaccard similarity across population edges:
  $$\text{Diversity} = 1.0 - \frac{1}{\binom{N}{2}} \sum_{i < j} \frac{|E(C_i) \cap E(C_j)|}{|E(C_i) \cup E(C_j)|}$$
  If diversity drops, mutation probability $p_m$ is boosted up to $0.60$ and crossover $p_c$ is lowered.
* **Why use it**: Prevents premature population collapse into identical clones.
* **Implementation Location**:
  * [app/services/ragro.py:L180-L187](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L180-L187)

#### Sub-Feature 2.5: Multi-Attribute Normalized Fitness Evaluation
* **What it does**: Assigns a scalar fitness score to every candidate chromosome.
* **How it works**: Evaluates normalized weighted criteria:
  $$\text{Fitness} = 0.40 \cdot \frac{\text{Risk}}{100} + 0.35 \cdot \frac{\text{Time}}{300} + 0.15 \cdot \frac{\text{Cost}}{2000} + 0.10 \cdot \frac{\text{Dist}}{200} + \text{HotspotPenalty}$$
* **Why use it**: Balances the 4 core conflicting metrics: Safety ($40\%$), Speed ($35\%$), Fare ($15\%$), and Distance ($10\%$).
* **Implementation Location**:
  * [app/services/ragro.py:L500-L526](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L500-L526)

#### Sub-Feature 2.6: Hazard Hotspot Penalty
* **What it does**: Penalizes candidate routes that pass through a localized high-risk point.
* **How it works**: Adds $(\text{MaxSegmentRisk} / 100.0) \times 0.15$ if $\text{MaxSegmentRisk} > 65.0$.
* **Why use it**: Prevents a route from being recommended if it has a low average risk but contains a single lethal landslide hotspot.
* **Implementation Location**:
  * [app/services/ragro.py:L517-L518](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L517-L518)

#### Sub-Feature 2.7: Practical Distance Detour Bounding ($\le 130\%$)
* **What it does**: Caps safe route candidates within $1.30\times$ of the shortest direct distance.
* **How it works**: Filters out candidates where $\text{distance} > \text{min\_dist} \times 1.30$.
* **Why use it**: Solves the user-reported problem where an algorithm chooses an absurd 5-hour detour just to lower a risk score from 12 to 2.
* **Implementation Location**:
  * [scripts/run_swagger.py:L1315-L1329](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1315-L1329)

#### Sub-Feature 2.8: Candidate Pool Filtering (`objective_slower` Exclusion)
* **What it does**: Excludes `objective_slower` from candidate consideration for the recommended safest route.
* **How it works**: Evaluates candidate pool: `r.get("objective") != "slower"`.
* **Why use it**: Prevents slow leisure routes through winding backroads from masquerading as safe recommendations.
* **Implementation Location**:
  * [scripts/run_swagger.py:L1312](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1312)

---

### Feature 3: Official Public Transit Tariffs (SLR & NTC)

#### Sub-Feature 3.1: Sri Lanka Railways (SLR) Distance-Tiered Tariffs
* **What it does**: Computes official passenger ticket fares for 1st, 2nd, and 3rd class travel across 300+ train stations.
* **How it works**: Looks up track distance against official gazetted fare brackets:
  $$\text{Fare}(d) = \text{lookup\_distance\_tariff}(\text{total\_rail\_km})$$
* **Why use it**: In Sri Lanka, train tickets are strictly regulated by track distance rather than dynamic airline-style pricing.
* **Implementation Location**:
  * [app/services/rail_graph_loader.py:L90-L150](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/rail_graph_loader.py#L90-L150)
  * [scripts/run_swagger.py:L676-L685](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L676-L685)

#### Sub-Feature 3.2: NTC Regulated Bus Stage Tariffs
* **What it does**: Ingests the 60,967-row National Transport Commission bus fare stage schedule.
* **How it works**: Resolves the boarding stage and alighting stage on inter-provincial trunk routes to calculate the exact passenger fare.
* **Why use it**: Sri Lankan buses charge by discrete fare stages (Stage 1, Stage 2, etc.) rather than continuous GPS meters.
* **Implementation Location**:
  * [app/services/bus_graph_loader.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/bus_graph_loader.py)
  * [scripts/run_swagger.py:L686-L693](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L686-L693)

#### Sub-Feature 3.3: National Bus Fallback Formula
* **What it does**: Provides a guaranteed fallback tariff for local or unmapped rural bus routes.
* **How it works**: Applies the official baseline formula:
  $$\text{BusFare} = \max(35.0, \text{total\_bus\_km} \times 2.25\text{ LKR})$$
* **Why use it**: Ensures the API never crashes or returns null fares for remote provincial routes.
* **Implementation Location**:
  * [scripts/run_swagger.py:L692](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L692)

#### Sub-Feature 3.4: Multimodal Journey Ticket Totaling
* **What it does**: Computes the unified passenger ticket fare across transfers while setting ticket fares to 0.0 LKR for private transport (car, bike, walk).
* **How it works**: Sums public transit ticket segments while ensuring car legs do not charge ticket prices.
* **Why use it**: Prevents misleading representations where driving a private car shows a public passenger ticket fare.
* **Implementation Location**:
  * [scripts/run_swagger.py:L694-L696](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L694-L696)
  * [scripts/run_swagger.py:L820-L824](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L820-L824)

---

### Feature 4: Live AI Fare Audit & Verification

#### Sub-Feature 4.1: Groq Cloud LLM Inference Engine
* **What it does**: Submits computed origin, destination, road distance, and public fares to Groq Cloud (`openai/gpt-oss-20b`).
* **How it works**: Formulates an analytical prompt with NTC/SLR gazette context and queries Groq with sub-second latency.
* **Why use it**: Provides real-time regulatory compliance checking and flags potential fare overcharges.
* **Implementation Location**:
  * [app/services/fare_verifier.py:L40-L160](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fare_verifier.py#L40-L160)
  * [scripts/run_swagger.py:L1097-L1105](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1097-L1105)

#### Sub-Feature 4.2: Audit Citations & Discrepancy Tolerance Detection
* **What it does**: Compares calculated fares against official gazettes, outputting a verification status (`AUDIT_VERIFIED`), discrepancy percentage, and legal citation.
* **How it works**: Evaluates tolerance thresholds ($\le 10\%$) and extracts official gazette references.
* **Why use it**: Eliminates LLM hallucinations by enforcing strict numeric tolerance gates.
* **Implementation Location**:
  * [app/services/fare_verifier.py:L115-L155](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fare_verifier.py#L115-L155)

---

### Feature 5: Private Vehicle Fuel Costing (Ceypetco)

#### Sub-Feature 5.1: Ceypetco Official Retail Tariffs
* **What it does**: Ingests active retail fuel tariffs from the Ceylon Petroleum Corporation (Petrol 92: 414 LKR, Petrol 95: 475 LKR, Auto Diesel: 392 LKR, Super Diesel: 528 LKR, Kerosene: 285 LKR).
* **How it works**: Maintains verified tariff structures with effective dates and official Ministry revision notice citations.
* **Why use it**: Accurately reflects Sri Lanka's national fuel pricing formula.
* **Implementation Location**:
  * [app/services/fuel_service.py:L20-L68](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L20-L68)

#### Sub-Feature 5.2: Vehicle Fleet Catalog & Local Adjustment Factor
* **What it does**: Catalogs popular Sri Lankan models (Suzuki Alto, Wagon R, Toyota Aqua, Prius, Hilux, KDH, CT100, Bajaj RE).
* **How it works**: Normalizes manufacturer lab figures (WLTP/JC08/ARAI) by applying real-world Sri Lankan urban congestion and hill-climb degradation factors.
* **Why use it**: Factory specifications overestimate fuel economy under Sri Lankan traffic conditions.
* **Implementation Location**:
  * [app/services/fuel_service.py:L120-L240](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L120-L240)

#### Sub-Feature 5.3: Bidirectional Efficiency Unit Conversion
* **What it does**: Seamlessly converts between $\text{km/L}$ and $\text{L}/100\text{km}$.
* **How it works**:
  $$\text{km/L} = \frac{100}{\text{L}/100\text{km}}$$
* **Why use it**: Japanese imports typically display $\text{km/L}$, while European vehicles use $\text{L}/100\text{km}$.
* **Implementation Location**:
  * [app/services/fuel_service.py:L280-L310](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L280-L310)

#### Sub-Feature 5.4: One-Way vs. Return-Trip Fuel Estimation
* **What it does**: Computes estimated liters required and total fuel cost for single or round trips.
* **How it works**: Multiplies distance by $2.0$ when `is_return_trip=True`.
* **Why use it**: Tourists planning day trips need round-trip fuel budgeting.
* **Implementation Location**:
  * [app/services/fuel_service.py:L350-L460](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L350-L460)

#### Sub-Feature 5.5: Public Transit vs. Car Fuel Cost Segregation
* **What it does**: Distinguishes public transit tickets from private car fuel expenses in `trip_cost_comparison`.
* **How it works**: Keeps car ticket fare strictly at 0.0 LKR and compares passenger ticket costs against total vehicle fuel consumption.
* **Why use it**: Prevents misleading comparisons between an individual bus ticket (e.g., 270 LKR) and an entire car's fuel burn (e.g., 3,200 LKR).
* **Implementation Location**:
  * [scripts/run_swagger.py:L1394-L1400](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1394-L1400)

---

### Feature 6: Environmental Hazard & Landslide Risk Assessment

#### Sub-Feature 6.1: PostGIS Geological Hazard Ingestion & CRS Transformation
* **What it does**: Ingests 194,016 NBRO hazard zones, 20,438 incidents, and 1,967 polygons into PostgreSQL/PostGIS.
* **How it works**: Uses `pyproj` to transform coordinates from Sri Lanka Grid 1999 (EPSG:5234, meters) to WGS-84 (EPSG:4326, degrees).
* **Why use it**: Government survey data is published in local grid projections that must be converted for GPS mapping.
* **Implementation Location**:
  * [scripts/import_nbro_hazard_zones.py:L110-L140](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/import_nbro_hazard_zones.py#L110-L140)

#### Sub-Feature 6.2: Sub-Millisecond Spatial Lookups (Scipy `cKDTree`)
* **What it does**: Performs nearest-neighbor hazard lookups in $<0.5\text{ ms}$ per coordinate.
* **How it works**: Builds an in-memory $k$-d tree over all 194,016 points transformed to radians on a unit sphere.
* **Why use it**: Live routing queries evaluate hundreds of waypoints; querying the database repeatedly creates multi-second latencies.
* **Implementation Location**:
  * [app/services/landslide_service.py:L150-L240](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/landslide_service.py#L150-L240)

#### Sub-Feature 6.3: Dynamic Landslide & Rainfall Formula
* **What it does**: Evaluates slope failure risk by combining geological susceptibility ($L$) with live rainfall ($R$).
* **How it works**:
  $$\text{DynamicLandslideScore} = 0.60 \times L + 0.40 \times R$$
* **Why use it**: An unstable slope is safe during a drought, but becomes hazardous after $75\text{ mm}$ of monsoonal rain.
* **Implementation Location**:
  * [app/services/environmental_risk_service.py:L390-L392](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/environmental_risk_service.py#L390-L392)
  * [scripts/run_swagger.py:L783](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L783)

#### Sub-Feature 6.4: Segment Environmental Risk Formula
* **What it does**: Computes individual segment hazard:
  $$\text{SegmentRisk} = 0.60 \times \text{DynamicLandslideScore} + 0.40 \times W = 0.36 \cdot L_{\text{mode}} + 0.24 \cdot R + 0.40 \cdot W$$
* **How it works**: Combines slope stability with atmospheric weather ($W$, wind/visibility/thunderstorms).
* **Why use it**: Provides granular risk indicators for every leg of the journey.
* **Implementation Location**:
  * [scripts/run_swagger.py:L784](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L784)
  * [app/services/ragro.py:L420](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L420)

#### Sub-Feature 6.5: Regional Weight Calibration (Hill Country vs. Lowland)
* **What it does**: Adjusts risk weighting based on topography.
* **How it works**:
  * Hill Country ($70\%$ Landslide / $30\%$ Weather).
  * Lowland / Coastal ($30\%$ Landslide / $70\%$ Weather).
* **Why use it**: Landslides do not occur in flat coastal plains like Galle or Colombo, where monsoon flooding is the primary hazard.
* **Implementation Location**:
  * [app/services/environmental_risk_service.py:L310-L345](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/environmental_risk_service.py#L310-L345)

#### Sub-Feature 6.6: Transport Mode Hazard Attenuation Factors
* **What it does**: Differentiates hazard exposure by transport mode.
* **How it works**: Scales base susceptibility by mode multipliers: Rail ($0.65\times$), Car ($0.80\times$), Bus ($1.00\times$).
* **Why use it**: Trains on engineered rights-of-way have lower slip vulnerability than overloaded buses navigating mountain hairpins.
* **Implementation Location**:
  * [scripts/run_swagger.py:L642-L648](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L642-L648)

#### Sub-Feature 6.7: Route-Level Travel-Time Weighted Aggregation & Safety Indicator
* **What it does**: Aggregates segment risks into a unified route score and complementary safety indicator.
* **How it works**:
  $$\text{RouteRisk} = \frac{\sum (\text{SegmentRisk}_i \times \text{TravelTime}_i)}{\sum \text{TravelTime}_i}, \quad \text{SafetyIndicator} = 100.0 - \text{RouteRisk}$$
* **Why use it**: Risk exposure is a function of duration spent in the hazard zone.
* **Implementation Location**:
  * [app/services/environmental_risk_service.py:L346-L362](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/environmental_risk_service.py#L346-L362)
  * [scripts/run_swagger.py:L835-L840](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L835-L840)

#### Sub-Feature 6.8: Research Risk vs. Official Warning Segregation
* **What it does**: Flags statistical research scores ($0-100$) separately from official government directives (`is_official_government_warning: false`).
* **How it works**: Returns explicit disclaimers alongside numerical scores.
* **Why use it**: Prevents legal liability and avoids confusing research models with official DMC evacuation orders.
* **Implementation Location**:
  * [scripts/run_swagger.py:L1199-L1200](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1199-L1200)

---

### Feature 7: Official Hazard Warning Service

#### Sub-Feature 7.1: NBRO Landslide Early Warning Bulletins Verification
* **What it does**: Checks official advisories issued by the NBRO Landslide Early Warning Centre across 10 vulnerable hill-country districts.
* **How it works**: Evaluates active spatial district envelopes and matches official alerts.
* **Why use it**: Incorporates verified government warning levels (Yellow Watch, Amber Alert, Red Evacuation).
* **Implementation Location**:
  * [app/services/warning_service.py:L40-L150](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/warning_service.py#L40-L150)

#### Sub-Feature 7.2: Standardized 3-State Warning Status
* **What it does**: Enforces a strict 3-state output status:
  * `ACTIVE_WARNING`
  * `NO_ACTIVE_WARNING_FOUND`
  * `WARNING_STATUS_UNKNOWN`
* **How it works**: Rejects ambiguous binary flags; if a government feed cannot be reached, it returns `WARNING_STATUS_UNKNOWN` rather than claiming the area is safe.
* **Why use it**: Adheres to international disaster risk reduction communication standards.
* **Implementation Location**:
  * [app/services/warning_service.py:L36-L39](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/warning_service.py#L36-L39)

---

### Feature 8: Continuous Polyline Scenic Intelligence

#### Sub-Feature 8.1: 7.5 km Corridor Buffer Analysis
* **What it does**: Evaluates natural viewpoints, waterfalls, and tea plantations within a $7.5\text{ km}$ buffer along the route polyline.
* **How it works**: Densifies coordinates and executes spatial queries against `sri_lanka_combined_scenic_places.csv`.
* **Why use it**: Sri Lanka's tourism brand is built on scenic hill-country rail and road journeys.
* **Implementation Location**:
  * [app/services/scenic_service.py:L110-L195](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/scenic_service.py#L110-L195)

#### Sub-Feature 8.2: Decoupled Rail vs. Road Corridor Ratings
* **What it does**: Evaluates rail corridors separately from road corridors.
* **How it works**: Tracks rail lines through mountainous tea estates (e.g., Kandy to Ella) to calculate distinct rail scenic scores.
* **Why use it**: Rail journeys offer higher scenic value than congested highway roads running parallel in valleys.
* **Implementation Location**:
  * [app/services/scenic_service.py:L210-L280](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/scenic_service.py#L210-L280)

---

### Feature 9: Frontend Architecture & User Experience

#### Sub-Feature 9.1: Dedicated Interactive Swagger UI Runner
* **What it does**: Runs interactive Swagger UI on port 8000 (`/docs` and `/redoc`) with zero external database dependencies.
* **How it works**: Self-contained runner script `scripts/run_swagger.py` mounting static assets and mock fallbacks.
* **Why use it**: Facilitates rapid examiner demonstration without spinning up multi-container Docker environments.
* **Implementation Location**:
  * [scripts/run_swagger.py:L58-L96](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L58-L96)

#### Sub-Feature 9.2: Production Flutter Web Client
* **What it does**: Serves the compiled Flutter web application mounted directly at `/flutter`.
* **How it works**: Mounted as FastAPI static files using local Leaflet CSS/JS bundles.
* **Why use it**: Provides a modern, responsive cross-platform web UI for live testing.
* **Implementation Location**:
  * [scripts/run_swagger.py:L92-L96](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L92-L96)

#### Sub-Feature 9.3: Top-to-Bottom Risk Score Synchronization
* **What it does**: Ensures the top environmental risk banner and bottom candidate cards display identical risk scores and safety percentages.
* **How it works**: Synchronizes `environmental_assessment` with candidate `environmental_risk_score` in [scripts/run_swagger.py:L1246-L1262](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1246-L1262).
* **Why use it**: Resolves user testing feedback regarding conflicting risk metrics.
* **Implementation Location**:
  * [scripts/run_swagger.py:L1246-L1262](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1246-L1262)

#### Sub-Feature 9.4: Overflow-Free Card Layout
* **What it does**: Resolves the Flutter `RenderFlex overflowed by 25 pixels` layout bug.
* **How it works**: Wraps text widgets in `Expanded` and adds `TextOverflow.ellipsis` inside `environmental_risk_card.dart`.
* **Why use it**: Guarantees clean rendering on mobile viewports.
* **Implementation Location**:
  * `environmental_risk_card.dart`

---

## 4. Master Codebase Reference Table

| Feature Category | Specific Sub-Feature | Implementation File | Key Functions / Classes |
|---|---|---|---|
| **Routing** | 6 Dijkstra Objectives | [app/services/dijkstra.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/dijkstra.py) | `DijkstraRouter.route()` |
| **Routing** | Multimodal Graph Network | [app/services/graph.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/graph.py) | `MultimodalGraph`, `Edge`, `Node` |
| **Routing** | Transfer Delay Modeling | [app/services/transfer_loader.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/transfer_loader.py) | `build_transfers()` |
| **Optimizer** | RAGRO Genetic Algorithm | [app/services/ragro.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py) | `RAGROOptimizer.optimize()` |
| **Optimizer** | Topological Crossover | [app/services/ragro.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L532) | `RAGROOptimizer._crossover()` |
| **Optimizer** | Sub-Path Detour Mutation | [app/services/ragro.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/ragro.py#L560) | `RAGROOptimizer._mutate()` |
| **Optimizer** | 130% Distance Bounding | [scripts/run_swagger.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py#L1315) | Practical candidate filter |
| **Public Fares** | SLR Train Ticket Tariffs | [app/services/rail_graph_loader.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/rail_graph_loader.py) | `lookup_distance_tariff()` |
| **Public Fares** | NTC Bus Stage Tariffs | [app/services/bus_graph_loader.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/bus_graph_loader.py) | `lookup_fare()` |
| **AI Audit** | Groq Regulatory Audit | [app/services/fare_verifier.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fare_verifier.py) | `FareVerifier.verify_fares()` |
| **Vehicle Fuel** | Ceypetco Retail Tariffs | [app/services/fuel_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L20) | `OFFICIAL_CEYPETCO_TARIFFS` |
| **Vehicle Fuel** | Vehicle Consumption Spec | [app/services/fuel_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/fuel_service.py#L350) | `estimate_fuel_cost()` |
| **Hazard GIS** | NBRO PostGIS Ingestion | [scripts/import_nbro_hazard_zones.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/import_nbro_hazard_zones.py) | `import_nbro_hazard_zones()` |
| **Hazard GIS** | Scipy cKDTree Indexing | [app/services/landslide_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/landslide_service.py#L150) | `get_susceptibility_score()` |
| **Hazard GIS** | Dynamic Landslide Risk | [app/services/environmental_risk_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/environmental_risk_service.py) | `assess_route()` |
| **Hazard GIS** | Warning Bulletins Check | [app/services/warning_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/warning_service.py) | `check_official_landslide_warnings()` |
| **Scenic** | 7.5 km Corridor Buffer | [app/services/scenic_service.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/app/services/scenic_service.py) | `calculate_scenic_score()` |
| **API Server** | Swagger & Flutter Server | [scripts/run_swagger.py](file:///c:/Users/abdul/OneDrive/Desktop/Rsearch/new_api/J26-DS-337/wandaraya-backend/scripts/run_swagger.py) | Endpoint `/api/v1/routes/query` |
