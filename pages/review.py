import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

# --- 1. 生产级初始化 ---
@st.cache_resource
def init_connections():
    # R2 连接
    r2 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version="s3v4")
    )
    # Supabase 连接
    supabase = create_client(
        os.getenv('NEW_SUPABASE_URL'), 
        os.getenv('NEW_SUPABASE_KEY')
    )
    return r2, supabase

# --- 2. 密码校验 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        def password_entered():
            if st.session_state["password"] == os.getenv("REVIEWER_PASSWORD"):
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else:
                st.session_state["password_correct"] = False
        
        st.text_input("请输入评审密码", type="password", on_change=password_entered, key="password")
        return False
    return True

# --- 3. 分页加载全量数据 ---
def load_all_data(client):
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = client.table("contest_artworks").select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
        all_data.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return all_data

# --- 4. 获取 R2 安全 URL ---
def get_secure_url(r2_key):
    r2, _ = init_connections()
    return r2.generate_presigned_url(
        'get_object',
        Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': r2_key},
        ExpiresIn=900
    )

# --- 5. 主页面逻辑 ---
def main():
    st.set_page_config(page_title="NAL 评审工作台", layout="wide")
    st.title("新艺文社数字化文学平台 - 第二届盲审工作台")
    
    if not check_password():
        st.stop()

    _, supabase = init_connections()
    data = load_all_data(supabase)
    
    # 构造选项：仅当字段存在时展示
    options = {}
    for item in data:
        code = item.get("blind_review_code", "未知编号")
        cat = item.get("category", "无分类")
        options[f"{code} ({cat})"] = item
    
    selected_label = st.selectbox("选择参赛作品", options=list(options.keys()))
    asset = options[selected_label]
    
    st.subheader(f"视觉原稿区 [{selected_label}]")
    st.info("以下图片采用端到端加密链接，15分钟后自动失效。")
    
    # 展示图片 (假设 assets_data 存储了 key)
    assets = asset.get("assets_data", {})
    r2_key = assets.get("r2_raw_key")
    
    if r2_key:
        secure_url = get_secure_url(r2_key)
        st.image(secure_url, use_column_width=True)
    else:
        st.warning("该作品暂无原稿资源。")

if __name__ == "__main__":
    main()
