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

# --- 2. 数据加载 (自带图片过滤功能) ---
@st.cache_data(ttl=600) # 缓存10分钟，提升页面加载速度
def load_valid_data(_client):
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = _client.table("contest_artworks").select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
            
        for item in response.data:
            assets = item.get("assets_data")
            r2_key = None
            
            # 安全提取 r2_raw_key
            if isinstance(assets, dict):
                r2_key = assets.get("r2_raw_key")
            elif isinstance(assets, list) and len(assets) > 0:
                if isinstance(assets[0], dict):
                    r2_key = assets[0].get("r2_raw_key")
            
            # 仅保留有图片链接的数据
            if r2_key:
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
    
    # 密码校验系统
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    
    if not st.session_state["password_correct"]:
        pwd = st.text_input("请输入评审密码", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            st.rerun()
        st.stop()

    # 初始化连接并获取有效数据
    _, supabase = init_connections()
    data = load_valid_data(supabase)
    
    if not data:
        st.warning("暂无包含图片的作品数据，请检查 R2 存储或数据库更新。")
        st.stop()
    
    # --- 级联选择 UI ---
    st.markdown("### 🔍 参赛作品选择")
    
    # 1. 提取所有可用的分类 (例如: 绘本奖, 插画奖)
    available_categories = list(set([item.get('category', '未分类') for item in data]))
    available_categories.sort() # 排序，让显示更整洁
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_category = st.selectbox("1. 选择赛道分类", options=available_categories)
        
    # 2. 根据选中的分类，过滤出对应的作品列表
    filtered_data = [item for item in data if item.get('category', '未分类') == selected_category]
    
    # 3. 构造该分类下的作品字典，显示格式为：作品名 [盲审编号]
    options = {}
    for item in filtered_data:
        title = item.get('title')
        # 如果 title 为空或不存在，给一个友好的默认值
        title_display = title if title else "无标题"
        code = item.get('blind_review_code', '未知编号')
        
        # 组装展示标签：作品名称在前，编号在后作为辅助标识
        label = f"{title_display} [{code}]"
        options[label] = item
        
    with col2:
        selected_label = st.selectbox(f"2. 选择【{selected_category}】下的作品", options=list(options.keys()))
    
    st.divider() # 分割线
    
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
            # 采用最新的 width=None 写法，自适应宽度铺满列
            st.image(secure_url, caption=f"原稿加载完毕: {asset.get('blind_review_code')}", width="stretch")
        except Exception as e:
            st.error(f"无法生成加密预览链接，请联系系统管理员。错误详情: {e}")

if __name__ == "__main__":
    main()
