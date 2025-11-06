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
mag_map = {"전체(all)": "all", "M2.5+": "2.5", "M4.5+": "4.5", "Significant": "significant"}
url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{mag_map[mag_class]}_{period_map[period]}.csv"

@st.cache_data(ttl=3600)
def load(url):
    df = pd.read_csv(url)
    df["time"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"latitude":"lat", "longitude":"lon", "mag":"magnitude"})
    return df

with st.spinner("데이터 불러오는 중..."):
    df = load(url)

f = df.copy()
if q:
    f = f[f["place"].str.contains(q, case=False, na=False)]
f = f[f["magnitude"] >= min_mag].copy()

@st.cache_data
def enrich_country_continent(df_input: pd.DataFrame) -> pd.DataFrame:
    df_geo = df_input.copy()
    coords = list(zip(df_geo["lat"].astype(float), df_geo["lon"].astype(float)))
    hits = rg.search(coords, mode=2)
    df_geo["country_code"] = [h["cc"] for h in hits]
    cc = CountryConverter()
    df_geo["country"] = cc.convert(df_geo["country_code"], to="name_short")
    df_geo["continent"] = cc.convert(df_geo["country_code"], to="continent")
    return df_geo

if HAS_GEO and not f.empty:
    with st.spinner("위치 → 국가/대륙 매핑 중..."):
        f = enrich_country_continent(f)
else:
    if not HAS_GEO:
        st.info("대륙/국가 집계를 사용하려면 다음 패키지를 설치하세요: `pip install reverse_geocoder country_converter`")
    f["country"] = np.nan
    f["continent"] = np.nan

c1, c2, c3, c4 = st.columns(4)
c1.metric("이벤트 수", f"{len(f):,}")
c2.metric("최대 규모", f"{f['magnitude'].max():.1f}" if len(f) else "-")
c3.metric("평균 규모", f"{f['magnitude'].mean():.2f}" if len(f) else "-")
c4.metric("평균 깊이(km)", f"{f['depth'].mean():.1f}" if len(f) else "-")

st.divider()

tab_map, tab_trend, tab_region, tab_data = st.tabs(["🗺️ 지도", "📈 추세", "🌐 지역 집계", "🗃️ 데이터"])

with tab_map:
    st.subheader("📍 지진 위치")
    if len(f):
        mag = f["magnitude"].fillna(0).clip(lower=0, upper=8)
        color = ((mag / 8) * 255).astype(int)
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=f.assign(
                color_r=color,
                color_g=(255 - color),
                color_b=80,
                size=(mag * 2 + 4)
            ),
            get_position='[lon, lat]',
            get_color='[color_r, color_g, color_b, 160]',
            get_radius='size',
            pickable=True,
        )
        view_state = pdk.ViewState(latitude=0, longitude=0, zoom=1.1)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state,
                                 tooltip={"text": "{place}\nM{magnitude} • depth {depth} km"}))
    else:
        st.info("표시할 결과가 없습니다. 필터를 조정해 보세요.")

with tab_trend:
    st.subheader("🔢 규모 히스토그램")
    if len(f):
        hist = np.histogram(f["magnitude"].dropna(), bins=20, range=(0, max(8, f["magnitude"].max())))
        st.bar_chart(pd.DataFrame({"count": hist[0]}, index=pd.Index(hist[1][:-1], name="mag")), use_container_width=True)
    st.subheader("⏱️ 시간대별 발생 수(3시간 단위)")
    if len(f):
        ts = f.set_index("time").resample("3H")["id"].count()
        st.line_chart(ts, use_container_width=True)

with tab_region:
    st.subheader("🌐 대륙·국가별 집계")
    if len(f) and f["continent"].notna().any():
        cont_df = f.groupby("continent", dropna=True).agg(events=("id","count"),
                  max_mag=("magnitude","max"), avg_mag=("magnitude","mean"),
                  avg_depth=("depth","mean")).sort_values("events", ascending=False).reset_index()
        st.markdown("**대륙별 요약**")
        st.dataframe(cont_df, use_container_width=True)
        st.bar_chart(cont_df.set_index("continent")["events"], use_container_width=True)

        country_df = f.groupby("country", dropna=True).agg(events=("id","count"),
                  max_mag=("magnitude","max"), avg_mag=("magnitude","mean"),
                  avg_depth=("depth","mean")).sort_values("events", ascending=False).head(20).reset_index()
        st.markdown("**국가별 요약 (Top 20)**")
        st.dataframe(country_df, use_container_width=True)
    else:
        st.info("대륙/국가 매핑 결과가 없습니다.")

with tab_data:
    with st.expander("원본 데이터 보기 / 다운로드"):
        cols = ["time","magnitude","depth","place","lat","lon","type","status","id"]
        extra = [c for c in ["country","continent","country_code"] if c in f.columns]
        show_cols = [c for c in cols + extra if c in f.columns]
        st.dataframe(f[show_cols], use_container_width=True)
        st.download_button("CSV 다운로드", f[show_cols].to_csv(index=False).encode("utf-8"),
                           "earthquakes_filtered.csv", "text/csv")

st.caption("데이터 출처: USGS Earthquake Hazards Program. "
           "대륙/국가 매핑: reverse_geocoder + country_converter.")
