import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk

st.set_page_config(page_title="Global Earthquakes Dashboard", page_icon="🌍", layout="wide")
st.title("🌍 실시간 지진 대시보드 (USGS) + 대륙/국가 집계")

# ---------------------------
# 0) 안전 옵션 & 유틸
# ---------------------------
def coalesce_col(df: pd.DataFrame, targets, fallback=None, cast=None):
    """여러 후보 컬럼명 중 존재하는 것을 선택해 반환. 없으면 fallback 생성."""
    for c in targets:
        if c in df.columns:
            return df[c] if cast is None else df[c].astype(cast, errors="ignore")
    # 없으면 새로 만들기
    df[targets[0]] = fallback
    return df[targets[0]]

# ---------------------------
# 1) 컨트롤
# ---------------------------
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
URL = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{mag_map[mag_class]}_{period_map[period]}.csv"

# ---------------------------
# 2) 데이터 로드 & 스키마 정규화
# ---------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_data(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)
    # 시간
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    else:
        df["time"] = pd.NaT

    # 위경도/규모/깊이 표준화
    # 일부 환경에서 dtype 문제로 에러날 수 있으니 to_numeric 사용
    df.rename(columns={"latitude":"lat", "longitude":"lon", "mag":"magnitude"}, inplace=True)

    for col in ["lat", "lon", "magnitude", "depth"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 문자열 컬럼 안전 처리
    if "place" not in df.columns:
        df["place"] = ""
    else:
        df["place"] = df["place"].fillna("")

    # id 없으면 만들어주기
    if "id" not in df.columns:
        df["id"] = pd.util.hash_pandas_object(df[["time","lat","lon"]], index=False).astype(str)

    return df

with st.spinner("데이터 불러오는 중..."):
    df = load_data(URL)

# 필터
f = df.copy()
if q:
    f = f[f["place"].str.contains(q, case=False, na=False)]
f = f[f["magnitude"].fillna(0) >= min_mag].copy()

# ---------------------------
# 3) 대륙/국가 매핑 (선택적)
# ---------------------------
@st.cache_data(show_spinner=False)
def enrich_country_continent(df_input: pd.DataFrame) -> pd.DataFrame:
    """reverse_geocoder + country_converter가 있을 때만 매핑."""
    try:
        import reverse_geocoder as rg
        from country_converter import CountryConverter
    except Exception:
        # 라이브러리 없으면 원본 반환 (안전)
        out = df_input.copy()
        out["country"] = np.nan
        out["continent"] = np.nan
        out["country_code"] = np.nan
        return out

    out = df_input.copy()
    # 좌표 유효한 행만 매핑
    valid = out[["lat","lon"]].dropna()
    if valid.empty:
        out["country"] = np.nan
        out["continent"] = np.nan
        out["country_code"] = np.nan
        return out

    coords = list(zip(valid["lat"].astype(float), valid["lon"].astype(float)))
    hits = rg.search(coords, mode=2)  # 벡터화 모드
    iso2 = pd.Series([h["cc"] for h in hits], index=valid.index)

    out["country_code"] = np.nan
    out.loc[iso2.index, "country_code"] = iso2.values

    cc = CountryConverter()
    out["country"] = cc.convert(out["country_code"], to="name_short", not_found=None)
    out["continent"] = cc.convert(out["country_code"], to="continent", not_found=None)
    return out

with st.spinner("위치 → 국가/대륙 매핑 중... (없어도 앱은 정상 동작)"):
    f = enrich_country_continent(f)

# ---------------------------
# 4) KPI
# ---------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("이벤트 수", f"{len(f):,}")
c2.metric("최대 규모", f"{f['magnitude'].max():.1f}" if len(f) else "-")
c3.metric("평균 규모", f"{f['magnitude'].mean():.2f}" if len(f) else "-")
c4.metric("평균 깊이(km)", f"{f['depth'].mean():.1f}" if len(f) else "-")

st.divider()

# ---------------------------
# 5) 탭
# ---------------------------
tab_map, tab_trend, tab_region, tab_data = st.tabs(["🗺️ 지도", "📈 추세", "🌐 지역 집계", "🗃️ 데이터"])

# ===== 지도  =====
with tab_map:
    st.subheader("📍 지진 위치 ")
    if len(f):
        # 뷰포트
        if f["lat"].notna().any() and f["lon"].notna().any():
            lat_center = float(f["lat"].mean())
            lon_center = float(f["lon"].mean())
        else:
            lat_center, lon_center = 0.0, 0.0

        mag = f["magnitude"].fillna(0).clip(lower=0, upper=8)
        size_m = ((mag + 1.0) ** 2) * 6000
        size_m = np.clip(size_m, 3000, 60000)

        color = ((mag / 8) * 255).astype(int)
        plot_df = f.assign(
            color_r=color.clip(80, 255),
            color_g=(120 - (color * 0.4)).clip(0, 120),
            color_b=60,
            size=size_m
        )

        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=plot_df.dropna(subset=["lat","lon"]),
            get_position='[lon, lat]',
            get_radius='size',
            radius_min_pixels=3,
            radius_max_pixels=120,
            get_fill_color='[color_r, color_g, color_b, 210]',
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True
        )

        show_density = st.toggle("밀도(Heatmap) 켜기", value=True, help="겹치는 지역을 색 번짐으로 강조")
        heat = pdk.Layer(
            "HeatmapLayer",
            data=plot_df.dropna(subset=["lat","lon"])[["lon","lat","magnitude"]].rename(columns={"magnitude":"weight"}),
            get_position='[lon, lat]',
            get_weight="weight",
            radius_pixels=40,
            intensity=1.0
        ) if show_density else None

        view_state = pdk.ViewState(latitude=lat_center, longitude=lon_center, zoom=1.6, pitch=0, bearing=0)
        layers = [scatter] if not show_density else [heat, scatter]
        deck = pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            tooltip={"text": "{place}\nM{magnitude} • depth {depth} km"},
            map_provider="carto"  # 토큰 없이 사용
        )
        st.pydeck_chart(deck, use_container_width=True)
        # (지도 렌더링 바로 아래)
st.markdown(
    """
    <div style="margin-top:8px;padding:10px 12px;border:1px solid #eaeaea;border-radius:8px;background:#fafafa">
      <div style="font-weight:600;margin-bottom:6px;">색상 범례 (Magnitude, 지진 규모)</div>
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="width:160px;height:12px;background:linear-gradient(90deg,
            rgb(120,160,80) 0%,
            rgb(200,140,60) 40%,
            rgb(230,90,60) 70%,
            rgb(255,40,60) 100%);
            border:1px solid #ddd;border-radius:4px;"></div>
        <div style="font-size:12px;color:#555;">녹/노랑 → 주황 → 빨강 으로 갈수록 <b>규모가 큼</b></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#777;margin-top:4px;">
        <span>M≈2</span><span>M≈4</span><span>M≈6</span><span>M≈8+</span>
      </div>
      <div style="font-size:12px;color:#666;margin-top:6px;">
        점의 <b>크기</b>도 규모에 비례하여 커집니다. 흰색 테두리는 겹치는 위치를 구분하기 위한 시각적 강조입니다.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

    else:
        st.info("표시할 결과가 없습니다. 필터를 조정해 보세요.")






# ===== 추세 =====
with tab_trend:
    st.subheader("🔢 규모 히스토그램")
    if len(f) and f["magnitude"].notna().any():
        upper = float(max(8.0, f["magnitude"].max()))
        hist = np.histogram(f["magnitude"].dropna(), bins=20, range=(0, upper))
        st.bar_chart(pd.DataFrame({"count": hist[0]}, index=pd.Index(hist[1][:-1], name="mag")), use_container_width=True)

    st.subheader("⏱️ 시간대별 발생 수(3시간 단위)")
    if len(f) and f["time"].notna().any():
        ts = f.set_index("time").resample("3H")["id"].count()
        st.line_chart(ts, use_container_width=True)

# ===== 지역 집계 =====
with tab_region:
    st.subheader("🌐 대륙·국가별 집계")
    if len(f) and f["continent"].notna().any():
        cont_df = (
            f.dropna(subset=["continent"])
             .groupby("continent")
             .agg(events=("id","count"),
                  max_mag=("magnitude","max"),
                  avg_mag=("magnitude","mean"),
                  avg_depth=("depth","mean"))
             .sort_values("events", ascending=False)
             .reset_index()
        )
        st.markdown("**대륙별 요약**")
        st.dataframe(cont_df, use_container_width=True)
        st.bar_chart(cont_df.set_index("continent")["events"], use_container_width=True)

        country_df = (
            f.dropna(subset=["country"])
             .groupby("country")
             .agg(events=("id","count"),
                  max_mag=("magnitude","max"),
                  avg_mag=("magnitude","mean"),
                  avg_depth=("depth","mean"))
             .sort_values("events", ascending=False)
             .head(20)
             .reset_index()
        )
        st.markdown("**국가별 요약 (Top 20)**")
        st.dataframe(country_df, use_container_width=True)
    else:
        st.info("대륙/국가 매핑 결과가 없거나 라이브러리가 없습니다. (앱은 계속 사용 가능합니다)")

# ===== 데이터 원본 =====
with tab_data:
    with st.expander("원본 데이터 보기 / 다운로드"):
        base_cols = ["time","magnitude","depth","place","lat","lon","type","status","id"]
        extra = [c for c in ["country","continent","country_code"] if c in f.columns]
        show_cols = [c for c in base_cols + extra if c in f.columns]
        st.dataframe(f[show_cols], use_container_width=True)
        st.download_button("CSV 다운로드", f[show_cols].to_csv(index=False).encode("utf-8"),
                           "earthquakes_filtered.csv", "text/csv")

st.caption("데이터 출처: USGS Earthquake Hazards Program. (대륙/국가 매핑은 선택적이며 라이브러리 없으면 생략)")
