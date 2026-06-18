import streamlit as st
import boto3
import os
from botocore.config import Config
from supabase import create_client

st.set_page_config(page_title="NAL盲审工作台", layout="wide")

# ================= 安全验证拦截 =================
def check_password():
    def password_entered():
        if st.session_state["password"] == os.getenv("REVIEWER_PASSWORD"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 评审通道受限制，请输入专家授权码", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 评审通道受限制，请输入专家授权码", type="password", on_change=password_entered, key="password")
        st.error("授权码无效，请联系新艺文社组委会。")
        return False
    return True

if not check_password():
    st.stop()

# ================= 初始化云端连接 (pages/review.py) =================
@st.cache_resource
def init_connections():
    # 使用 os.getenv 直接读取 Render 环境变量，彻底绕过 st.secrets
    r2 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version="s3v4")
    )
    
    # 同样使用 os.getenv 读取数据库配置
    supabase = create_client(
        os.getenv('NEW_SUPABASE_URL'), 
        os.getenv('NEW_SUPABASE_KEY')
    )
    return r2, supabase

r2_client, supabase_client = init_connections()

def get_secure_url(r2_key):
    """请求 R2 生成 15 分钟临时安全链接"""
    if not r2_key: return None
    return r2_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': st.secrets['R2_BUCKET_NAME'], 'Key': r2_key},
        ExpiresIn=900
    )

# ================= UI 渲染逻辑 =================
st.title("新艺文社数字化文学平台 - 第二届盲审工作台")

# 1. 拉取所有稿件 (真实生产环境可以加上 .eq("review_status", "pending"))
response = supabase_client.table("contest_artworks").select("*").execute()

# --- 诊断日志 ---
st.write(f"DEBUG: 数据库连接 URL: {os.getenv('NEW_SUPABASE_URL')}")
st.write(f"DEBUG: 获取到的数据行数: {len(response.data) if response.data else 0}")
if response.data:
    st.write("DEBUG: 数据样例:", response.data[0])
else:
    st.warning("DEBUG: 数据库返回为空，请检查表名 'contest_artworks' 或数据是否存入了该库。")
# --------------

if not response.data:
    st.info("当前无稿件数据。")
    st.stop()

# 2. 侧边栏/顶部 选择稿件
options = {f"{item['blind_review_code']} ({item['category']})": item['id'] for item in response.data}
selected_label = st.selectbox("请选择待评阅稿件：", list(options.keys()))
current_id = options[selected_label]

# 3. 获取选中稿件的完整详情
artwork = supabase_client.table("contest_artworks").select("*").eq("id", current_id).single().execute().data

st.divider()

# 4. 双轨分屏展示
col_left, col_right = st.columns([1.5, 1])

with col_left:
    st.subheader(f"🖼️ 视觉原稿区 [{artwork['blind_review_code']}]")
    st.caption("以下图片采用端到端加密链接，15分钟后自动失效。")
    
    # 遍历 assets_data，按顺序渲染所有页面
    assets = artwork.get("assets_data", [])
    if not assets:
        st.warning("该稿件暂未挂载图像资产。")
    else:
        for asset in assets:
            with st.spinner(f"正在安全解密页面 {asset.get('sort')}..."):
                secure_url = get_secure_url(asset.get("r2_raw_key"))
                if secure_url:
                    st.image(secure_url, caption=f"页面序号: {asset.get('sort')}", use_container_width=True)

with col_right:
    st.subheader("📝 文本与评审区")
    
    # 展示创作声明/大纲
    st.info(f"**【创作大纲/声明】**\n\n{artwork.get('synopsis_or_statement', '暂无文字说明')}")
    
    # 评分表单
    with st.form("review_form"):
        st.write("请秉持“儿童本位”原则进行量化评估：")
        score_child = st.slider("儿童反馈主体性 (0-100)", 0, 100, 80)
        score_mix = st.slider("图文合奏度与叙事动力学 (0-100)", 0, 100, 80)
        score_ethics = st.slider("叙事伦理与包容度 (0-100)", 0, 100, 80)
        comment = st.text_area("专家学术评语及修改建议（必填）", placeholder="请输入评审理由...")
        
        submitted = st.form_submit_button("提交评审结果", type="primary")
        
        if submitted:
            if not comment.strip():
                st.error("请输入专家评语。")
            else:
                updated_metadata = artwork.get("metadata", {})
                updated_metadata["review_scores"] = {
                    "child_subjectivity": score_child,
                    "text_image": score_mix,
                    "ethics": score_ethics
                }
                updated_metadata["reviewer_comment"] = comment
                
                # 写入数据库
                supabase_client.table("contest_artworks").update({
                    "review_status": "completed",
                    "metadata": updated_metadata
                }).eq("id", current_id).execute()
                
                st.success("🎉 评审结果已安全入库！")
                st.balloons()
