import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import List, Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


def search_commons_images(query: str, limit: int) -> List[Dict[str, Any]]:
    """Use Wikimedia Commons to fetch image files directly relevant to the query."""
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "origin": "*",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": min(limit, 50),
        "prop": "imageinfo|info",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,
        "inprop": "url",
    }
    r = requests.get(api, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    items: List[Dict[str, Any]] = []
    for pageid, page in pages.items():
        imageinfo = (page.get("imageinfo") or [{}])[0]
        thumb = imageinfo.get("thumburl") or imageinfo.get("url")
        if not thumb:
            continue
        title = page.get("title", "")
        desc_url = page.get("fullurl") or f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}"
        summary = None
        extmeta = imageinfo.get("extmetadata") or {}
        artist = (extmeta.get("Artist") or {}).get("value")
        if artist:
            summary = f"By {artist}"
        items.append({
            "title": title.replace("File:", "").strip(),
            "thumbnail": thumb,
            "pageUrl": desc_url,
            "summary": summary,
            "source": "wikimedia_commons"
        })
    return items


def search_wikipedia_pages(query: str, limit: int) -> List[Dict[str, Any]]:
    """Fallback: search Wikipedia pages with thumbnails."""
    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": min(limit, 50),
        "prop": "pageimages|extracts|info",
        "pilicense": "any",
        "pithumbsize": 600,
        "format": "json",
        "origin": "*",
        "exintro": 1,
        "explaintext": 1,
        "exsentences": 1,
        "inprop": "url",
    }
    r = requests.get(api_url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    items: List[Dict[str, Any]] = []
    for pageid, page in pages.items():
        thumb = page.get("thumbnail", {}).get("source")
        if not thumb:
            continue
        title = page.get("title")
        extract = page.get("extract")
        fullurl = page.get("fullurl") or f"https://en.wikipedia.org/?curid={pageid}"
        items.append({
            "title": title,
            "thumbnail": thumb,
            "pageUrl": fullurl,
            "summary": extract,
            "source": "wikipedia"
        })
    return items


@app.get("/images")
def get_images(query: str = Query(..., min_length=1, description="Search prompt"), limit: int = Query(24, ge=1, le=50)) -> Dict[str, Any]:
    """
    Search for images relevant to a prompt using Wikimedia Commons first (direct media),
    then fall back to Wikipedia page thumbnails. Only if both fail, return placeholders.
    """
    try:
        # 1) Wikimedia Commons: returns actual image files for the query
        items = search_commons_images(query, limit)

        # 2) If too few from Commons, top up with Wikipedia thumbnails
        if len(items) < limit:
            wiki_items = search_wikipedia_pages(query, limit)
            # Avoid duplicates by URL
            seen = {i["thumbnail"] for i in items}
            for w in wiki_items:
                if w["thumbnail"] not in seen and len(items) < limit:
                    items.append(w)
                    seen.add(w["thumbnail"])

        # 3) Final fallback: high-quality placeholders so the UI still shows something
        if not items:
            items = [
                {
                    "title": f"Placeholder #{i+1}",
                    "thumbnail": f"https://picsum.photos/seed/{query}-{i}/800/600",
                    "pageUrl": "https://picsum.photos/",
                    "summary": "Placeholder image while we find results",
                    "source": "picsum"
                }
                for i in range(min(limit, 12))
            ]

        return {"query": query, "count": len(items), "items": items}

    except Exception as e:
        fallback = [
            {
                "title": f"Placeholder #{i+1}",
                "thumbnail": f"https://picsum.photos/seed/{query}-{i}/800/600",
                "pageUrl": "https://picsum.photos/",
                "summary": "Placeholder image due to an error fetching results",
                "source": "picsum"
            }
            for i in range(6)
        ]
        return {"query": query, "count": len(fallback), "items": fallback, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
