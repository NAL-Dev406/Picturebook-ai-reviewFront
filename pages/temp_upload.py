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
        st.info("请在此上传您的 Word 或 PDF 作品。")
        uploaded_files = st.file_uploader("支持多选", type=["pdf", "docx", "doc"], accept_multiple_files=True)
        
        if uploaded_files and st.button("开始上传", type="primary"):
            success_count = 0
            with st.spinner("正在安全上传到云端..."):
                for file in uploaded_files:
                    # 加上时间戳防止同名文件互相覆盖
                    safe_filename = f"temp_text_works/{int(time.time())}_{file.name}"
                    try:
                        r2_client.upload_fileobj(file, bucket_name, safe_filename)
                        success_count += 1
                    except Exception as e:
                        st.error(f"{file.name} 上传失败: {e}")
            
            st.success(f"成功上传 {success_count} 个文件！")

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
