import streamlit as st
import folium
from streamlit_folium import st_folium
from google_places import GooglePlacesHandler
from map_utils import create_base_map, draw_distance_circle, add_landmarks_to_map
from cache_manager import get_cached_landmarks, cache_manager
import time
from urllib.parse import quote, unquote
import json
from journey_tracker import JourneyTracker
import hashlib
import os
from recommender import LandmarkRecommender
from weather_handler import WeatherHandler
from coord_utils import parse_coordinates, format_dms
from wiki_handler import WikiLandmarkFetcher  # Fixed import


# Page config
st.set_page_config(
    page_title="Local Landmarks Explorer",
    page_icon="🗺️",
    layout="wide"
)

# Add debounce time to session state
if 'last_update_time' not in st.session_state:
    st.session_state.last_update_time = 0

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
if 'recommender' not in st.session_state:
    st.session_state.recommender = LandmarkRecommender()
if 'weather_handler' not in st.session_state:
    st.session_state.weather_handler = WeatherHandler()
if 'offline_mode' not in st.session_state:
    st.session_state.offline_mode = False
if 'wiki_language' not in st.session_state: #added for language selection
    st.session_state.wiki_language = "en" #default language
if 'last_data_source' not in st.session_state:
    st.session_state.last_data_source = "Google Places"  # Set Google Places as default


# Update the CSS section at the beginning of the file
st.markdown("""
<style>
    .recommended-image {
        width: 100%;
        height: 150px;  /* Reduced height */
        object-fit: cover;
        border-radius: 10px;
        margin-bottom: 4px;  /* Reduced margin */
    }
    .recommendation-card {
        padding: 8px;  /* Reduced padding */
        border-radius: 8px;
        background-color: #f0f2f6;
        margin: 4px;  /* Reduced margin */
        height: 100%;
    }
    .recommendation-title {
        font-size: 14px;  /* Smaller font */
        font-weight: 500;
        margin: 4px 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .recommendation-score {
        font-size: 12px;  /* Smaller font */
        color: #555;
    }
    .placeholder-image {
        width: 100%;
        height: 150px;  /* Match reduced height */
        background-color: #e0e0e0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        margin-bottom: 4px;
        font-size: 14px;  /* Smaller font */
    }
    /* Make the map container take up more space */
    .stfolium-container {
        width: 100% !important;
    }
    /* Reduce padding in sidebar elements */
    .streamlit-expanderHeader {
        padding: 0.5rem !important;
    }
    /* Compact sidebar content */
    .sidebar .element-container {
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Title and description
st.title("🗺️ Local Landmarks Explorer")
st.markdown("""
Explore landmarks in your area with information from Google Places. 
Pan and zoom the map to discover new locations!
""")

# Recommendations section
st.markdown("### 🎯 Recommended Landmarks")
if st.session_state.landmarks:
    recommendations = st.session_state.recommender.get_recommendations(
        st.session_state.landmarks,
        st.session_state.map_center,
        top_n=3  # Reduce to 3 recommendations to save space
    )

    if recommendations:
        rec_cols = st.columns(len(recommendations))
        for i, landmark in enumerate(recommendations):
            with rec_cols[i]:
                # Create image HTML with error handling
                image_html = ""
                if landmark.get('image_url'):
                    try:
                        image_html = f'<img src="{landmark["image_url"]}" class="recommended-image" onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'flex\';">'
                        image_html += '<div class="placeholder-image" style="display:none;">📍 No image available</div>'
                    except Exception:
                        image_html = '<div class="placeholder-image">📍 No image available</div>'
                else:
                    image_html = '<div class="placeholder-image">📍 No image available</div>'

                st.markdown(f"""
                <div class="recommendation-card">
                    {image_html}
                    <div class="recommendation-title">{landmark['title']}</div>
                    <div class="recommendation-score">Score: {landmark['personalized_score']:.2f}</div>
                </div>
                """, unsafe_allow_html=True)


# Display total landmarks count
filtered_landmarks = [
    l for l in st.session_state.landmarks
    if (search_term.lower() in l['title'].lower() or not search_term)
    and l['relevance'] >= min_rating
]
st.markdown(f"**Found {len(filtered_landmarks)} landmarks in this area**")


# Create the main map - now taking most of the width
try:
    # Get appropriate tile URL based on mode
    tile_url = cache_manager.get_tile_url(os.environ['GOOGLE_MAPS_API_KEY'])

    # Create base map
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.zoom_level,
        tiles=tile_url,
        attr="Map data © OpenStreetMap contributors" if st.session_state.offline_mode else "Google Maps",
        control_scale=True,
        prefer_canvas=True
    )

    # Add landmarks and distance circle if we have data
    if st.session_state.landmarks:
        add_landmarks_to_map(m, st.session_state.landmarks, show_heatmap)
        if radius_km > 0:
            draw_distance_circle(m, tuple(st.session_state.map_center), radius_km)

    # Display map with minimal returned objects
    map_data = st_folium(
        m,
        width=None,  # Let it take full width
        height=600,
        key="landmark_explorer",
        returned_objects=["center", "zoom"]
    )

    # Handle map interactions with optimized updates
    if isinstance(map_data, dict) and time.time() - st.session_state.last_update_time > 1.0:  # 1 second debounce
        center_data = map_data.get("center")
        new_zoom = map_data.get("zoom")

        # Batch updates to reduce state changes
        updates_needed = False

        if isinstance(center_data, dict):
            new_lat = float(center_data.get("lat", st.session_state.map_center[0]))
            new_lng = float(center_data.get("lng", st.session_state.map_center[1]))

            # Check if center changed significantly
            if abs(new_lat - st.session_state.map_center[0]) > 0.001 or \
               abs(new_lng - st.session_state.map_center[1]) > 0.001:
                st.session_state.map_center = [new_lat, new_lng]
                updates_needed = True

        # Update zoom if changed
        if new_zoom is not None and new_zoom != st.session_state.zoom_level:
            st.session_state.zoom_level = int(new_zoom)
            updates_needed = True

        # Only fetch new landmarks if significant changes occurred
        if updates_needed:
            # Update URL parameters in batch
            st.query_params.update({
                'center': f"{st.session_state.map_center[0]},{st.session_state.map_center[1]}",
                'zoom': str(st.session_state.zoom_level)
            })

            # Calculate bounds only when needed
            zoom_factor = 360 / (2 ** st.session_state.zoom_level)
            new_bounds = (
                st.session_state.map_center[0] - zoom_factor * 0.3,  # Reduced view area
                st.session_state.map_center[1] - zoom_factor * 0.4,
                st.session_state.map_center[0] + zoom_factor * 0.3,
                st.session_state.map_center[1] + zoom_factor * 0.4
            )

            # Check if bounds changed enough to warrant new data
            if st.session_state.last_bounds is None or \
               any(abs(a - b) > zoom_factor * 0.1 for a, b in zip(new_bounds, st.session_state.last_bounds)):
                try:
                    landmarks = get_cached_landmarks(
                        new_bounds,
                        st.session_state.zoom_level,
                        st.session_state.offline_mode,
                        st.session_state.wiki_language,
                        data_source
                    )
                    if landmarks:
                        st.session_state.landmarks = landmarks
                        st.session_state.last_bounds = new_bounds
                except Exception as e:
                    st.error(f"Error fetching landmarks: {str(e)}")

            st.session_state.last_update_time = time.time()

except Exception as e:
    st.error(f"Error rendering map: {str(e)}")


# Move landmarks list to sidebar
st.sidebar.markdown("---")
st.sidebar.header("📍 Landmarks List")
landmarks_expander = st.sidebar.expander("View All Landmarks", expanded=False)
with landmarks_expander:
    for landmark in filtered_landmarks:
        with st.container():
            process_landmark_discovery(landmark)

            # Record interaction with landmark
            st.session_state.recommender.record_interaction(
                str(landmark['coordinates']),
                landmark.get('type', 'landmark'),
                landmark['distance']  # Add the distance parameter
            )

            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                <h4 style='margin: 0;'>{landmark['title']}</h4>
                <p style='margin: 0.2rem 0;'><strong>🎯 {landmark['relevance']:.2f}</strong> • <strong>📍 {landmark['distance']:.1f}km</strong></p>
                <p style='margin: 0.2rem 0; font-size: 0.9em;'>{landmark['summary'][:100]}...</p>
                <a href='{landmark['url']}' target='_blank' style='font-size: 0.9em;'>More info</a>
            </div>
            """, unsafe_allow_html=True)

# Sidebar controls (rest of the sidebar remains the same)
st.sidebar.header("Map Controls")

# Layer toggles
show_heatmap = st.sidebar.checkbox("Show Heatmap", value=st.session_state.show_heatmap)
st.session_state.show_heatmap = show_heatmap

# Offline Mode Toggle
offline_mode = st.sidebar.checkbox("📱 Offline Mode", value=st.session_state.offline_mode)
if offline_mode != st.session_state.offline_mode:
    st.session_state.offline_mode = offline_mode
    if offline_mode:
        st.sidebar.info("🔄 Offline mode enabled. Using cached map data.")
    else:
        st.sidebar.info("🌐 Online mode enabled. Fetching live data.")


# Data source selector
st.sidebar.markdown("---")
st.sidebar.header("🗃️ Data Source")
data_source = st.sidebar.radio(
    "Choose Landmarks Data Source",
    options=["Google Places", "Wikipedia"],  # Reorder to make Google Places first
    help="Select where to fetch landmark information from"
)

if 'last_data_source' not in st.session_state:
    st.session_state.last_data_source = data_source
elif st.session_state.last_data_source != data_source:
    st.session_state.last_data_source = data_source
    st.session_state.landmarks = []  # Clear landmarks when switching source
    st.sidebar.success(f"Switched to {data_source} data source")

# Language selector (only show for Wikipedia source)
if data_source == "Wikipedia":
    st.sidebar.markdown("---")
    st.sidebar.header("🌍 Language Settings")
    wiki_fetcher = WikiLandmarkFetcher()
    languages = wiki_fetcher.get_supported_languages()
    selected_language = st.sidebar.selectbox(
        "Select Language",
        options=list(languages.keys()),
        format_func=lambda x: languages[x],
        index=list(languages.keys()).index(st.session_state.wiki_language),
        help="Choose the language for landmark information"
    )

    # Update language if changed
    if selected_language != st.session_state.wiki_language:
        if wiki_fetcher.set_language(selected_language):
            st.session_state.wiki_language = selected_language
            st.sidebar.success(f"Language changed to {languages[selected_language]}")
            st.session_state.landmarks = []
        else:
            st.sidebar.error("Failed to change language")

# Filters
st.sidebar.header("Filters")
search_term = st.sidebar.text_input("Search landmarks", "")
min_rating = st.sidebar.slider("Minimum relevance score", 0.0, 1.0, 0.3)
radius_km = st.sidebar.number_input("Show distance circle (km)", min_value=0.0, max_value=50.0, value=0.0, step=0.5)

# Custom location
st.sidebar.header("Custom Location")

# Add combined coordinates input
combined_coords = st.sidebar.text_input(
    "Enter Coordinates",
    help="Enter coordinates in either format:\n" +
         "• Decimal Degrees (DD): 37.3349, -122.0090\n" +
         "• DMS: 37°20'5.64\"N, 122°0'32.40\"W",
    placeholder="Enter coordinates (DD or DMS)",
    key="combined_coords"
)

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
        st.sidebar.error("Invalid coordinate format. Please use DD or DMS format.")

# Separate lat/lon inputs with synced values
lat_input = st.sidebar.number_input(
    "Latitude", 
    value=float(custom_lat if custom_lat is not None else st.session_state.map_center[0]),
    format="%.4f",
    help="Decimal degrees (e.g., 37.3349)",
    key="lat_input"
)

lon_input = st.sidebar.number_input(
    "Longitude", 
    value=float(custom_lon if custom_lon is not None else st.session_state.map_center[1]),
    format="%.4f",
    help="Decimal degrees (e.g., -122.0090)",
    key="lon_input"
)

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
        st.sidebar.error("Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180.")

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

# Add this after the Journey Progress section in the sidebar
st.sidebar.markdown("---")
st.sidebar.header("📊 Travel Insights")

# Get travel insights
travel_insights = st.session_state.recommender.get_travel_insights()

# Display insights with emojis and formatting
if travel_insights['avg_distance'] is not None:
    st.sidebar.markdown(f"""
    🕒 Favorite Time: {travel_insights['favorite_time'].title()}
    🌞 Preferred Season: {travel_insights['preferred_season'].title()}
    📍 Average Distance: {travel_insights['avg_distance']:.1f} km
    📅 Usually Visits: {travel_insights['preferred_day_type'].title()}s
    """)

    # Show top categories
    st.sidebar.markdown("**Top Categories:**")
    for category, weight in travel_insights['frequent_categories']:
        st.sidebar.markdown(f"🏷️ {category.replace('_', ' ').title()}")

    # Show exploration statistics
    st.sidebar.markdown(f"🗺️ Explored Areas: {travel_insights['num_clusters']}")


st.sidebar.markdown("---")
st.sidebar.header("📍 Local Weather")
if st.session_state.map_center:
    weather_data = st.session_state.weather_handler.get_weather(
        st.session_state.map_center[0],
        st.session_state.map_center[1]
    )
    if weather_data:
        st.sidebar.markdown(
            st.session_state.weather_handler.format_weather_html(weather_data),
            unsafe_allow_html=True
        )
    else:
        st.sidebar.warning("Unable to fetch weather data")



# Footer
st.markdown("---")
st.markdown("""
Data sourced from Google Places. Updates automatically as you explore the map.
* 🔴 Red markers: High relevance landmarks
* 🟠 Orange markers: Medium relevance landmarks
* 🔵 Blue markers: Lower relevance landmarks
""")

def get_cached_landmarks(bounds, zoom_level, offline_mode, language, data_source): #added data_source parameter
    try:
        return cache_manager.cache_landmarks(bounds, zoom_level, offline_mode, language, data_source) #pass data source to cache_manager
    except:
        return []

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