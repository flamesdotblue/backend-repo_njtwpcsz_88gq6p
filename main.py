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


@app.get("/images")
def get_images(query: str = Query(..., min_length=1, description="Search prompt"), limit: int = Query(24, ge=1, le=50)) -> Dict[str, Any]:
    """
    Search for images related to a prompt using Wikipedia's public API (no key required).
    Returns a simple list of thumbnails and page links.
    """
    # Wikipedia API endpoint for searching pages with thumbnails
    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": min(limit, 50),
        "prop": "pageimages|extracts",
        "pilicense": "any",
        "pithumbsize": 600,
        "format": "json",
        "origin": "*",
        "exintro": 1,
        "explaintext": 1,
        "exsentences": 1,
    }

    try:
        r = requests.get(api_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        items: List[Dict[str, Any]] = []
        for pageid, page in pages.items():
            thumb = page.get("thumbnail", {}).get("source")
            title = page.get("title")
            extract = page.get("extract")
            if thumb:
                items.append({
                    "title": title,
                    "thumbnail": thumb,
                    "pageUrl": f"https://en.wikipedia.org/?curid={pageid}",
                    "summary": extract,
                    "source": "wikipedia"
                })
        # If nothing found, provide a gentle fallback using Picsum placeholders matching the theme
        if not items:
            items = [
                {
                    "title": f"Placeholder #{i+1}",
                    "thumbnail": f"https://picsum.photos/seed/{query}-{i}/600/400",
                    "pageUrl": "https://picsum.photos/",
                    "summary": "Placeholder image while we find results",
                    "source": "picsum"
                }
                for i in range(min(limit, 12))
            ]
        return {"query": query, "count": len(items), "items": items}
    except Exception as e:
        # On error, still return an object with a helpful message and safe fallback images
        fallback = [
            {
                "title": f"Placeholder #{i+1}",
                "thumbnail": f"https://picsum.photos/seed/{query}-{i}/600/400",
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
