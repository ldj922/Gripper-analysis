import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# --- 1. 설정 및 경로 정의 ---
st.set_page_config(layout="wide", page_title="그리퍼 분석 시스템")
STORAGE_PATH = "data_storage"

# [cite: 137, 138] 저장용 폴더 자동 생성 (폴더가 없으면 에러 방지를 위해 생성)
if not os.path.exists(STORAGE_PATH):
    os.makedirs(STORAGE_PATH)

st.title("🔄 그리퍼 데이터 분석")

# --- 가로 스크롤 활성화 CSS ---
st.markdown(
    """<style>.stPlotlyChart { overflow-x: auto !important; }</style>""",
    unsafe_allow_html=True
)

# --- 2. [함수] 데이터 스캔 및 사이클 번호 부여 ---
@st.cache_data(show_spinner="사이클 데이터를 처리 중입니다...")
def load_cycle_data(root_path):
    all_data = []
    # [cite: 377, 379] os.walk를 통해 모든 하위 폴더 탐색 (날짜/테스트별 폴더 포함)
    for root, dirs, files in os.walk(root_path):
        for file in files:
            if file.endswith(".csv") and "6축 센서" not in file:
                try:
                    file_path = os.path.join(root, file)
                    test_name = os.path.basename(root) # 폴더명을 테스트 명으로 인식
                    
                    df = pd.read_csv(file_path, encoding='cp949')
                    df.columns = df.columns.str.strip()
                    
                    # --- [핵심] 사이클 및 인덱스 생성 로직 [cite: 595, 596] ---
                    # 1. 파일 내 절대 순번 부여 (X축 대용으로 시계열 공백 제거)
                    df['Index'] = range(len(df)) 
                    # 2. 5행마다 1사이클 번호 부여 (1, 2, 3...) [cite: 588, 596]
                    df['Cycle'] = (df['Index'] // 5) + 1 
                    # 3. 사이클 내 세부 순번 (1-1, 1-2... 1-5) 표시용 [cite: 590, 602]
                    df['Sub_Index'] = (df['Index'] % 5) + 1
                    df['Cycle_Label'] = df['Cycle'].astype(str) + "-" + df['Sub_Index'].astype(str)

                    # [cite: 107, 115] 파일 이름 기반 데이터 종류 자동 분류
                    if "전류" in file: d_type = "전류"
                    elif "온도" in file: d_type = "온도"
                    elif "각도" in file: d_type = "각도"
                    elif "속도" in file: d_type = "속도"
                    else: d_type = "기타"

                    target_cols = [c for c in df.columns if '모터' in c or c in ['최대', '최소', '평균']]
                    
                    # Index와 Cycle 정보를 유지하며 데이터 재구조화(Melt)
                    melted = df.melt(id_vars=['Index', 'Cycle', 'Cycle_Label'], 
                                     value_vars=target_cols, var_name='항목', value_name='값')
                    melted['종류'] = d_type
                    melted['테스트명'] = test_name
                    all_data.append(melted)
                except Exception as e:
                    st.error(f"파일 로드 에러 ({file}): {e}")
                    
    return pd.concat(all_data).reset_index(drop=True) if all_data else None

# --- 3. 데이터 로드 및 UI 표시 ---
full_df = load_cycle_data(STORAGE_PATH)

if full_df is None:
    st.info(f"'{STORAGE_PATH}' 폴더 내에 데이터 폴더를 넣어주세요.")
else:
    # --- 사이드바 설정 ---
    st.sidebar.header("⚙️ 분석 및 비교 설정")
    
    # [cite: 365, 534] 저장된 모든 하위 폴더 리스트에서 비교 테스트 다중 선택
    all_tests = sorted(full_df['테스트명'].unique())
    selected_tests = st.sidebar.multiselect("비교할 테스트 선택", options=all_tests, default=all_tests[:1])
    
    filtered_df = full_df[full_df['테스트명'].isin(selected_tests)]
    
    if not filtered_df.empty:
        # 특정 구간의 동작만 확인하기 위한 사이클 범위 필터
        max_cycle = int(filtered_df['Cycle'].max())
        st.sidebar.subheader("🔄 사이클 범위 설정")
        cycle_range = st.sidebar.slider("분석할 사이클(Cycle) 범위", 1, max_cycle, (1, min(100, max_cycle)))

        # [cite: 111, 112] 데이터 종류 및 Y축 축 배치 선택
        st.sidebar.markdown("---")
        available_types = sorted(filtered_df['종류'].unique())
        selected_types = st.sidebar.multiselect("데이터 종류", options=available_types, default=["전류"])
        
        y2_types = st.sidebar.multiselect("오른쪽 축(Y2) 배치", options=selected_types, 
                                        default=[t for t in selected_types if t in ["온도", "각도", "속도"]])
        
        available_items = sorted(filtered_df['항목'].unique())
        selected_items = st.multiselect("분석할 모터/통계 선택", options=available_items, default=["모터3"])

        # 선택된 사이클 범위에 따라 데이터 필터링
        final_df = filtered_df[filtered_df['Cycle'].between(cycle_range[0], cycle_range[1])]

        # --- 4. 그래프 시각화 ---
        if selected_items and selected_types:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            for test in selected_tests:
                for item in selected_items:
                    for t in selected_types:
                        plot_data = final_df[(final_df['테스트명'] == test) & 
                                             (final_df['항목'] == item) & 
                                             (final_df['종류'] == t)]
                        
                        if not plot_data.empty:
                            use_y2 = t in y2_types
                            line_style = dict(width=2, dash='dash') if item in ['최대', '최소', '평균'] else dict(width=1.5)
                            
                            # [cite: 597] 시각적 공백을 없애기 위해 X축에 데이터 순번(Index) 사용
                            fig.add_trace(
                                go.Scatter(
                                    x=plot_data['Index'], 
                                    y=plot_data['값'], 
                                    name=f"[{test}] {item} {t}", 
                                    line=line_style,
                                    hovertext=plot_data['Cycle_Label'], # 마우스 오버 시 사이클(예: 1-1) 표시 [cite: 603]
                                    mode='lines+markers' if (cycle_range[1] - cycle_range[0]) < 20 else 'lines'
                                ),
                                secondary_y=use_y2
                            )

            # [cite: 116] 데이터 양에 따른 가로 너비 동적 계산
            data_points = len(final_df['Index'].unique())
            dynamic_width = max(1000, data_points * 12) 

            # [cite: 117, 118] 그래프 레이아웃 및 제목 설정
            y1_title = " / ".join([t for t in selected_types if t not in y2_types])
            y2_title = " / ".join(y2_types)

            fig.update_layout(
                width=dynamic_width, height=750, hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                title=f"그리퍼 사이클 기반 통합 분석 (X축: 데이터 순번)"
            )
            
            fig.update_xaxes(title_text="<b>데이터 포인트 (5포인트 = 1사이클)</b>") # [cite: 593]
            fig.update_yaxes(title_text=f"<b>왼쪽: {y1_title}</b>", secondary_y=False)
            fig.update_yaxes(title_text=f"<b>오른쪽: {y2_title}</b>", secondary_y=True)
            
            # [cite: 432] Streamlit 최신 버전 규격 대응 (width='content')
            st.plotly_chart(fig, width='content')
        else:
            st.info("사이드바에서 데이터 종류와 분석 항목을 선택해 주세요.")