import streamlit as st
import boto3
import os
import time
from botocore.config import Config

# --- 初始化 R2 连接 (只用 R2) ---
@st.cache_resource
def init_r2():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version="s3v4")
    )

def main():
    st.set_page_config(page_title="临时文档收发站", layout="wide")
    st.title("📥 临时文字作品收发站")
    
    r2_client = init_r2()
    bucket_name = os.getenv('R2_BUCKET_NAME')
    
    tab_upload, tab_download = st.tabs(["📤 选手上传区", "⬇️ 后台下载区(需密码)"])
    
   # === 1. 选手上传区 ===
    with tab_upload:
        st.info("请在此上传作品。单次最多允许上传 50 个文件，单个文件大小请勿超过 10MB。")
        
        uploaded_files = st.file_uploader(
            "拖拽或点击选择文件", 
            type=["pdf", "docx", "doc"], 
            accept_multiple_files=True
        )
        
        if uploaded_files:
            # --- 核心拦截校验逻辑 ---
            # 1. 校验数量限制
            if len(uploaded_files) > 50:
                st.error(f"⚠️ 当前选择了 {len(uploaded_files)} 个文件。单次最多只能上传 50 个，请分批处理。")
                st.stop() # 停止后续渲染，强制用户重新选择
                
            # 2. 校验单文件大小限制 (10MB = 10 * 1024 * 1024 bytes)
            MAX_SIZE_BYTES = 10 * 1024 * 1024
            oversized_files = [f.name for f in uploaded_files if f.size > MAX_SIZE_BYTES]
            
            if oversized_files:
                st.error("⚠️ 以下文件大小超过了 10MB 限制，请压缩后重新上传：")
                for name in oversized_files:
                    st.write(f"- {name}")
                st.stop() # 停止上传按钮的渲染
            
            # --- 校验通过，显示上传按钮 ---
            st.success(f"✅ 已选中 {len(uploaded_files)} 个合规文件，可以开始上传。")
            
            if st.button("🚀 开始安全上传", type="primary"):
                success_count = 0
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, file in enumerate(uploaded_files):
                    status_text.text(f"正在处理 ({idx+1}/{len(uploaded_files)}): {file.name}")
                    
                    # 加上时间戳防止同名文件互相覆盖
                    safe_filename = f"temp_text_works/{int(time.time())}_{file.name}"
                    try:
                        r2_client.upload_fileobj(file, bucket_name, safe_filename)
                        success_count += 1
                    except Exception as e:
                        st.error(f"❌ {file.name} 上传失败: {e}")
                    
                    # 动态更新进度条
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                status_text.empty()
                st.balloons()
                st.success(f"🎉 批量传输完成！成功上传 {success_count} 个文件。")

    # === 2. 后台下载区 ===
    with tab_download:
        pwd = st.text_input("请输入管理员密码以查看下载列表", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.divider()
            if st.button("🔄 刷新云端文件列表"):
                st.rerun()
                
            try:
                # 直接从 R2 获取文件列表
                response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix="temp_text_works/")
                files = response.get('Contents', [])
                
                if not files:
                    st.info("当前云端暂无上传的文件。")
                else:
                    st.write(f"共找到 **{len(files)}** 个文件：")
                    for file in files:
                        file_key = file['Key']
                        # 略过文件夹本身
                        if file_key == "temp_text_works/": 
                            continue
                            
                        # 生成 1 小时有效的下载链接
                        download_url = r2_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': bucket_name, 'Key': file_key},
                            ExpiresIn=3600 
                        )
                        # 剥离前缀，只显示文件名
                        display_name = file_key.replace("temp_text_works/", "")
                        st.markdown(f"- [{display_name}]({download_url})")
                        
            except Exception as e:
                st.error(f"读取文件列表失败: {e}")

if __name__ == "__main__":
    main()
