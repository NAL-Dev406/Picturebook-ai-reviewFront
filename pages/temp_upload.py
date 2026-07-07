import streamlit as st
import boto3
import os
import time
import io
import zipfile
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
        st.info("单次最多允许上传 50 个文件。为了保证服务器稳定，【单批次总容量】请勿超过 100MB。")
        
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
                st.stop() 
                
            # 2. 校验单文件大小限制 (10MB)
            MAX_SINGLE_SIZE = 10 * 1024 * 1024
            oversized_files = [f.name for f in uploaded_files if f.size > MAX_SINGLE_SIZE]
            if oversized_files:
                st.error("⚠️ 以下单个文件大小超过了 10MB 限制，请压缩后重新上传：")
                for name in oversized_files:
                    st.write(f"- {name}")
                st.stop() 

            # 🌟 3. 新增：校验单批次总容量限制 (安全水位：100MB)
            MAX_TOTAL_SIZE = 100 * 1024 * 1024
            total_size = sum(f.size for f in uploaded_files)
            if total_size > MAX_TOTAL_SIZE:
                st.error(f"⚠️ 内存熔断保护：当前这批文件总大小为 {total_size / (1024*1024):.1f} MB，超出了服务器的安全上限 (100 MB)。请减少本次上传的文件数量，分多次上传。")
                st.stop()
            
            # --- 校验通过，显示上传按钮 ---
            st.success(f"✅ 已选中 {len(uploaded_files)} 个文件 (总计 {total_size / (1024*1024):.1f} MB)，可以安全上传。")
            
            if st.button("🚀 开始安全上传", type="primary"):
                success_count = 0
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, file in enumerate(uploaded_files):
                    status_text.text(f"正在处理 ({idx+1}/{len(uploaded_files)}): {file.name}")
                    
                    safe_filename = f"temp_text_works/{int(time.time())}_{file.name}"
                    try:
                        r2_client.upload_fileobj(file, bucket_name, safe_filename)
                        success_count += 1
                    except Exception as e:
                        st.error(f"❌ {file.name} 上传失败: {e}")
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                status_text.empty()
                st.balloons()
                st.success(f"🎉 批量传输完成！成功上传 {success_count} 个文件。")
                
   # === 2. 后台下载与管理区 ===
    with tab_download:
        pwd = st.text_input("请输入管理员密码以查看和管理文件", type="password")
        if pwd == os.getenv("REVIEWER_PASSWORD"):
            st.divider()
            
            # --- 顶层操作区：分设三个操作列 ---
            col_action1, col_action2, col_action3 = st.columns([1, 2, 2])
            
            with col_action1:
                if st.button("🔄 刷新云端列表", use_container_width=True):
                    st.rerun()
            
            with col_action2:
                # 🌟 新增：一键打包下载逻辑
                if st.button("📦 一键打包全部 (ZIP)", type="primary", use_container_width=True):
                    with st.spinner("正在从云端拉取文件并生成压缩包，请稍候..."):
                        try:
                            response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix="temp_text_works/")
                            files_to_zip = [f for f in response.get('Contents', []) if f['Key'] != "temp_text_works/"]
                            
                            if not files_to_zip:
                                st.warning("云端当前没有可打包的文件。")
                            else:
                                # 在内存中创建 ZIP 文件
                                zip_buffer = io.BytesIO()
                                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                    for file in files_to_zip:
                                        file_key = file['Key']
                                        file_name = file_key.replace("temp_text_works/", "")
                                        # 从 R2 获取文件流
                                        obj = r2_client.get_object(Bucket=bucket_name, Key=file_key)
                                        # 写入压缩包
                                        zip_file.writestr(file_name, obj['Body'].read())
                                
                                zip_buffer.seek(0)
                                
                                # 渲染出真正的下载按钮
                                st.success("✅ 打包完成！请点击下方按钮保存到本地。")
                                st.download_button(
                                    label=f"⬇️ 下载 NAL_文字作品打包_{int(time.time())}.zip",
                                    data=zip_buffer,
                                    file_name=f"NAL_纯文本作品打包_{int(time.time())}.zip",
                                    mime="application/zip",
                                    use_container_width=True
                                )
                        except Exception as e:
                            st.error(f"打包失败: {e}")

            with col_action3:
                # 危险操作区：一键清空所有文件
                with st.expander("🚨 危险操作区：清空所有文件"):
                    st.warning("此操作将永久删除 R2 存储桶中该目录下的所有纯文本文件，且不可恢复！建议下载 ZIP 后再操作。")
                    confirm_delete_all = st.checkbox("我已确认文件已安全备份，同意清空")
                    
                    if confirm_delete_all and st.button("🗑️ 确认全部清空", type="primary"):
                        with st.spinner("正在批量删除文件..."):
                            try:
                                response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix="temp_text_works/")
                                files_to_delete = response.get('Contents', [])
                                
                                if files_to_delete:
                                    delete_keys = [{'Key': obj['Key']} for obj in files_to_delete if obj['Key'] != "temp_text_works/"]
                                    if delete_keys:
                                        r2_client.delete_objects(Bucket=bucket_name, Delete={'Objects': delete_keys})
                                    st.success("✅ 所有临时文件已成功清空！")
                                    time.sleep(1) 
                                    st.rerun()
                                else:
                                    st.info("云端本来就是空的。")
                            except Exception as e:
                                st.error(f"清空失败: {e}")

            st.markdown("### 📂 当前云端待处理作品")
            try:
                response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix="temp_text_works/")
                files = response.get('Contents', [])
                valid_files = [f for f in files if f['Key'] != "temp_text_works/"]
                
                if not valid_files:
                    st.info("🎉 当前云端暂无待处理的作品文件。")
                else:
                    st.write(f"共找到 **{len(valid_files)}** 个文件：")
                    
                    for file in valid_files:
                        file_key = file['Key']
                        display_name = file_key.replace("temp_text_works/", "")
                        file_size_mb = file['Size'] / (1024 * 1024)
                        download_url = r2_client.generate_presigned_url('get_object', Params={'Bucket': bucket_name, 'Key': file_key}, ExpiresIn=3600)
                        
                        with st.container():
                            col_file, col_btn = st.columns([5, 1])
                            with col_file:
                                st.markdown(f"📄 [{display_name}]({download_url})  `({file_size_mb:.2f} MB)`")
                            with col_btn:
                                if st.button("🗑️ 删除", key=f"del_{file_key}", use_container_width=True):
                                    try:
                                        r2_client.delete_object(Bucket=bucket_name, Key=file_key)
                                        st.toast(f"已成功删除 {display_name}")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"删除 {display_name} 失败: {e}")
                            st.divider()
            except Exception as e:
                st.error(f"读取云端文件列表失败: {e}")

if __name__ == "__main__":
    main()
