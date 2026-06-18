import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

# --- 1. 生产级初始化连接 ---
@st.cache_resource
def init_connections():
    r2 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version="s3v4")
    )
    supabase = create_client(
        os.getenv('NEW_SUPABASE_URL'), 
        os.getenv('NEW_SUPABASE_KEY')
    )
    return r2, supabase

# --- 2. 预签名链接生成器 ---
def get_secure_url(r2_key, r2_client):
    try:
        return r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': r2_key},
            ExpiresIn=900 # 15分钟有效
        )
    except Exception as e:
        st.error(f"链接生成失败: {e}")
        return None

# --- 3. 高效数据加载与多图清洗 ---
# 缩短了缓存时间，防止你刚传完图但页面依然显示旧的无图列表
@st.cache_data(ttl=60) 
def load_valid_data(_client):
    valid_data = []
    total_fetched = 0
    page_size = 1000
    start = 0
    
    while True:
        response = _client.table("contest_artworks").select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
            
        total_fetched += len(response.data)
        
        for item in response.data:
            assets = item.get("assets_data")
            valid_image_keys = []
            
            # 解析最新的数据结构 (无论是单字典，还是多页的列表)
            if isinstance(assets, list):
                for page in assets:
                    if isinstance(page, dict) and page.get("r2_raw_key"):
                        key = str(page.get("r2_raw_key")).strip()
                        if key:  # 确保不为空
                            valid_image_keys.append(key)
            elif isinstance(assets, dict):
                r2_key = assets.get("r2_raw_key")
                if r2_key and str(r2_key).strip():
                    valid_image_keys.append(str(r2_key).strip())
            
            # 绝对过滤：只有包含至少一张有效图片路径的作品，才会被加入最终显示列表
            if valid_image_keys:
                item['parsed_r2_keys'] = valid_image_keys  
                valid_data.append(item)
        
        if len(response.data) < page_size:
            break
        start += page_size
        
    return valid_data, total_fetched

# --- 4. 页面主逻辑 ---
def main():
    st.set_page_config(page_title="NAL 评审工作台", layout="wide")
    
    # --- 密码校验 ---
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if not st.session_state["password_correct"]:
        pwd = st.text_input("请输入评审密码", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            st.rerun()
        st.stop()

    st.title("新艺文社数字化文学平台 - 第二届盲审工作台")

    # --- 获取数据 ---
    r2_client, supabase_client = init_connections()
    valid_data, total_fetched = load_valid_data(supabase_client)
    
    # 手动刷新缓存的按钮（如果看到没有图片的作品，可点此强制同步）
    with st.sidebar:
        st.success(f"系统共检索: **{total_fetched}** 条记录")
        st.info(f"含图片可阅览: **{len(valid_data)}** 部作品")
        if st.button("🔄 强制刷新最新数据"):
            load_valid_data.clear()
            st.rerun()
    
    if not valid_data:
        st.warning("当前数据库中暂无包含图片的作品。")
        st.stop()
    
    # --- UI 交互：级联选择 ---
    st.markdown("### 🔍 参赛作品选择")
    
    available_categories = list(set([item.get('category', '未分类') for item in valid_data]))
    available_categories.sort()
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_category = st.selectbox("1. 选择赛道分类", options=available_categories)
        
    filtered_data = [item for item in valid_data if item.get('category', '未分类') == selected_category]
    
    options = {}
    for item in filtered_data:
        title = item.get('title')
        title_display = title if (title and str(title).strip()) else "无标题"
        code = item.get('blind_review_code', '未知编号')
        
        label = f"{title_display} [{code}]"
        options[label] = item
        
    with col2:
        selected_label = st.selectbox(f"2. 选择【{selected_category}】下的作品", options=list(options.keys()))
    
    st.divider()
    
    # --- 多图流式渲染与缩放控制区 ---
    if selected_label:
        asset = options[selected_label]
        image_keys = asset.get("parsed_r2_keys", [])
        
        st.subheader(f"🎨 视觉原稿区: {selected_label}")
        
        # 增加动态缩放滑块，默认宽度 700px 适合大部分竖排绘本
        img_width = st.slider("🔍 调整图片显示比例 (拖动缩放)", min_value=300, max_value=2000, value=700, step=50)
        
        st.info(f"💡 提示：该作品共包含 {len(image_keys)} 页视觉稿。图片采用端到端加密链接，15分钟后自动失效。")
        
        # 居中显示图片的 CSS 技巧
        col_img1, col_img2, col_img3 = st.columns([1, 6, 1])
        
        with col_img2:
            # 遍历该作品的所有页面并依次渲染
            for idx, key in enumerate(image_keys):
                secure_url = get_secure_url(key, r2_client)
                if secure_url:
                    # 弃用 stretch，改用滑块驱动的动态 width
                    st.image(secure_url, caption=f"第 {idx + 1} 页", width=img_width)
                    st.markdown("<br>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
