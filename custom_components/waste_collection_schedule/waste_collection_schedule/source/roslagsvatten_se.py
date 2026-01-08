import json
import logging
import re
from datetime import datetime

import requests
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "Roslagsvatten"
DESCRIPTION = "Source for Roslagsvatten waste collection (Österåker, Vaxholm, etc.)."
URL = "https://roslagsvatten.se"

TEST_CASES = {
    "Osteraker Test": {
        "street_address": "Andromedavägen 1, Åkersberga",
        "municipality": "osteraker",
    },
    "Vaxholm Test": {
        "street_address": "Hamngatan 1, Vaxholm",
        "municipality": "vaxholm",
    },
}

_LOGGER = logging.getLogger(__name__)

ICON_MAP = {
    "Restavfall": "mdi:trash-can",
    "Matavfall": "mdi:food-apple",
    "Slam": "mdi:emoticon-poop",
    "Trädgårdsavfall": "mdi:leaf",
    "Farligt avfall": "mdi:biohazard",
}

class Source:
    def __init__(self, street_address: str, municipality: str):
        self._street_address = street_address
        self._municipality = municipality.lower()
        self._api_url = "https://roslagsvatten.se/schedule"

    def fetch(self):
        # 1. SEARCH for the building ID
        search_payload = {
            "searchText": self._street_address,
            "municipality": self._municipality
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0",
        }

        r = requests.post(
            f"{self._api_url}/search", 
            data=json.dumps(search_payload), 
            headers=headers
        )
        r.raise_for_status()
        
        search_results = r.json()
        if not search_results or "data" not in search_results[0]:
            _LOGGER.error("Could not find address info in Roslagsvatten search")
            return []

        # Extract data-bid="12345" from the HTML response
        html_search = search_results[0]["data"]
        bid_match = re.search(r'data-bid="(\d+)"', html_search)
        
        if not bid_match:
            _LOGGER.error(f"Could not find buildingId for address: {self._street_address}")
            return []
        
        building_id = bid_match.group(1)

        # 2. FETCH the schedule using the building ID
        fetch_payload = {
            "buildingId": building_id,
            "municipality": self._municipality
        }

        r = requests.post(
            f"{self._api_url}/fetch", 
            data=json.dumps(fetch_payload), 
            headers=headers
        )
        r.raise_for_status()
        
        fetch_results = r.json()
        if not fetch_results or "data" not in fetch_results[0]:
            return []

        html_schedule = fetch_results[0]["data"]

        # 3. PARSE the HTML using Regex
        # We look for: <h3>Waste Type</h3> and <p>Nästa hämtning: YYYY-MM-DD</p>
        entries = []
        
        # Regex to find all schedule blocks
        # This matches the title in <h3> and the date inside the following <p> tag
        pattern = re.compile(r"<h3>(.*?)</h3>[\s\S]*?Nästa hämtning: (\d{4}-\d{2}-\d{2})")
        
        matches = pattern.findall(html_schedule)
        
        for waste_type, date_str in matches:
            pickup_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            icon = ICON_MAP.get(waste_type, "mdi:trash-can")
            
            entries.append(
                Collection(
                    date=pickup_date,
                    t=waste_type,
                    icon=icon,
                )
            )

        return entries