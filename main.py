# Page config must come first
import streamlit as st
st.set_page_config(page_title="Landmarks Locator",
                   page_icon="🗺️",
                   layout="wide",
                   initial_sidebar_state="expanded")

import folium
from streamlit_folium import st_folium
import time
import math
from urllib.parse import quote, unquote
from typing import Tuple, List, Dict
from map_utils import draw_distance_circle, add_landmarks_to_map
from coord_utils import parse_coordinates, format_dms

# Initialize cache manager
from cache_manager import OfflineCacheManager
cache_manager = OfflineCacheManager()

from ai_handler import LandmarkAIHandler
ai_handler = LandmarkAIHandler()

# Update CSS for full height
st.markdown("""
<style>
    /* Make the map container take full viewport height */
    .stfolium-container {
        width: 100% !important;
        height: calc(100vh - 80px) !important;  /* Account for header space */
        margin-bottom: 0;
    }

    /* Ensure the folium map itself fills the container */
    .folium-map {
        height: 100% !important;
    }

    /* Compact sidebar content */
    .sidebar .element-container {
        margin-bottom: 0.5rem;
    }

    /* Hide unnecessary padding */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 0;
        max-width: 100%;
    }

    /* Hide footer */
    footer {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state with URL parameters if available
if 'map_center' not in st.session_state:
    try:
        center_str = st.query_params.get('center', '37.7749,-122.4194')
        lat, lon = map(float, center_str.split(','))
        st.session_state.map_center = [lat, lon]
    except:
        st.session_state.map_center = [37.7749, -122.4194]  # Default to San Francisco

if 'zoom_level' not in st.session_state:
    try:
        st.session_state.zoom_level = int(st.query_params.get('zoom', '12'))
    except:
        st.session_state.zoom_level = 12

if 'current_bounds' not in st.session_state:
    st.session_state.current_bounds = None
if 'last_bounds' not in st.session_state:
    st.session_state.last_bounds = None
if 'landmarks' not in st.session_state:
    st.session_state.landmarks = []
if 'show_circle' not in st.session_state:
    st.session_state.show_circle = False
if 'ai_landmarks' not in st.session_state:
    st.session_state.ai_landmarks = False
if 'offline_mode' not in st.session_state:
    st.session_state.offline_mode = False
if 'last_data_source' not in st.session_state:
    st.session_state.last_data_source = "Wikipedia"  # Default to Wikipedia

def get_landmarks(bounds: Tuple[float, float, float, float],
                  zoom_level: int,
                  data_source: str = 'Wikipedia') -> List[Dict]:
    """
    Fetch and cache landmarks for the given area
    """
    try:
        # If we're offline, try to get cached data
        if st.session_state.offline_mode:
            return cache_manager.get_cached_landmarks(bounds)

        # Only fetch new landmarks if zoom level is appropriate
        if zoom_level >= 8:  # Prevent fetching at very low zoom levels
            landmarks = []

            if data_source == "Wikipedia":
                from wiki_handler import WikiLandmarkFetcher
                wiki_fetcher = WikiLandmarkFetcher()
                landmarks = wiki_fetcher.get_landmarks(bounds)
            else:  # Google Places
                from google_places import GooglePlacesHandler
                places_handler = GooglePlacesHandler()
                landmarks = places_handler.get_landmarks(bounds)

            # Enhance landmarks with AI if not in offline mode
            if landmarks and st.session_state.ai_landmarks and not st.session_state.offline_mode:
                landmarks = [ai_handler.enhance_landmark_description(landmark) for landmark in landmarks]

            # Cache the landmarks for offline use
            if landmarks:
                cache_manager.cache_landmarks(landmarks, bounds)

            return landmarks
        else:
            return cache_manager.get_cached_landmarks(bounds)

    except Exception as e:
        st.error(f"Error fetching landmarks: {str(e)}")
        if st.session_state.offline_mode:
            return cache_manager.get_cached_landmarks(bounds)
        return []


def update_landmarks():
    """Update landmarks for the current map view."""
    if not st.session_state.current_bounds:
        return

    bounds = st.session_state.current_bounds
    try:
        with st.spinner('Fetching landmarks...'):
            landmarks = get_landmarks(
                bounds,
                st.session_state.zoom_level,
                data_source=st.session_state.last_data_source)
            if landmarks:
                st.session_state.landmarks = landmarks
                st.session_state.last_bounds = bounds
    except Exception as e:
        st.error(f"Error fetching landmarks: {str(e)}")

# Sidebar controls
st.sidebar.header("🗺️ Landmarks Locator")

# Show circle control
st.session_state.show_circle = st.sidebar.checkbox(
    "Show Location", value=st.session_state.show_circle)
radius_km = 1 if st.session_state.show_circle else 0

# AI landmarks toggle
st.session_state.ai_landmarks = st.sidebar.checkbox(
    "AI landmarks", value=st.session_state.ai_landmarks)

try:
    # Create base map
    m = folium.Map(location=st.session_state.map_center,
                   zoom_start=st.session_state.zoom_level,
                   tiles=cache_manager.get_tile_url(),
                   attr="OpenStreetMap" if st.session_state.offline_mode else "Google Maps",
                   control_scale=True,
                   prefer_canvas=True)

    # Add landmarks and distance circle if we have data
    if st.session_state.landmarks:
        add_landmarks_to_map(m, st.session_state.landmarks, False)
        if radius_km > 0:
            center = (float(st.session_state.map_center[0]),
                     float(st.session_state.map_center[1]))
            draw_distance_circle(m, center, radius_km)

    # Display map with full height
    map_data = st_folium(
        m,
        width=None,  # Let it take full width
        height=None,  # Let CSS control the height
        key="landmark_locator",
        returned_objects=["center", "zoom", "bounds"])

    # Handle map interactions
    if isinstance(map_data, dict):
        # Update center and zoom
        center_data = map_data.get("center")
        new_zoom = map_data.get("zoom")
        bounds_data = map_data.get("bounds")

        if isinstance(center_data, dict):
            new_lat = float(center_data.get("lat", st.session_state.map_center[0]))
            new_lng = float(center_data.get("lng", st.session_state.map_center[1]))
            st.session_state.map_center = [new_lat, new_lng]
            st.query_params['center'] = f"{new_lat},{new_lng}"

        # Handle zoom changes without forcing refresh
        if new_zoom is not None:
            new_zoom = int(float(new_zoom))  # Convert to float first to handle any decimal values
            if new_zoom != st.session_state.zoom_level:
                st.session_state.zoom_level = new_zoom
                st.query_params['zoom'] = str(new_zoom)

        # Update current bounds from map
        if bounds_data:
            st.session_state.current_bounds = (
                bounds_data['_southWest']['lat'],
                bounds_data['_southWest']['lng'],
                bounds_data['_northEast']['lat'],
                bounds_data['_northEast']['lng']
            )

    # Move search button to sidebar to maximize map space
    st.sidebar.markdown("---")
    if st.sidebar.button("🔍 Search This Area", type="primary"):
        update_landmarks()

except Exception as e:
    st.error(f"Error rendering map: {str(e)}")

# Display landmarks
landmarks_expander = st.sidebar.expander(
    f"View {len(st.session_state.landmarks)} Landmarks", expanded=False)
with landmarks_expander:
    for landmark in st.session_state.landmarks:
        with st.container():
            if st.session_state.ai_landmarks:
                st.subheader(landmark['title'])
                if 'enhanced_description' in landmark:
                    st.write(landmark['enhanced_description'])
                if 'historical_significance' in landmark:
                    st.write("**Historical Significance:**")
                    st.write(landmark['historical_significance'])
                if 'best_times' in landmark:
                    st.write("**Best Times to Visit:**")
                    st.write(landmark['best_times'])
                if 'interesting_facts' in landmark:
                    st.write("**Interesting Facts:**")
                    for fact in landmark['interesting_facts']:
                        st.markdown(f"• {fact}")
                st.divider()
            if 'image_url' in landmark:
                st.image(landmark['image_url'],
                        caption=f"[{landmark['title']}]({landmark['url']})",
                        use_container_width=True)

# Custom location
st.sidebar.markdown("---")

# Add combined coordinates input
combined_coords = st.sidebar.text_input(
    "Custom Location",
    help="Enter coordinates in either format:\n" +
    "• Decimal Degrees (DD): 37.3349, -122.0090\n" +
    "• DMS: 37°20'5.64\"N, 122°0'32.40\"W",
    placeholder="Enter coordinates (DD or DMS)",
    key="combined_coords")

# Initialize coordinate values
custom_lat = None
custom_lon = None
coords_valid = False

if combined_coords:
    coords = parse_coordinates(combined_coords)
    if coords:
        custom_lat = coords.lat
        custom_lon = coords.lon
        coords_valid = True
        st.sidebar.success(f"""
        ✅ Valid coordinates:
        • DD: {custom_lat:.4f}, {custom_lon:.4f}
        • DMS: {format_dms(custom_lat, True)}, {format_dms(custom_lon, False)}
        """)
    else:
        st.sidebar.error(
            "Invalid coordinate format. Please use DD or DMS format.")

# Separate lat/lon inputs with synced values
lat_input = st.sidebar.number_input(
    "Latitude",
    value=float(custom_lat if custom_lat is not None else st.session_state.
                map_center[0]),
    format="%.4f",
    help="Decimal degrees (e.g., 37.3349)",
    key="lat_input")

lon_input = st.sidebar.number_input(
    "Longitude",
    value=float(custom_lon if custom_lon is not None else st.session_state.
                map_center[1]),
    format="%.4f",
    help="Decimal degrees (e.g., -122.0090)",
    key="lon_input")

# Update values from separate inputs if combined input is empty
if not combined_coords:
    custom_lat = lat_input
    custom_lon = lon_input
    # Show both formats for separate input values
    if -90 <= lat_input <= 90 and -180 <= lon_input <= 180:
        st.sidebar.success(f"""
        ✅ Current coordinates:
        • DD: {custom_lat:.4f}, {custom_lon:.4f}
        • DMS: {format_dms(custom_lat, True)}, {format_dms(custom_lon, False)}
        """)

if st.sidebar.button("Go to Location"):
    if custom_lat is not None and custom_lon is not None and -90 <= custom_lat <= 90 and -180 <= custom_lon <= 180:
        st.session_state.map_center = [custom_lat, custom_lon]
        st.session_state.zoom_level = 12
        # Update URL parameters
        st.query_params['center'] = f"{custom_lat},{custom_lon}"
        st.query_params['zoom'] = str(st.session_state.zoom_level)
    else:
        st.sidebar.error(
            "Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180."
        )

st.sidebar.header("Map Controls")

# Offline Mode Toggle
offline_mode = st.sidebar.checkbox("📱 Offline Mode",
                                   value=st.session_state.offline_mode)
if offline_mode != st.session_state.offline_mode:
    st.session_state.offline_mode = offline_mode
    if offline_mode:
        st.sidebar.info("🔄 Offline mode enabled. Using cached map data.")
    else:
        st.sidebar.info("🌐 Online mode enabled. Fetching live data.")

# Add cache management controls
if st.session_state.offline_mode:
    st.sidebar.header("📦 Cache Management")

    # Display cache statistics
    cache_stats = cache_manager.get_cache_stats()
    st.sidebar.markdown(f"""
    **Cache Statistics:**
    - 📍 Landmarks: {cache_stats['landmarks_cached']}
    - 🖼️ Images: {cache_stats['images_cached']}
    - 🕒 Last Update: {cache_stats['last_update'] or 'Never'}
    """)

    # Cache management buttons
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("🔄 Update Cache"):
            # Force a cache update for current view
            if st.session_state.last_bounds:
                landmarks = get_landmarks(
                    st.session_state.last_bounds,
                    st.session_state.zoom_level,
                    data_source=st.session_state.last_data_source)
                if landmarks:
                    st.session_state.landmarks = landmarks
                    st.success("Cache updated successfully!")
    with col2:
        if st.button("🗑️ Clear Old Cache"):
            cache_manager.clear_old_cache()

# Update data source handling and trigger landmark refresh when changed
data_source = st.sidebar.radio(
    "Choose Landmarks Data Source",
    options=["Wikipedia", "Google Places"],
    help="Select where to fetch landmark information from",
    key="data_source")

if data_source != st.session_state.last_data_source:
    st.session_state.last_data_source = data_source
    # Force refresh of landmarks with new data source
    if st.session_state.last_bounds:
        try:
            landmarks = get_landmarks(st.session_state.last_bounds,
                                      st.session_state.zoom_level,
                                      data_source=data_source)
            if landmarks:
                st.session_state.landmarks = landmarks
            else:
                st.error("No landmarks found with selected data source.")
        except Exception as e:
            st.error(f"Error fetching landmarks: {str(e)}")
    st.rerun()

# Footer (removed due to CSS)