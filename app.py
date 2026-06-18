import streamlit as st

def main():
    # 配置页面基本信息
    st.set_page_config(
        page_title="新艺文社数字化文学平台",
        page_icon="📚",
        layout="centered" # 门户页居中显示更美观
    )

    st.title("📚 新艺文社数字化文学平台")
    st.subheader("第二届儿童文学与图画书盲审系统")
    
    st.divider()

    # 引导说明
    st.info("👈 请通过左侧边栏导航，或点击下方按钮进入专属工作台。")
    
    st.markdown("<br>", unsafe_allow_html=True)

    # 居中放置一个跳转按钮
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # 使用 Streamlit 原生的页面跳转功能 (需 Streamlit 1.31.0+)
        if st.button("🚀 进入盲审工作台", type="primary", use_container_width=True):
            try:
                st.switch_page("pages/review.py")
            except Exception as e:
                st.error("无法自动跳转，请手动点击左侧边栏的 review 页面。")

if __name__ == "__main__":
    main()
