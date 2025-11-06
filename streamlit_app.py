import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk

try:
    import reverse_geocoder as rg
    from country_converter import CountryConverter
    HAS_GEO = True
except Exception:
    HAS_GEO = False

st.set_page_config(page_title="Global Earthquakes Dashboard", page_icon="🌍", layout="wide")
st.title("🌍 실시간 지진 대시보드 (USGS) + 대륙/국가 집계")

col0, col1, col2, col3 = st.columns([1.2,1,1,1])
with col0:
    period = st.selectbox("기간", ["최근 24시간", "최근 7일", "최근 30일"], index=1)
with col1:
    mag_class = st.selectbox("규모 구간", ["전체(all)", "M2.5+", "M4.5+", "Significant"])
with col2:
    min_mag = st.slider("최소 규모(추가 필터)", 0.0, 8.0, 0.0, 0.1)
with col3:
    q = st.text_input("지역 키워드(예: Japan, Alaska 등)", "")

period_map = {"최근 24시간": "day", "최근 7일": "week", "최근 30일": "month"}
mag_map = {"전체(all)": "all", "M2.5+": "2.5"_
