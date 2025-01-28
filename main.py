import streamlit as st
import folium
from streamlit_folium import st_folium
from google_places import GooglePlacesHandler
from map_utils import create_base_map, draw_distance_circle, add_landmarks_to_map
from cache_manager import get_cached_landmarks
import time
from urllib.parse import quote, unquote
import json
from journey_tracker import JourneyTracker
import hashlib
import os

# Page config
st.set_page_config(
    page_title="Local Landmarks Explorer",
    page_icon="🗺️",
    layout="wide"
)

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

if 'last_bounds' not in st.session_state:
    st.session_state.last_bounds = None
if 'landmarks' not in st.session_state:
    st.session_state.landmarks = []
if 'selected_landmark' not in st.session_state:
    st.session_state.selected_landmark = None
if 'show_heatmap' not in st.session_state:
    st.session_state.show_heatmap = False
if 'journey_tracker' not in st.session_state:
    st.session_state.journey_tracker = JourneyTracker()

# Title and description
st.title("🗺️ Local Landmarks Explorer")
st.markdown("""
Explore landmarks in your area with information from Google Places. 
Pan and zoom the map to discover new locations!
""")

# Sidebar controls
st.sidebar.header("Map Controls")

# Layer toggles
show_heatmap = st.sidebar.checkbox("Show Heatmap", value=st.session_state.show_heatmap)
st.session_state.show_heatmap = show_heatmap

# Filters
st.sidebar.header("Filters")
search_term = st.sidebar.text_input("Search landmarks", "")
min_rating = st.sidebar.slider("Minimum relevance score", 0.0, 1.0, 0.3)
radius_km = st.sidebar.number_input("Show distance circle (km)", min_value=0.0, max_value=50.0, value=0.0, step=0.5)

# Custom location
st.sidebar.header("Custom Location")
custom_lat = st.sidebar.number_input("Latitude", value=st.session_state.map_center[0], format="%.4f")
custom_lon = st.sidebar.number_input("Longitude", value=st.session_state.map_center[1], format="%.4f")

if st.sidebar.button("Go to Location"):
    st.session_state.map_center = [custom_lat, custom_lon]
    st.session_state.zoom_level = 12
    # Update URL parameters
    st.query_params['center'] = f"{custom_lat},{custom_lon}"
    st.query_params['zoom'] = str(st.session_state.zoom_level)

# Journey Progress
st.sidebar.markdown("---")
st.sidebar.header("🗺️ Journey Progress")

# Get current progress
progress = st.session_state.journey_tracker.get_progress()
total_discovered = progress["total_discovered"]

# Show progress metrics
st.sidebar.metric("Landmarks Discovered", total_discovered)

# Show achievements
if progress["achievements"]:
    st.sidebar.subheader("🏆 Achievements")
    for achievement in progress["achievements"]:
        st.sidebar.markdown(f"{achievement.icon} **{achievement.name}**")
        st.sidebar.caption(achievement.description)

# Show next achievement
if progress["next_achievement"]:
    next_achievement = progress["next_achievement"]
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Next Achievement")
    st.sidebar.markdown(f"{next_achievement.icon} **{next_achievement.name}**")
    st.sidebar.caption(next_achievement.description)
    st.sidebar.progress(min(total_discovered / next_achievement.requirement, 1.0))

# Main map container
map_col, info_col = st.columns([2, 1])

with map_col:
    try:
        # Create base map with Google Maps tiles
        m = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.zoom_level,
            tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={os.environ['GOOGLE_MAPS_API_KEY']}",
            attr="Google Maps",
            control_scale=True,
            prefer_canvas=True
        )

        # Add landmarks to map
        if st.session_state.landmarks:
            add_landmarks_to_map(m, st.session_state.landmarks, show_heatmap)

        # Add distance circle if radius is set
        if radius_km > 0:
            draw_distance_circle(m, tuple(st.session_state.map_center), radius_km)

        # Display map
        map_data = st_folium(
            m,
            width=800,
            height=600,
            key="landmark_explorer",
            returned_objects=["bounds", "center", "zoom"]
        )

        # Handle map interactions
        if isinstance(map_data, dict):
            # Update center if changed
            center_data = map_data.get("center")
            if isinstance(center_data, dict):
                lat = float(center_data.get("lat", st.session_state.map_center[0]))
                lng = float(center_data.get("lng", st.session_state.map_center[1]))
                st.session_state.map_center = [lat, lng]
                st.query_params['center'] = f"{lat},{lng}"

            # Update zoom level if changed
            zoom = map_data.get("zoom")
            if zoom is not None:
                st.session_state.zoom_level = int(zoom)
                st.query_params['zoom'] = str(zoom)

            # Handle bounds updates
            bounds = map_data.get("bounds")
            if isinstance(bounds, dict):
                sw = bounds.get("_southWest", {})
                ne = bounds.get("_northEast", {})

                if isinstance(sw, dict) and isinstance(ne, dict):
                    new_bounds = (
                        float(sw.get("lat", 0)),
                        float(sw.get("lng", 0)),
                        float(ne.get("lat", 0)),
                        float(ne.get("lng", 0))
                    )

                    if all(isinstance(x, float) for x in new_bounds):
                        if (st.session_state.last_bounds is None or
                            new_bounds != st.session_state.last_bounds):
                            try:
                                landmarks = get_cached_landmarks(new_bounds, st.session_state.zoom_level)
                                if landmarks:
                                    st.session_state.landmarks = landmarks
                                    st.session_state.last_bounds = new_bounds
                            except Exception as e:
                                st.error(f"Error fetching landmarks: {str(e)}")

    except Exception as e:
        st.error(f"Error rendering map: {str(e)}")

with info_col:
    # Filter landmarks based on search and rating
    filtered_landmarks = [
        l for l in st.session_state.landmarks
        if (search_term.lower() in l['title'].lower() or not search_term)
        and l['relevance'] >= min_rating
    ]

    st.subheader(f"Found {len(filtered_landmarks)} Landmarks")

    # Display landmarks with discovery tracking
    def process_landmark_discovery(landmark):
        """Process landmark discovery and handle animations"""
        # Create unique ID for landmark
        landmark_id = hashlib.md5(f"{landmark['title']}:{landmark['coordinates']}".encode()).hexdigest()

        # Check if this is a new discovery
        discovery_info = st.session_state.journey_tracker.add_discovery(landmark_id, landmark['title'])

        if discovery_info["is_new"]:
            # Show discovery animation
            st.balloons()

            # Show achievement notifications
            for achievement in discovery_info.get("new_achievements", []):
                st.success(f"🎉 Achievement Unlocked: {achievement.icon} {achievement.name}")
                st.toast(f"New Achievement: {achievement.name}")

    # Display landmarks
    for landmark in filtered_landmarks:
        with st.expander(landmark['title']):
            process_landmark_discovery(landmark)

            # Display the landmark image if available
            if 'image_url' in landmark:
                st.image(landmark['image_url'], caption=landmark['title'], use_container_width=True)

            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem;'>
                <h3 style='margin-top: 0;'>{landmark['title']}</h3>
                <p><strong>🎯 Relevance:</strong> {landmark['relevance']:.2f}</p>
                <p><strong>📍 Distance:</strong> {landmark['distance']:.1f}km</p>
                <p>{landmark['summary']}</p>
                <a href='{landmark['url']}' target='_blank'>Read more on Google Places</a>
            </div>
            """, unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
Data sourced from Google Places. Updates automatically as you explore the map.
* 🔴 Red markers: High relevance landmarks
* 🟠 Orange markers: Medium relevance landmarks
* 🔵 Blue markers: Lower relevance landmarks
""")

def get_cached_landmarks(bounds, zoom_level):
    # Placeholder - Replace with actual caching logic using bounds and zoom level
    try:
        return cache_landmarks(bounds)
    except:
        return []