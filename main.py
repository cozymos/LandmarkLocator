import streamlit as st
import folium
from streamlit_folium import st_folium
from wiki_handler import WikiLandmarkFetcher
from map_utils import create_base_map, draw_distance_circle, add_landmarks_to_map
from cache_manager import cache_landmarks
import time

# Page config
st.set_page_config(
    page_title="Local Landmarks Explorer",
    page_icon="🗺️",
    layout="wide"
)

# Initialize session state for map persistence
if 'last_bounds' not in st.session_state:
    st.session_state.last_bounds = None
if 'landmarks' not in st.session_state:
    st.session_state.landmarks = []
if 'selected_landmark' not in st.session_state:
    st.session_state.selected_landmark = None
if 'show_heatmap' not in st.session_state:
    st.session_state.show_heatmap = False
if 'map_center' not in st.session_state:
    st.session_state.map_center = [37.7749, -122.4194]  # Default to San Francisco
if 'zoom_level' not in st.session_state:
    st.session_state.zoom_level = 12

# Title and description
st.title("🗺️ Local Landmarks Explorer")
st.markdown("""
Explore landmarks in your area with information from Wikipedia. 
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

# Main map container
map_col, info_col = st.columns([2, 1])

with map_col:
    try:
        # Create base map
        m = create_base_map()

        # Add landmarks to map
        if st.session_state.landmarks:
            add_landmarks_to_map(m, st.session_state.landmarks, show_heatmap)

        # Add distance circle if radius is set
        if radius_km > 0:
            draw_distance_circle(m, tuple(st.session_state.map_center), radius_km)

        # Display map with state persistence
        map_data = st_folium(
            m,
            key=f"landmark_map_{st.session_state.map_center[0]}_{st.session_state.map_center[1]}",
            width=800,
            height=600,
            returned_objects=["bounds", "center", "zoom"]
        )

        # Update map state if data is available
        if map_data:
            # Update center and zoom
            center_data = map_data.get("center", {})
            if center_data and isinstance(center_data, dict):
                lat = center_data.get("lat")
                lng = center_data.get("lng")
                if lat is not None and lng is not None:
                    st.session_state.map_center = [float(lat), float(lng)]

            zoom = map_data.get("zoom")
            if zoom is not None:
                st.session_state.zoom_level = zoom

            # Process bounds for landmarks
            bounds_data = map_data.get("bounds", {})
            if bounds_data and isinstance(bounds_data, dict):
                sw = bounds_data.get("_southWest", {})
                ne = bounds_data.get("_northEast", {})

                if (sw and ne and 
                    all(key in sw and sw[key] is not None for key in ["lat", "lng"]) and
                    all(key in ne and ne[key] is not None for key in ["lat", "lng"])):

                    new_bounds = (
                        float(sw["lat"]),
                        float(sw["lng"]),
                        float(ne["lat"]),
                        float(ne["lng"])
                    )

                    # Only fetch new landmarks if bounds have changed
                    if new_bounds != st.session_state.last_bounds:
                        try:
                            landmarks = cache_landmarks(new_bounds)
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

    # Display landmarks
    for landmark in filtered_landmarks:
        with st.expander(landmark['title']):
            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem;'>
                <h3 style='margin-top: 0;'>{landmark['title']}</h3>
                <p><strong>🎯 Relevance:</strong> {landmark['relevance']:.2f}</p>
                <p><strong>📍 Distance:</strong> {landmark['distance']:.1f}km</p>
                <p>{landmark['summary']}</p>
                <a href='{landmark['url']}' target='_blank'>Read more on Wikipedia</a>
            </div>
            """, unsafe_allow_html=True)

            # Add buttons for interaction
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Show Distance Circle ({landmark['title']})", key=f"circle_{landmark['title']}"):
                    draw_distance_circle(m, landmark['coordinates'], radius_km if radius_km > 0 else 1.0)
            with col2:
                if st.button(f"Center Map ({landmark['title']})", key=f"center_{landmark['title']}"):
                    st.session_state.map_center = list(landmark['coordinates'])

# Footer
st.markdown("---")
st.markdown("""
Data sourced from Wikipedia. Updates automatically as you explore the map.
* 🔴 Red markers: High relevance landmarks
* 🟠 Orange markers: Medium relevance landmarks
* 🔵 Blue markers: Lower relevance landmarks
""")