import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

# --- 1. 初始化 ---
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

# --- 2. 数据加载 (分页 + 过滤) ---
def load_valid_data(client):
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = client.table("contest_artworks").select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
            
        # --- 核心过滤逻辑：只保留有 R2 图片资源的数据 ---
        for item in response.data:
            assets = item.get("assets_data")
            # 提取 r2_key 的逻辑，适配 dict 或 list 结构
            r2_key = None
            if isinstance(assets, dict):
                r2_key = assets.get("r2_raw_key")
            elif isinstance(assets, list) and len(assets) > 0:
                if isinstance(assets[0], dict):
                    r2_key = assets[0].get("r2_raw_key")
            
            if r2_key:
                # 给 item 增加一个解析好的字段，方便后面直接用
                item['parsed_r2_key'] = r2_key
                all_data.append(item)
        
        if len(response.data) < page_size:
            break
        start += page_size
    return all_data

# --- 3. 页面主逻辑 ---
def main():
    st.set_page_config(page_title="NAL 评审工作台", layout="wide")
    st.title("新艺文社数字化文学平台 - 第二届盲审工作台")
    
    # 密码校验
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if not st.session_state["password_correct"]:
        pwd = st.text_input("请输入评审密码", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            st.rerun()
        st.stop()

    _, supabase = init_connections()
    
    # 加载已过滤的数据
    data = load_valid_data(supabase)
    
    if not data:
        st.warning("暂无包含图片的作品数据。")
        st.stop()
    
    # 构造选项
    options = {f"{item.get('blind_review_code', '未知')} ({item.get('category', '无分类')})": item for item in data}
    
    selected_label = st.selectbox("选择参赛作品", options=list(options.keys()))
    asset = options[selected_label]
    
    st.subheader(f"视觉原稿区 [{selected_label}]")
    st.info("以下图片采用端到端加密链接，15分钟后自动失效。")
    
    # 直接使用预处理好的 key
    r2_key = asset.get("parsed_r2_key")
    
    # 获取 R2 链接
    r2, _ = init_connections()
    secure_url = r2.generate_presigned_url(
        'get_object',
        Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': r2_key},
        ExpiresIn=900
    )
    st.image(secure_url, use_column_width=True)

if __name__ == "__main__":
    main()
