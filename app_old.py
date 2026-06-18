import streamlit as st
import requests
import time
import os
from supabase import create_client, Client

# --- 1. 配置与环境初始化 ---
st.set_page_config(page_title="NAL | 视觉叙事深度评审引擎", page_icon="🏛️", layout="wide")

# 注入 CSS 以确保风格与 nal-ai.org 高度统一
st.markdown("""
    <style>
    /* 隐藏 Streamlit 默认页眉页脚，提升专业感 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 统一背景色 */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* 精准覆盖文字字体，放过底层框架的 div 和 span */
    .stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label, .stMarkdownContainer {
        font-family: 'Georgia', 'Times New Roman', serif !important;
    }
    </style>
""", unsafe_allow_html=True)

# 兼容 Render 与 Streamlit 环境的多重保险读取
def get_config(key, default=""):
    val = os.environ.get(key)
    if val: return val
    try: return st.secrets.get(key, default)
    except: return default

# 🚨 安全警报：已去除代码中硬编码的真实 JWT 密钥，改用安全读取
SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_KEY = get_config("SUPABASE_KEY")
API_BASE_URL = get_config("API_BASE_URL", "https://pb-api.nal-ai.org")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ 系统环境未就绪：缺少数据库连接凭证。请确认 Secrets 或环境变量配置正确。")
    st.stop()

# 初始化 Supabase 客户端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. 核心函数：上传素材至存储桶 ---
def upload_images_to_nal_storage(files):
    """
    将上传的文件推送到 Supabase 'nal_images' 存储桶并返回公开 URL
    """
    public_urls = []
    for file in files:
        try:
            file_path = f"review_images/{int(time.time())}_{file.name}"
            file_content = file.getvalue()
            
            # 上传到公共存储桶
            supabase.storage.from_("nal_images").upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": file.type}
            )
            
            # 获取允许外部访问的公网链接
            url_res = supabase.storage.from_("nal_images").get_public_url(file_path)
            public_urls.append(url_res)
        except Exception as e:
            st.error(f"⚠️ 文件 {file.name} 上传失败: {e}")
    return public_urls

# --- 3. 侧边栏：学术参数配置 ---
st.title("🏛️ NewArtLiterature Collective")
st.subheader("绘本与插画视觉叙事协同评审")

with st.sidebar:
    st.header("评审参数配置")
    work_type = st.selectbox("作品形态", ["绘本 (Picture Book)", "插画 (Illustration)"])
    st.divider()
    
    st.markdown("**NAL 评估模型 (基于创作意图)：**")
    if "绘本" in work_type:
        st.caption("🔍 **焦点：** 跨页节奏、图文协同度、文字留白处的视觉补偿。")
    else:
        st.caption("🔍 **焦点：** 单幅画面对创作意图的精准传达、构图隐喻、避免无意义的视觉炫技。")
        
    st.divider()
    st.markdown("""
    **4:3:3 权重分布：**
    - 视觉对撞 (40%)
    - 创意维度 (30%)
    - 叙事平衡/单幅张力 (30%)
    """)
    st.caption("当前引擎: v2.1.0-NAL-Synergy")
    st.info("💡 建议：上传素材前请确保已完成‘创作意图’的文本沉淀。")

# --- 4. 主界面：动态输入区 ---
st.write(f"### 📝 第一步：确立叙事内核与意图")

script_placeholder = "请输入完整的绘本文字脚本，以便分析图文节奏..." if "绘本" in work_type else "请输入这幅插画的创作意图、配文或背景设定，以便分析图像表达是否精准..."
script_text = st.text_area(
    "文本脚本 / 创作意图 (v5 分析锚点)", 
    height=150, 
    placeholder=script_placeholder
)

st.write(f"### 🖼️ 第二步：上传 {work_type} 视觉素材")
# 更新了提示文案，并增加了 type 限制以防上传不支持的文件
uploaded_files = st.file_uploader(
    "支持上传 JPG, PNG 格式 (⚠️ 最多上传 5 张，单张大小不超过 1MB)", 
    accept_multiple_files=True,
    type=['jpg', 'jpeg', 'png']
)

if uploaded_files:
    # 🚨 校验 1：限制最大数量为 5 张
    if len(uploaded_files) > 5:
        st.error(f"⚠️ 上传数量超限：您当前上传了 {len(uploaded_files)} 张图片，系统最多允许评审 5 张核心画面。请在上方点击 'X' 删减图片。")
        st.stop() # 强制停止后续代码运行，不让用户看到提交按钮

    # 🚨 校验 2：限制单张文件最大为 1MB (1MB = 1 * 1024 * 1024 Bytes)
    MAX_SIZE_BYTES = 1 * 1024 * 1024
    oversized_files = [file.name for file in uploaded_files if file.size > MAX_SIZE_BYTES]
    
    if oversized_files:
        st.error("⚠️ 文件体积超限：系统限制单张图片最大为 1MB。以下图片过大：")
        for name in oversized_files:
            st.write(f"- {name}")
        st.info("💡 架构师建议：对于 AI 视觉模型而言，适当压缩后的图片（如 800px 宽度）完全不影响叙事节奏和图文协同的分析。建议使用画图工具或在线压缩后重试。")
        st.stop() # 强制拦截

    # 如果通过了以上所有安全校验，再展示预览区
    with st.expander("👀 待评审素材预览", expanded=False):
        # 优化了列的分配，如果少于 4 张图就不会出现空白列
        num_cols = min(len(uploaded_files), 4) 
        cols = st.columns(num_cols)
        for idx, file in enumerate(uploaded_files):
            cols[idx % num_cols].image(file, use_container_width=True)

# --- 5. 提交与轮询逻辑 ---
if st.button("🚀 提交 NAL 学术评审", type="primary"):
    
    if not script_text.strip():
        st.warning("⚠️ 请输入文本脚本或创作意图。在 NAL 评估体系中，理解作者意图是评判视觉表现力的前提。")
        st.stop()
        
    if not uploaded_files:
        st.warning("⚠️ 请至少上传一张视觉素材以供分析。")
        st.stop()
        
    # 执行上传
    with st.spinner("📦 正在建立视觉素材与叙事文本的云端映射..."):
        image_urls = upload_images_to_nal_storage(uploaded_files)
    
    if not image_urls:
        st.error("素材同步失败，请检查 Supabase 存储桶配置。")
    else:
        try:
            with st.spinner("📡 正在唤醒后台 v65 视觉协同引擎..."):
                payload = {
                    "work_type": "picture_book" if "绘本" in work_type else "illustration",
                    "script_text": script_text,
                    "image_urls": image_urls
                }
                resp = requests.post(f"{API_BASE_URL}/PB/api/evaluate", json=payload, timeout=20)
            
            if resp.status_code == 200:
                row_id = resp.json().get("row_id")
                st.toast(f"✅ NAL 评审立项成功！档案 ID: {row_id}", icon="🤖")
                
                status_area = st.empty()
                progress_bar = st.progress(0)
                start_time = time.time()
                
                quotes = [
                    "正在锚定文本意图与视觉表现的基准线...",
                    "正在解析色彩张力与构图的叙事性...",
                    "正在评估图像是否陷入‘无意义的炫技’...",
                    "正在计算 NAL 核心指标：图文/意图协同度...",
                    "学术评审报告深度撰写中..."
                ]
                
                while True:
                    status_resp = requests.get(f"{API_BASE_URL}/PB/api/status/{row_id}", timeout=10)
                    if status_resp.status_code == 200:
                        # 增加一层容错，防止网关返回 HTML 错误导致 json() 崩溃
                        try:
                            data = status_resp.json()
                        except ValueError:
                            st.error("❌ 后端返回了异常格式数据，通信中断。")
                            break
                            
                        status = data.get("status")
                        
                        if status == "completed":
                            progress_bar.progress(100)
                            status_area.success("🎯 深度评审已完成！")
                            
                            # --- 6. 学术报告展示区 ---
                            st.divider()
                            col_score, col_report = st.columns([1, 2.5])
                            
                            with col_score:
                                score = data.get("v65_visual_score", 0)
                                st.metric("NAL 综合协同得分", f"{score} / 10")
                                st.write("**4:3:3 评测维度表：**")
                                st.caption("☑️ 视觉对撞表现")
                                st.caption("☑️ 创意/原创维度")
                                st.caption("☑️ 叙事平衡与意图契合")
                                
                            with col_report:
                                st.markdown("### 🏛️ 学术评审报告 (Synergy Report)")
                                st.info(data.get("v65_synergy_report", "报告提取失败。"))
                                
                                report_text = data.get("v65_synergy_report", "")
                                if report_text:
                                    st.download_button(
                                        label="📥 下载学术评审报告",
                                        data=f"NAL 评审报告 (ID: {row_id})\n综合得分: {score}\n\n{report_text}",
                                        file_name=f"NAL_Report_{row_id}.txt",
                                        mime="text/plain"
                                    )
                            break
                            
                        elif status == "failed":
                            st.error("❌ 模型分析崩溃，请检查素材是否触碰安全限制或后端日志报错。")
                            break
                        else:
                            elapsed = int(time.time() - start_time)
                            q_idx = (elapsed // 8) % len(quotes)
                            status_area.info(f"⏳ {quotes[q_idx]} (已耗时 {elapsed}s)")
                            progress_bar.progress(min(elapsed * 2, 95)) 
                            
                    time.sleep(5)
            else:
                st.error(f"后端 API 拒绝服务 (HTTP {resp.status_code})")
                st.write("请确认 Render 后端 pb-api.nal-ai.org 已正常运行。")
        except Exception as e:
            st.error(f"网络阻断，无法连接到 NAL 评审中枢: {e}")

# --- 7. 页脚版权声明 ---
st.divider()
st.markdown(
    "<div style='text-align: center; color: gray; font-size: 0.8em;'>"
    "© 2026 NewArtLiterature Collective | 倡导有灵魂的视觉叙事与数字化学术分析<br>"
    "新艺文社数字化平台 · 非营利性学术机构"
    "</div>", 
    unsafe_allow_html=True
)
