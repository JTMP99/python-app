from flask import request, jsonify
import requests
from bs4 import BeautifulSoup
from . import scraping_bp

@scraping_bp.route("/", methods=["GET"])
def enhanced_scrape():
    url = request.args.get("url", "https://legislature.maine.gov/audio/")
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            links.append({"text": a.get_text(strip=True), "href": a["href"]})
        return jsonify({"url": url, "links": links})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
