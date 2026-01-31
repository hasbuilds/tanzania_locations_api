from __future__ import annotations
import csv
import io

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import StreamingResponse


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "tanzania_all_regions_full_v3.json"
STATIC_DIR = APP_DIR / "static"

app = FastAPI()

@app.get("/debug-paths", include_in_schema=False)
def debug_paths():
    return {
        "APP_DIR": str(APP_DIR),
        "DATA_PATH": str(DATA_PATH),
        "DATA_EXISTS": DATA_PATH.exists(),
        "STATIC_DIR": str(STATIC_DIR),
        "STATIC_EXISTS": STATIC_DIR.exists(),
        "INDEX_PATH": str(STATIC_DIR / "index.html"),
        "INDEX_EXISTS": (STATIC_DIR / "index.html").exists(),
    }


# Serve static files (HTML/CSS/JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    # Landing page UI
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Missing static/index.html")
    return FileResponse(index_path)


# Pydantic response models
class RegionOut(BaseModel):
    name: str
    postcode: Optional[int] = None


class DistrictOut(BaseModel):
    name: str


class WardOut(BaseModel):
    name: str


class StreetOut(BaseModel):
    name: str
    places: List[str] = []


class SearchHit(BaseModel):
    level: str  # region | district | ward | street
    path: str   # e.g. "Dar es Salaam / Ilala / Buguruni / Malapa"
    name: str



# In-memory store + indexes
DATA: Dict[str, Any] = {}
_region_index: Dict[str, Dict[str, Any]] = {}
_district_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
_ward_index: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
_street_index: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]] = {}


def norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def load_data() -> None:
    global DATA
    if not DATA_PATH.exists():
        raise RuntimeError(f"Missing data file: {DATA_PATH}")

    with DATA_PATH.open("r", encoding="utf-8") as f:
        DATA = json.load(f)

    build_indexes(DATA)


def build_indexes(data: Dict[str, Any]) -> None:
    _region_index.clear()
    _district_index.clear()
    _ward_index.clear()
    _street_index.clear()

    regions = data.get("regions", [])
    if not isinstance(regions, list):
        raise RuntimeError("Invalid JSON structure: 'regions' must be a list")

    for r in regions:
        r_name = r.get("REGION") or r.get("name") or ""
        r_norm = norm(r_name)
        if not r_norm:
            continue

        _region_index[r_norm] = r
        _district_index.setdefault(r_norm, {})
        _ward_index.setdefault(r_norm, {})
        _street_index.setdefault(r_norm, {})

        districts = r.get("DISTRIC", [])
        if not isinstance(districts, list):
            continue

        for d in districts:
            d_name = d.get("NAME") or d.get("name") or ""
            d_norm = norm(d_name)
            if not d_norm:
                continue

            _district_index[r_norm][d_norm] = d
            _ward_index[r_norm].setdefault(d_norm, {})
            _street_index[r_norm].setdefault(d_norm, {})

            wards = d.get("WARD", [])
            if not isinstance(wards, list):
                continue

            for w in wards:
                w_name = w.get("NAME") or w.get("name") or ""
                w_norm = norm(w_name)
                if not w_norm:
                    continue

                _ward_index[r_norm][d_norm][w_norm] = w
                _street_index[r_norm][d_norm].setdefault(w_norm, {})

                streets = w.get("STREETS", [])
                if not isinstance(streets, list):
                    continue

                for s in streets:
                    s_name = s.get("NAME") or s.get("name") or ""
                    s_norm = norm(s_name)
                    if not s_norm:
                        continue

                    _street_index[r_norm][d_norm][w_norm][s_norm] = s


@app.on_event("startup")
def _startup() -> None:
    load_data()



# Helpers
def require_region(region: str) -> Tuple[str, Dict[str, Any]]:
    r_norm = norm(region)
    r = _region_index.get(r_norm)
    if not r:
        raise HTTPException(status_code=404, detail=f"Region not found: {region}")
    return r_norm, r


def require_district(r_norm: str, district: str) -> Tuple[str, Dict[str, Any]]:
    d_norm = norm(district)
    d = _district_index.get(r_norm, {}).get(d_norm)
    if not d:
        raise HTTPException(status_code=404, detail=f"District not found: {district}")
    return d_norm, d


def require_ward(r_norm: str, d_norm: str, ward: str) -> Tuple[str, Dict[str, Any]]:
    w_norm = norm(ward)
    w = _ward_index.get(r_norm, {}).get(d_norm, {}).get(w_norm)
    if not w:
        raise HTTPException(status_code=404, detail=f"Ward not found: {ward}")
    return w_norm, w


def paginate(items: List[Any], limit: int, offset: int) -> List[Any]:
    if offset < 0:
        offset = 0
    if limit < 1:
        limit = 1
    return items[offset : offset + limit]


def csv_stream(rows: List[List[str]], filename: str) -> StreamingResponse:
    """
    Stream CSV without storing a physical file.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)

    buf.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)


def optional_region(region: Optional[str]) -> Optional[str]:
    if not region:
        return None
    r_norm = norm(region)
    if r_norm not in _region_index:
        raise HTTPException(status_code=404, detail=f"Region not found: {region}")
    return r_norm


def optional_district(r_norm: str, district: Optional[str]) -> Optional[str]:
    if not district:
        return None
    d_norm = norm(district)
    if d_norm not in _district_index.get(r_norm, {}):
        raise HTTPException(status_code=404, detail=f"District not found: {district}")
    return d_norm


def optional_ward(r_norm: str, d_norm: str, ward: Optional[str]) -> Optional[str]:
    if not ward:
        return None
    w_norm = norm(ward)
    if w_norm not in _ward_index.get(r_norm, {}).get(d_norm, {}):
        raise HTTPException(status_code=404, detail=f"Ward not found: {ward}")
    return w_norm




# Routes
@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "country": DATA.get("country", "unknown"),
        "regions": len(DATA.get("regions", [])),
    }


@app.get("/regions", response_model=List[RegionOut])
def list_regions(
    q: Optional[str] = Query(default=None, description="Filter by region name (contains)."),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[RegionOut]:
    regions = DATA.get("regions", [])
    out: List[RegionOut] = []

    qn = norm(q) if q else None

    for r in regions:
        name = r.get("REGION") or ""
        if qn and qn not in norm(name):
            continue
        out.append(RegionOut(name=name, postcode=r.get("POSTCODE")))

    out.sort(key=lambda x: norm(x.name))
    return paginate(out, limit, offset)

def pick_list(obj: Dict[str, Any], *keys: str) -> List[Any]:
    """
    Return the first value that is a list for the given keys.
    Helps support different JSON structures e.g. DISTRIC vs DISTRICT.
    """
    for k in keys:
        val = obj.get(k)
        if isinstance(val, list):
            return val
    return []


@app.get("/regions/{region}/districts", response_model=List[DistrictOut])
def list_districts(
    region: str,
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> List[DistrictOut]:
    r_norm, r = require_region(region)
    districts = pick_list(r, "DISTRIC", "DISTRICT", "DISTRICTS") or []
    out = [DistrictOut(name=d.get("NAME", "")) for d in districts if d.get("NAME")]
    out.sort(key=lambda x: norm(x.name))
    return paginate(out, limit, offset)


@app.get("/regions/{region}/districts/{district}/wards", response_model=List[WardOut])
def list_wards(
    region: str,
    district: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> List[WardOut]:
    r_norm, _ = require_region(region)
    d_norm, d = require_district(r_norm, district)
    wards = pick_list(d, "WARD", "WARDS") or []
    out = [WardOut(name=w.get("NAME", "")) for w in wards if w.get("NAME")]
    out.sort(key=lambda x: norm(x.name))
    return paginate(out, limit, offset)


@app.get("/regions/{region}/districts/{district}/wards/{ward}/streets", response_model=List[StreetOut])
def list_streets(
    region: str,
    district: str,
    ward: str,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> List[StreetOut]:
    r_norm, _ = require_region(region)
    d_norm, _ = require_district(r_norm, district)
    w_norm, w = require_ward(r_norm, d_norm, ward)

    streets = pick_list(w, "STREETS", "STREET", "ROADS") or []
    out: List[StreetOut] = []
    for s in streets:
        s_name = s.get("NAME") or ""
        if not s_name:
            continue
        places = s.get("PLACES")
        if not isinstance(places, list):
            places = []
        out.append(StreetOut(name=s_name, places=places))

    out.sort(key=lambda x: norm(x.name))
    return paginate(out, limit, offset)


@app.get("/search", response_model=List[SearchHit])
def search(
    q: str = Query(..., min_length=2, description="Search keyword (contains)."),
    level: str = Query(default="all", description="all | region | district | ward | street"),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[SearchHit]:
    qn = norm(q)
    hits: List[SearchHit] = []

    if level in ("all", "region"):
        for r_norm, r in _region_index.items():
            r_name = r.get("REGION", "")
            if qn in r_norm:
                hits.append(SearchHit(level="region", path=r_name, name=r_name))

    if level in ("all", "district"):
        for r_norm, districts in _district_index.items():
            r_name = _region_index[r_norm].get("REGION", "")
            for d_norm, d in districts.items():
                d_name = d.get("NAME", "")
                if qn in d_norm:
                    hits.append(SearchHit(level="district", path=f"{r_name} / {d_name}", name=d_name))

    if level in ("all", "ward"):
        for r_norm, districts in _ward_index.items():
            r_name = _region_index[r_norm].get("REGION", "")
            for d_norm, wards in districts.items():
                d_name = _district_index[r_norm][d_norm].get("NAME", "")
                for w_norm, w in wards.items():
                    w_name = w.get("NAME", "")
                    if qn in w_norm:
                        hits.append(SearchHit(level="ward", path=f"{r_name} / {d_name} / {w_name}", name=w_name))

    if level in ("all", "street"):
        for r_norm, districts in _street_index.items():
            r_name = _region_index[r_norm].get("REGION", "")
            for d_norm, wards in districts.items():
                d_name = _district_index[r_norm][d_norm].get("NAME", "")
                for w_norm, streets in wards.items():
                    w_name = _ward_index[r_norm][d_norm][w_norm].get("NAME", "")
                    for s_norm, s in streets.items():
                        s_name = s.get("NAME", "")
                        if qn in s_norm:
                            hits.append(
                                SearchHit(
                                    level="street",
                                    path=f"{r_name} / {d_name} / {w_name} / {s_name}",
                                    name=s_name,
                                )
                            )

    seen = set()
    uniq: List[SearchHit] = []
    for h in hits:
        key = (h.level, norm(h.path))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)

    uniq.sort(key=lambda x: (len(x.path), norm(x.path)))
    return uniq[:limit]

@app.get("/download/places", include_in_schema=True)
def download_places(
    region: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    ward: Optional[str] = Query(default=None),
) -> StreamingResponse:
    """
    CSV columns: region, district, ward, street, place
    """
    rows: List[List[str]] = [["region", "district", "ward", "street", "place"]]

    def add_places(r_name: str, d_name: str, w_name: str, s: Dict[str, Any]) -> None:
        s_name = s.get("NAME", "")
        places = s.get("PLACES")
        if not isinstance(places, list):
            places = []
        if not places:
            rows.append([r_name, d_name, w_name, s_name, ""])
            return
        for p in places:
            rows.append([r_name, d_name, w_name, s_name, str(p)])

    # Export everything if no region
    if not region:
        for r_norm, r in _region_index.items():
            r_name = r.get("REGION", "")
            for d_norm, d in _district_index.get(r_norm, {}).items():
                d_name = d.get("NAME", "")
                for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
                    w_name = w.get("NAME", "")
                    for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                        add_places(r_name, d_name, w_name, s)
        return csv_stream(rows, "tanzania_places.csv")

    r_norm = optional_region(region)
    assert r_norm is not None
    r_name = _region_index[r_norm].get("REGION", "")

    if not district:
        for d_norm, d in _district_index.get(r_norm, {}).items():
            d_name = d.get("NAME", "")
            for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
                w_name = w.get("NAME", "")
                for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                    add_places(r_name, d_name, w_name, s)
        safe = norm(region).replace(" ", "_")
        return csv_stream(rows, f"{safe}_places.csv")

    d_norm = optional_district(r_norm, district)
    assert d_norm is not None
    d_name = _district_index[r_norm][d_norm].get("NAME", "")

    if not ward:
        for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
            w_name = w.get("NAME", "")
            for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                add_places(r_name, d_name, w_name, s)
        safe = (norm(region) + "_" + norm(district)).replace(" ", "_")
        return csv_stream(rows, f"{safe}_places.csv")

    w_norm = optional_ward(r_norm, d_norm, ward)
    assert w_norm is not None
    w_name = _ward_index[r_norm][d_norm][w_norm].get("NAME", "")

    for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
        add_places(r_name, d_name, w_name, s)

    safe = (norm(region) + "_" + norm(district) + "_" + norm(ward)).replace(" ", "_")
    return csv_stream(rows, f"{safe}_places.csv")

@app.get("/download/search", include_in_schema=True)
def download_search(
    q: str = Query(..., min_length=2),
    level: str = Query(default="all"),
    limit: int = Query(default=200, ge=1, le=2000),
) -> StreamingResponse:
    """
    Same logic as /search, but returns a downloadable CSV.
    """
    hits = search(q=q, level=level, limit=limit)  # reuse your existing function
    rows = [["level", "name", "path"]]
    for h in hits:
        rows.append([h.level, h.name, h.path])

    safe = f"search_{norm(q).replace(' ', '_')}.csv"
    return csv_stream(rows, safe)



@app.get("/download/streets", include_in_schema=True)
def download_streets(
    region: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    ward: Optional[str] = Query(default=None),
) -> StreamingResponse:
    """
    CSV columns: region, district, ward, street, places_count
    Filters are optional:
      - no filters => exports all streets in Tanzania
      - region only => exports all streets in that region
      - region + district => exports all streets in that district
      - region + district + ward => exports all streets in that ward
    """
    rows: List[List[str]] = [["region", "district", "ward", "street", "places_count"]]

    # If region not provided, export everything
    if not region:
        for r_norm, r in _region_index.items():
            r_name = r.get("REGION", "")
            for d_norm, d in _district_index.get(r_norm, {}).items():
                d_name = d.get("NAME", "")
                for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
                    w_name = w.get("NAME", "")
                    for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                        s_name = s.get("NAME", "")
                        places = s.get("PLACES")
                        if not isinstance(places, list):
                            places = []
                        rows.append([r_name, d_name, w_name, s_name, str(len(places))])

        return csv_stream(rows, "tanzania_streets.csv")

    # If region provided, validate it
    r_norm = optional_region(region)
    assert r_norm is not None

    # If district is provided, validate it. Else export entire region.
    if not district:
        r = _region_index[r_norm]
        r_name = r.get("REGION", "")
        for d_norm, d in _district_index.get(r_norm, {}).items():
            d_name = d.get("NAME", "")
            for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
                w_name = w.get("NAME", "")
                for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                    s_name = s.get("NAME", "")
                    places = s.get("PLACES")
                    if not isinstance(places, list):
                        places = []
                    rows.append([r_name, d_name, w_name, s_name, str(len(places))])

        safe = norm(region).replace(" ", "_")
        return csv_stream(rows, f"{safe}_streets.csv")

    d_norm = optional_district(r_norm, district)
    assert d_norm is not None

    # If ward is provided, validate it. Else export entire district.
    if not ward:
        r_name = _region_index[r_norm].get("REGION", "")
        d_name = _district_index[r_norm][d_norm].get("NAME", "")
        for w_norm, w in _ward_index.get(r_norm, {}).get(d_norm, {}).items():
            w_name = w.get("NAME", "")
            for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
                s_name = s.get("NAME", "")
                places = s.get("PLACES")
                if not isinstance(places, list):
                    places = []
                rows.append([r_name, d_name, w_name, s_name, str(len(places))])

        safe = (norm(region) + "_" + norm(district)).replace(" ", "_")
        return csv_stream(rows, f"{safe}_streets.csv")

    w_norm = optional_ward(r_norm, d_norm, ward)
    assert w_norm is not None

    # Export only one ward
    r_name = _region_index[r_norm].get("REGION", "")
    d_name = _district_index[r_norm][d_norm].get("NAME", "")
    w_name = _ward_index[r_norm][d_norm][w_norm].get("NAME", "")

    for s_norm, s in _street_index.get(r_norm, {}).get(d_norm, {}).get(w_norm, {}).items():
        s_name = s.get("NAME", "")
        places = s.get("PLACES")
        if not isinstance(places, list):
            places = []
        rows.append([r_name, d_name, w_name, s_name, str(len(places))])

    safe = (norm(region) + "_" + norm(district) + "_" + norm(ward)).replace(" ", "_")
    return csv_stream(rows, f"{safe}_streets.csv")
