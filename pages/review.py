import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

# --- 1. 生产级初始化：全面移除 st.secrets，采用 os.getenv ---
@st.cache_resource
def init_connections():
    # R2 存储连接
    r2 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version="s3v4")
    )
    
    # Supabase 数据库连接
    supabase = create_client(
        os.getenv('NEW_SUPABASE_URL'), 
        os.getenv('NEW_SUPABASE_KEY')
    )
    return r2, supabase

# --- 2. 密码校验：直接对比系统环境变量 ---
def check_password():
    def password_entered():
        if st.session_state["password"] == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
            
    if "password_correct" not in st.session_state:
        st.text_input("请输入评审密码", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

# --- 3. 页面主逻辑 ---
def main():
    st.set_page_config(page_title="NAL 评审工作台", layout="wide")
    
    if not check_password():
        st.stop()

    r2, supabase = init_connections()
    
    # 防弹级数据读取
    try:
        response = supabase.table("contest_artworks").select("*").execute()
        data = response.data
    except Exception as e:
        st.error(f"连接数据库失败: {e}")
        st.stop()

    # 下拉菜单：使用防御性字典生成
    options = {}
    for item in data:
        code = item.get("blind_review_code", "未知编号")
        cat = item.get("category", "无分类")
        uid = item.get("id")
        if uid:
            options[f"{code} ({cat})"] = uid

    # 选择作品
    selected_label = st.selectbox("选择参赛作品", options=list(options.keys()))
    selected_id = options[selected_label]
    
    # 展示图片逻辑
    st.write(f"正在展示作品 ID: {selected_id}")
    # 这里接入你之前获取 R2 图片并展示的代码...

if __name__ == "__main__":
    main()
