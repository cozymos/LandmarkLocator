import wikipediaapi
import geopy.distance
from typing import Dict, List, Tuple
import time
import math
import streamlit as st
import logging


class WikiLandmarkFetcher:

    def __init__(self):
        """Initialize Wikipedia API instance"""
        logging.getLogger("wikipediaapi").setLevel(logging.WARNING)

        self.wiki = wikipediaapi.Wikipedia(
            'LandmarkLocator/1.0',
            'en',  # Fixed to English
            extract_format=wikipediaapi.ExtractFormat.WIKI)

        self.last_request = 0
        self.min_delay = 1  # Minimum delay between requests in seconds

        # Pre-defined landmarks for testing
        self.test_landmarks = {
            'San Francisco': {
                'title':
                'Golden Gate Bridge',
                'lat':
                37.8199,
                'lon':
                -122.4783,
                'image_url':
                'https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/GoldenGateBridge-001.jpg/1200px-GoldenGateBridge-001.jpg'
            },
            'Alcatraz': {
                'title':
                'Alcatraz Island',
                'lat':
                37.8267,
                'lon':
                -122.4233,
                'image_url':
                'https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/Alcatraz_Island_aerial_view.jpg/1920px-Alcatraz_Island_aerial_view.jpg'
            },
            'Pier39': {
                'title':
                'Pier 39',
                'lat':
                37.8087,
                'lon':
                -122.4098,
                'image_url':
                'https://upload.wikimedia.org/wikipedia/commons/5/56/San_Francisco_from_Forbes_Island_pier_39%2C_544.jpg'
            },
            'Lombard': {
                'title':
                'Lombard Street',
                'lat':
                37.8021,
                'lon':
                -122.4187,
                'image_url':
                'https://upload.wikimedia.org/wikipedia/commons/d/d1/Lombard_Street_2020.jpg'
            }
        }

    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_passed = current_time - self.last_request
        if time_passed < self.min_delay:
            time.sleep(self.min_delay - time_passed)
        self.last_request = time.time()

    def get_landmarks(self, bounds: Tuple[float, float, float,
                                          float]) -> List[Dict]:
        """
        Fetch landmarks within the given bounds: (south, west, north, east)
        """
        self._rate_limit()

        center_lat = (bounds[0] + bounds[2]) / 2
        center_lon = (bounds[1] + bounds[3]) / 2

        try:
            landmarks = []

            # Calculate the visible area in square kilometers
            width = geopy.distance.distance((center_lat, bounds[1]),
                                            (center_lat, bounds[3])).km
            height = geopy.distance.distance((bounds[0], center_lon),
                                             (bounds[2], center_lon)).km
            visible_area = width * height

            # Only show landmarks within the visible bounds
            for landmark in self.test_landmarks.values():
                if (bounds[0] <= landmark['lat'] <= bounds[2]
                        and bounds[1] <= landmark['lon'] <= bounds[3]):

                    # Calculate distance from center
                    distance = geopy.distance.distance(
                        (center_lat, center_lon),
                        (landmark['lat'], landmark['lon'])).km
                    '''
                    # Calculate relevance score based on distance and visible area
                    max_distance = math.sqrt(width**2 + height**2) / 2
                    relevance = 1.0 - (distance / max_distance if max_distance > 0 else 0)
                    relevance = max(0.1, min(1.0, relevance))

                    page = self.wiki.page(landmark['title'])
                    if page.exists():
                        landmarks.append({
                            'title': page.title,
                            'summary': page.summary[:200] + "..." if len(page.summary) > 200 else page.summary,
                            'url': page.fullurl,
                            'image_url': landmark['image_url'],
                            'distance': round(distance, 2),
                            'relevance': round(relevance, 2),
                            'coordinates': (landmark['lat'], landmark['lon'])
                        })
                    '''
                    landmarks.append({
                        'title':
                        landmark['title'],
                        'summary':
                        landmark['title'],
                        'url':
                        landmark['image_url'],
                        'image_url':
                        landmark['image_url'],
                        'distance':
                        round(distance, 2),
                        'relevance':
                        1.0,
                        'coordinates': (landmark['lat'], landmark['lon'])
                    })
            return landmarks

        except Exception as e:
            raise Exception(f"Failed to fetch landmarks: {str(e)}")
