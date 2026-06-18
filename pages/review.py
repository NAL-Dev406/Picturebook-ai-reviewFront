import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

# --- 1. 初始化连接 ---
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

# --- 2. 极其严苛的数据过滤加载 ---
@st.cache_data(ttl=600)
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
            r2_key = None
            
            # 安全提取逻辑
            if isinstance(assets, dict):
                r2_key = assets.get("r2_raw_key")
            elif isinstance(assets, list) and len(assets) > 0:
                if isinstance(assets[0], dict):
                    r2_key = assets[0].get("r2_raw_key")
            
            # --- 核心：极度严苛的有效性检查 ---
            # 必须是字符串，且去掉两边空格后长度大于0，才算是真有图片
            if isinstance(r2_key, str) and r2_key.strip() != "":
                item['parsed_r2_key'] = r2_key.strip()
                valid_data.append(item)
        
        if len(response.data) < page_size:
            break
        start += page_size
        
    return valid_data, total_fetched

# --- 3. 页面主逻辑 ---
def main():
    st.set_page_config(page_title="NAL 评审工作台", layout="wide")
    
    # 密码校验
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if not st.session_state["password_correct"]:
        pwd = st.text_input("请输入评审密码", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            st.rerun()
        st.stop()

    st.title("新艺文社数字化文学平台 - 第二届盲审工作台")

    # 初始化连接并获取有效数据
    _, supabase = init_connections()
    valid_data, total_fetched = load_valid_data(supabase)
    
    # 在侧边栏显示调试/统计信息，让你心里有数
    with st.sidebar:
        st.success(f"数据库总记录: **{total_fetched}** 条")
        st.info(f"含图片有效记录: **{len(valid_data)}** 条")
        st.warning(f"已自动过滤拦截: **{total_fetched - len(valid_data)}** 条无图记录")
    
    if not valid_data:
        st.warning("当前数据库中没有找到任何包含有效图片链接的作品，请检查上传脚本是否成功。")
        st.stop()
    
    # --- 级联选择 UI ---
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
    
    # --- 渲染选中的作品图片 ---
    if selected_label:
        asset = options[selected_label]
        r2_key = asset.get("parsed_r2_key")
        
        st.subheader(f"🎨 视觉原稿区: {selected_label}")
        st.info("💡 提示：以下图片采用端到端加密链接，15分钟后自动失效，请勿外传。")
        
        r2, _ = init_connections()
        try:
            secure_url = r2.generate_presigned_url(
                'get_object',
                Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': r2_key},
                ExpiresIn=900
            )
            # 使用 width="stretch" 适配新版 Streamlit
            st.image(secure_url, caption=f"原稿加载完毕: {asset.get('blind_review_code')}", width="stretch")
        except Exception as e:
            st.error(f"无法生成加密预览链接，请联系系统管理员。错误详情: {e}")

if __name__ == "__main__":
    main()
