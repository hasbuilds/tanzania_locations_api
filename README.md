# Tanzania Locations API

Tanzania Locations API is a backend service that provides structured, hierarchical access to Tanzania’s administrative locations — Regions, Districts, Wards, Streets, and Places — from a single normalized JSON dataset.

The project is built using FastAPI and Pydantic for type-safe APIs and data validation, and is served using Uvicorn as an ASGI server. It is designed to be lightweight, fast, and easy to integrate into other systems.

---

## Project Description

This API loads Tanzania location data into memory at startup, builds efficient lookup indexes, and exposes RESTful endpoints for browsing, searching, and exporting location data. It also serves a minimal HTML/CSS/JavaScript interface directly from the backend for interactive exploration.

The project emphasizes clean architecture, strong typing, and performance without relying on heavy frontend frameworks or external databases.

---

## Core Features

- Hierarchical location access  
  (Region → District → Ward → Street → Place)
- Fast in-memory indexing for efficient queries
- Type-safe request and response models using Pydantic
- RESTful API with pagination and validation
- Keyword search across all administrative levels
- CSV export endpoints for data analysis and integration
- Lightweight UI served directly by FastAPI
- Stateless and easy to deploy

---

## Tech Stack

- **Backend Framework:** FastAPI
- **Data Validation:** Pydantic
- **ASGI Server:** Uvicorn
- **Language:** Python
- **Data Source:** JSON
- **Exports:** CSV (streamed responses)

---

## Project Structure

#├── main.py
#├── tanzania_all_regions_full_v3.json
#└── static/
#├── index.html
#├── style.css
#└── app.js
