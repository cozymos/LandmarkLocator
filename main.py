import streamlit as st
import folium
from streamlit_folium import st_folium
from wiki_handler import WikiLandmarkFetcher
from map_utils import get_map_bounds, create_base_map
from cache_manager import cache_landmarks
import time

# Page config
st.set_page_config(
    page_title="Local Landmarks Explorer",
    page_icon="🗺️",
    layout="wide"
)

# Initialize session state
if 'last_bounds' not in st.session_state:
    st.session_state.last_bounds = None
if 'landmarks' not in st.session_state:
    st.session_state.landmarks = []

# Title and description
st.title("🗺️ Local Landmarks Explorer")
st.markdown("""
Explore landmarks in your area with information from Wikipedia. 
Pan and zoom the map to discover new locations!
""")

# Sidebar filters
st.sidebar.header("Filters")
search_term = st.sidebar.text_input("Search landmarks", "")
min_rating = st.sidebar.slider("Minimum relevance score", 0.0, 1.0, 0.3)

# Initialize wiki fetcher
wiki_fetcher = WikiLandmarkFetcher()

# Create base map
m = create_base_map()

# Main map container
map_col, info_col = st.columns([2, 1])

with map_col:
    # Display map using st_folium instead of folium_static
    map_data = st_folium(m, width=800)

    # Get current map bounds if map_data is available
    if map_data is not None and 'bounds' in map_data:
        bounds = (
            map_data['bounds']['_southWest']['lat'],
            map_data['bounds']['_southWest']['lng'],
            map_data['bounds']['_northEast']['lat'],
            map_data['bounds']['_northEast']['lng']
        )

        if bounds != st.session_state.last_bounds:
            with st.spinner("Fetching landmarks..."):
                try:
                    # Fetch and cache landmarks
                    landmarks = cache_landmarks(bounds, wiki_fetcher)
                    st.session_state.landmarks = landmarks
                    st.session_state.last_bounds = bounds
                except Exception as e:
                    st.error(f"Error fetching landmarks: {str(e)}")
                    landmarks = []

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
            st.markdown(f"**Distance:** {landmark['distance']:.1f}km")
            st.markdown(f"**Relevance:** {landmark['relevance']:.2f}")
            st.markdown(landmark['summary'])
            st.markdown(f"[Read more on Wikipedia]({landmark['url']})")

# Footer
st.markdown("---")
st.markdown("Data sourced from Wikipedia. Updates automatically as you explore the map.")