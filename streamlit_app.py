import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Global Earthquakes Dashboard", page_icon="🌍", layout="wide")
st.title("🌍 실시간 지진 대시보드 (USGS)")

# --- Controls ---
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

@st.cache_data(show_spinner=False)
def load(url):
    df = pd.read_csv(url)
    # 표준 컬럼 정리
    df["time"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"latitude":"lat", "longitude":"lon", "mag":"magnitude"})
    return df

with st.spinner("데이터 불러오는 중..."):
    df = load(url)

# --- Filtering ---
f = df.copy()
if q:
    f = f[f["place"].str.contains(q, case=False, na=False)]
f = f[f["magnitude"] >= min_mag]

# --- KPIs ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("이벤트 수", f"{len(f):,}")
c2.metric("최대 규모", f"{f['magnitude'].max():.1f}" if len(f) else "-")
c3.metric("평균 규모", f"{f['magnitude'].mean():.2f}" if len(f) else "-")
c4.metric("평균 깊이(km)", f"{f['depth'].mean():.1f}" if len(f) else "-")

st.divider()

# --- Layout: Map + Charts ---
mcol, rcol = st.columns([1.2, 1])
with mcol:
    st.subheader("📍 위치(지명은 place 컬럼)")
    if len(f):
        # st.map은 lat/lon 필요
        st.map(f[["lat","lon"]], use_container_width=True)
    else:
        st.info("표시할 결과가 없습니다. 필터를 조정해 보세요.")

with rcol:
    st.subheader("🔢 규모 히스토그램")
    if len(f):
        hist = np.histogram(f["magnitude"].dropna(), bins=20, range=(0, max(8, f["magnitude"].max())))
        st.bar_chart(pd.DataFrame({"count": hist[0]}, index=pd.Index(hist[1][:-1], name="mag")), use_container_width=True)
    else:
        st.empty()

    st.subheader("⏱️ 시간대별 발생 수")
    if len(f):
        ts = f.set_index("time").resample("3H")["id"].count()
        st.line_chart(ts, use_container_width=True)
    else:
        st.empty()

# --- Data view & download ---
with st.expander("원본 데이터 보기 / 다운로드"):
    st.dataframe(f[["time","magnitude","depth","place","lat","lon","type","status","id"]], use_container_width=True)
    st.download_button("CSV 다운로드", f.to_csv(index=False).encode("utf-8"), "earthquakes_filtered.csv", "text/csv")

st.caption("데이터 출처: USGS Earthquake Hazards Program 실시간 피드(기간/규모별 CSV).")
