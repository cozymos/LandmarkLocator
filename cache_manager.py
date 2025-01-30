import streamlit as st
from typing import Tuple, List, Dict
import json
import os
import time
from datetime import datetime, timedelta
import requests
from functools import partial
import folium
from PIL import Image
from io import BytesIO
import hashlib

# Assume image_validator is defined elsewhere and imported correctly.  This is crucial.
# Example: from image_validator import ImageValidator
#          image_validator = ImageValidator()

class OfflineCacheManager:
    def __init__(self):
        # Initialize cache directories with absolute paths
        self.cache_dir = os.path.abspath(".cache")
        self.tiles_dir = os.path.abspath(os.path.join(self.cache_dir, "map_tiles"))
        self.landmarks_dir = os.path.abspath(os.path.join(self.cache_dir, "landmarks"))
        self.images_dir = os.path.abspath(os.path.join(self.cache_dir, "images"))

        # Create cache directories if they don't exist
        for directory in [self.cache_dir, self.tiles_dir, self.landmarks_dir, self.images_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                st.write(f"Debug - Created directory: {directory}")

        # Initialize cache stats in session state
        if 'cache_stats' not in st.session_state:
            st.session_state.cache_stats = {
                'landmarks_cached': 0,
                'images_cached': 0,
                'last_update': None
            }

    def _cache_image(self, image_url: str) -> str:
        """Download and cache an image, return absolute filename if successful"""
        try:
            # Generate filename from URL using MD5 hash
            safe_hash = hashlib.md5(image_url.encode()).hexdigest()
            filename = os.path.abspath(os.path.join(self.images_dir, f"{safe_hash}.jpg"))

            st.write(f"Debug - Processing image URL: {image_url}")
            st.write(f"Debug - Target cache path: {filename}")

            # Validate image URL first
            is_valid, error_msg = image_validator.validate_image_url(image_url)
            if not is_valid:
                st.write(f"Debug - Invalid image URL: {error_msg}")
                return ""

            # Check if file exists and is readable
            if os.path.exists(filename):
                try:
                    # Verify file is readable and valid
                    is_valid, error_msg = image_validator.validate_image_file(filename)
                    if is_valid:
                        st.write(f"Debug - Using existing cached file: {filename}")
                        return filename
                    else:
                        st.write(f"Debug - Existing file invalid: {error_msg}")
                except Exception as e:
                    st.write(f"Debug - Error reading existing file: {str(e)}")

            # Download and save new image
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                st.write(f"Debug - Successfully cached new image: {filename}")

                # Validate the newly cached file
                is_valid, error_msg = image_validator.validate_image_file(filename)
                if is_valid:
                    return filename
                else:
                    st.write(f"Debug - Newly cached file invalid: {error_msg}")
                    os.remove(filename)  # Remove invalid file
                    return ""

            st.write("Debug - Failed to save image")
            return ""

        except Exception as e:
            st.write(f"Debug - Error in _cache_image: {str(e)}")
            return ""

    def cache_landmarks(self, landmarks: List[Dict], bounds: Tuple[float, float, float, float], language: str):
        """Cache landmark data and associated images for offline use"""
        try:
            bounds_key = f"{language}_" + "_".join(str(round(b, 3)) for b in bounds)
            cache_path = os.path.abspath(os.path.join(self.landmarks_dir, f"landmarks_{bounds_key}.json"))

            st.write(f"Debug - Caching landmarks to: {cache_path}")

            cached_landmarks = []
            for landmark in landmarks:
                cached_landmark = landmark.copy()

                if 'image_url' in landmark and landmark['image_url']:
                    st.write(f"Debug - Processing image for landmark: {landmark['title']}")
                    cached_path = self._cache_image(landmark['image_url'])
                    if cached_path:
                        cached_landmark['image_url'] = cached_path
                        st.write(f"Debug - Cached image path set to: {cached_path}")

                cached_landmarks.append(cached_landmark)

            # Save to cache file
            with open(cache_path, 'w') as f:
                json.dump({
                    'landmarks': cached_landmarks,
                    'timestamp': time.time(),
                    'bounds': bounds,
                    'language': language
                }, f)

            # Update cache stats
            st.session_state.cache_stats['landmarks_cached'] = len(os.listdir(self.landmarks_dir))
            st.session_state.cache_stats['images_cached'] = len(os.listdir(self.images_dir))
            st.session_state.cache_stats['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            st.write(f"Debug - Successfully cached {len(cached_landmarks)} landmarks")

        except Exception as e:
            st.write(f"Debug - Error in cache_landmarks: {str(e)}")

    def get_tile_url(self, api_key: str) -> str:
        """Get appropriate tile URL based on mode"""
        if st.session_state.offline_mode:
            # Use OpenStreetMap tiles when offline (they support offline caching)
            return "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        else:
            # Use Google Maps tiles when online
            return f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={api_key}"

    def get_cached_landmarks(self, bounds: Tuple[float, float, float, float], language: str, max_age_hours: int = 24) -> List[Dict]:
        """Retrieve cached landmarks with smart bounds matching"""
        try:
            # Find the closest cached bounds for the specified language
            closest_cache = None
            min_distance = float('inf')

            for cache_file in os.listdir(self.landmarks_dir):
                if cache_file.startswith(f'landmarks_{language}_'):
                    cached_bounds = [float(x) for x in cache_file.split('_')[2:-1]]  # Skip language prefix and .json
                    distance = sum((a - b) ** 2 for a, b in zip(bounds, cached_bounds))

                    if distance < min_distance:
                        min_distance = distance
                        closest_cache = cache_file

            if closest_cache:
                cache_path = os.path.join(self.landmarks_dir, closest_cache)
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)

            # Check if cache is still valid and matches the requested language
            age_hours = (time.time() - cache_data['timestamp']) / 3600
            if age_hours <= max_age_hours and cache_data.get('language') == language:
                # Process cached landmarks
                landmarks = cache_data['landmarks']
                for landmark in landmarks:
                    # Always use cached image if available
                    if 'cached_image' in landmark:
                        landmark['image_url'] = landmark['cached_image']
                return landmarks

            return []

        except Exception as e:
            st.warning(f"Failed to retrieve cached landmarks: {str(e)}")
            return []

    def clear_old_cache(self, max_age_hours: int = 24):
        """Clear cache files older than specified hours"""
        try:
            current_time = time.time()
            cleared_count = 0

            # Clear old landmark cache
            for cache_file in os.listdir(self.landmarks_dir):
                cache_path = os.path.join(self.landmarks_dir, cache_file)
                if os.path.getmtime(cache_path) < current_time - (max_age_hours * 3600):
                    os.remove(cache_path)
                    cleared_count += 1

            # Clear old image cache
            for image_file in os.listdir(self.images_dir):
                image_path = os.path.join(self.images_dir, image_file)
                if os.path.getmtime(image_path) < current_time - (max_age_hours * 3600):
                    os.remove(image_path)
                    cleared_count += 1

            if cleared_count > 0:
                st.success(f"Cleared {cleared_count} old cache files")

        except Exception as e:
            st.warning(f"Failed to clear old cache: {str(e)}")

    def get_cache_stats(self) -> Dict:
        """Get current cache statistics"""
        return st.session_state.cache_stats

# Initialize cache manager
cache_manager = OfflineCacheManager()

def get_landmarks(
    bounds: Tuple[float, float, float, float],
    zoom_level: int,
    language: str = 'en',
    data_source: str = 'Google Places'
) -> List[Dict]:
    """
    Smart wrapper for landmark fetching and caching
    """
    try:
        # Only fetch new landmarks if zoom level is appropriate
        if zoom_level >= 8:  # Prevent fetching at very low zoom levels
            landmarks = []

            if data_source == "Wikipedia":
                from wiki_handler import WikiLandmarkFetcher
                wiki_fetcher = WikiLandmarkFetcher()
                landmarks = wiki_fetcher.get_landmarks(bounds)  # Language handled in class
            else:  # Google Places
                from google_places import GooglePlacesHandler
                places_handler = GooglePlacesHandler()
                landmarks = places_handler.get_landmarks(bounds)

            # Cache the landmarks for offline use
            if landmarks:
                cache_manager.cache_landmarks(landmarks, bounds, language)

            return landmarks
        else:
            return cache_manager.get_cached_landmarks(bounds, language)

    except Exception as e:
        st.error(f"Error fetching landmarks: {str(e)}")
        return cache_manager.get_cached_landmarks(bounds, language)