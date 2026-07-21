# WANDARAYA - Component 1
## Context-Aware Recommendation Agent & Intelligence Platform

Component 1 is the **intelligence core of the Wandaraya platform**.  
It provides AI-driven travel recommendations, weather intelligence, multi-agent orchestration, automated data pipelines, and the backend services required to power the Wandaraya mobile application.

The main objective of Component 1 is to transform raw tourism, weather, and user context data into **personalized, context-aware travel experiences**.

---

# 1. Component 1 Responsibilities

Component 1 is responsible for five major capabilities:

## 1. Context-Aware Recommendation Engine

The recommendation engine generates personalized destination suggestions by analyzing multiple contextual factors.

It uses a 5-layer context stack:

### Weather Layer
Uses weather intelligence to understand how suitable a destination is for a selected travel date.

Factors:
- Predicted rainfall
- Temperature conditions
- Weather suitability score
- Monsoon patterns

---

### Time-of-Day Layer

Adjusts recommendations based on the best visiting time.

Examples:
- Sunrise viewpoints recommended during morning
- Beach activities prioritized during suitable hours
- Outdoor activities reduced during extreme heat

---

### Holiday & Crowd Layer

Considers Sri Lankan holidays and cultural events.

Examples:
- Poya days
- National holidays
- Festivals
- Tourist crowd levels

This helps avoid overcrowded experiences and provides alternatives.

---

### Seasonality Layer

Analyzes historical tourism and climate patterns.

Examples:

- Whale watching during suitable months
- Hiking during favorable seasons
- Beach destinations during dry periods

---

### Emotion Layer

Uses user/group emotional preferences from Component 3.

Examples:

- Adventure seeking
- Relaxation
- Family-friendly
- Romantic
- Cultural exploration

---

# 2. Weather Prediction Intelligence

Component 1 contains a custom Sri Lankan weather prediction system.

The purpose is to provide long-term travel weather intelligence beyond standard weather APIs.

## Why a Custom Weather Model?

Traditional weather APIs mainly provide short-term forecasts.

Wandaraya requires predictions for:

- 1 month ahead
- 2 months ahead
- 3 months ahead

The weather model learns Sri Lankan district-level climate patterns using historical weather data.

---

## Weather Prediction Outputs

The model provides:

### Rainfall Probability

Predicts the possibility of rainfall for:

- District
- Date
- Travel period


### Temperature Prediction

Provides expected:

- Minimum temperature
- Maximum temperature


### Weather Suitability Score

Generates a travel suitability value:

Example:

This score directly influences destination ranking.


### Monsoon Detection

Identifies seasonal weather patterns.

Examples:

- Southwest monsoon
- Northeast monsoon
- Dry seasons

---

# 3. AI Multi-Agent Orchestration

Component 1 acts as the central AI coordinator.

It manages communication between multiple intelligent agents using LangGraph.

## Coordinator Agent

The coordinator receives user travel requirements and distributes tasks to different agents.

It communicates with:

- Destination Agent
- Route Agent (Component 2)
- Emotion Agent (Component 3)
- Booking Agent

Then combines all outputs.

---

## Destination Agent

Responsible for:

- Finding suitable destinations
- Applying context ranking
- Using semantic search
- Filtering unsuitable places


---

## Trip Planner Agent

Uses AI generation to create the final travel plan.

Produces:

- Day-by-day itinerary
- Activities
- Travel timing
- Weather explanations
- Hotel recommendations


---

## Booking Agent

Responsible for:

- Hotel availability
- Hotel information
- Booking integration
- Affiliate links

---

# 4. Knowledge Base & Semantic Search

Component 1 maintains the tourism knowledge base.

It stores and processes:

- Tourist attractions
- Historical information
- Reviews
- Cultural information
- Travel descriptions
- Visitor experiences


The knowledge base supports AI search using vector embeddings.

It enables queries like:

> "Best peaceful mountain places for a couple in December"

and returns relevant destinations.

---

# 5. Data Pipeline Management

Apache Airflow manages all automated data operations.

The pipeline continuously collects and updates information from external sources.

Main data sources:

- Sri Lanka Meteorology Department
- Google Places
- SLTDA tourism data
- Wikivoyage/Wikipedia
- TripAdvisor reviews
- Government holiday calendars
- Railway schedules
- Weather APIs


Airflow manages:

- Data collection
- Data cleaning
- Database updates
- Model retraining
- Knowledge base updates

---

# 6. Mobile Platform Backend

Component 1 provides backend services for the Wandaraya mobile application.

It supports:

## Trip Planning

- Generate itineraries
- Save trips
- Update plans


## Start Trip Mode

Provides real-time trip assistance:

- Morning trip briefing
- Travel reminders
- Weather alerts
- Location-based notifications


## Dynamic Replanning

Automatically adjusts travel plans when disruptions occur.

Examples:

- Heavy rain
- Attraction closure
- Unexpected changes


## Emergency Support

Provides:

- SOS functionality
- Nearby emergency locations
- Safety assistance


## Push Notifications

Uses Firebase notifications for:

- Trip reminders
- Weather warnings
- Important alerts

---

# 7. Component 1 High-Level Architecture
             User Mobile Application
                     |
                     |
             FastAPI Backend
                     |
    --------------------------------
    |              |               |

---

# 8. Component 1 Folder Structure
wandaraya-backend/
│
├── app/ # Main FastAPI application
│ │
│ ├── agents/ # LangGraph AI Agents
│ │ ├── coordinator.py # Coordinator Agent
│ │ ├── destination.py # Destination Recommendation Agent
│ │ ├── trip_planner.py # AI Trip Planner Agent
│ │ └── booking_agent.py # Hotel Booking Agent
│ │
│ ├── context_stack/ # Context-aware recommendation layers
│ │ ├── weather.py # Weather Context Layer
│ │ ├── time_of_day.py # Time Context Layer
│ │ ├── holiday.py # Holiday / Poya Context Layer
│ │ ├── seasonality.py # Seasonal Recommendation Layer
│ │ └── emotion.py # User Emotion Context Layer
│ │
│ ├── weather_model/ # Weather Prediction ML Module
│ │ ├── train.py # Model Training
│ │ ├── predict.py # Weather Prediction
│ │ ├── evaluate.py # Model Evaluation
│ │ ├── scoring.py # Weather Suitability Scoring
│ │ └── models/ # Saved Weather Models
│ │
│ ├── knowledge_base/ # Tourism Knowledge Base
│ │ ├── embeddings.py # Embedding Generation
│ │ ├── qdrant_client.py # Vector Database Operations
│ │ └── content_filter.py # Content Processing & Filtering
│ │
│ ├── services/ # External and Business Services
│ │ ├── gemini.py # AI LLM Services
│ │ ├── weather_service.py # Weather Services
│ │ ├── places_service.py # Places Information Services
│ │ ├── booking_service.py # Booking Services
│ │ └── fcm_service.py # Notification Services
│ │
│ ├── routers/ # FastAPI API Endpoints
│ │ ├── recommend.py # Recommendation APIs
│ │ ├── orchestrate.py # Agent Orchestration APIs
│ │ ├── itinerary.py # Itinerary APIs
│ │ ├── trip.py # Trip Management APIs
│ │ └── notifications.py # Notification APIs
│ │
│ ├── models/ # Database Models
│ │ ├── attraction.py
│ │ ├── itinerary.py
│ │ ├── user.py
│ │ ├── weather.py
│ │ └── calendar.py
│ │
│ ├── schemas/ # API Data Validation Schemas
│ │ ├── recommend.py # Recommendation Request/Response Models
│ │ ├── itinerary.py # Itinerary Response Models
│ │ ├── weather.py # Weather Models
│ │ └── trip.py # Trip Request Models
│ │
│ ├── database.py # Database Connection Management
│ ├── config.py # Application Configuration
│ └── main.py # FastAPI Application Entry Point
│
│
├── airflow/ # Apache Airflow Data Pipeline System
│ │
│ ├── dags/ # Airflow Workflow Definitions
│ │ ├── weather/ # Weather Data Pipelines
│ │ ├── tourism/ # Tourism Data Pipelines
│ │ ├── knowledge_base/ # Knowledge Base Update Pipelines
│ │ └── ml_training/ # ML Model Training Pipelines
│ │
│ └── plugins/ # Custom Airflow Plugins
│
│
├── data/ # Raw and Processed Data Storage
│ │
│ ├── weather/ # Historical Weather Data
│ ├── tourism/ # Tourism Dataset
│ └── processed/ # Cleaned Data
│
│
├── migrations/ # Database Migration Files
│
│
├── tests/ # System Testing
│ │
│ ├── test_weather_model.py # Weather Model Tests
│ ├── test_context_stack.py # Context Layer Tests
│ ├── test_agents.py # AI Agent Tests
│ └── test_api.py # API Tests
│
│
├── docker-compose.yml # Application Services
│ # FastAPI + PostgreSQL + Redis + Qdrant
│
├── docker-compose.airflow.yml # Airflow Services
│ # Airflow Scheduler + Webserver
│
├── Dockerfile # Backend Container Configuration
│
├── requirements.txt # Python Dependencies
│
├── .env # Environment Variables
│
├── .gitignore # Git Ignore Rules
│
└── README.md # Project Documentation


---

# 9. Technologies Used

## Backend

- FastAPI
- Python 3.11
- Pydantic


## AI & Machine Learning

- LangGraph
- Google Gemini
- Prophet
- Scikit-learn
- Pandas


## Data Engineering

- Apache Airflow
- BeautifulSoup
- HTTP Clients


## Databases

- PostgreSQL + PostGIS
- Redis
- Qdrant Vector Database


## Infrastructure

- Docker
- Docker Compose
- GitHub Actions
- Google Cloud Run


---

# 10. Component 1 Final Outcome

After completion, Component 1 provides:

✅ AI-powered travel recommendation engine  
✅ Sri Lankan district-level weather prediction model  
✅ Multi-agent AI travel planning system  
✅ Automated tourism data pipeline  
✅ Semantic tourism knowledge base  
✅ Dynamic itinerary generation  
✅ Real-time trip assistance backend  
✅ Mobile application intelligence platform  

Component 1 acts as the **brain of Wandaraya**, connecting user preferences, AI reasoning, weather intelligence, tourism knowledge, and real-time travel assistance into a single intelligent platform.