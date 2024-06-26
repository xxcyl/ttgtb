import nest_asyncio
nest_asyncio.apply()

import google.generativeai as genai
from llama_parse import LlamaParse
from tqdm import tqdm
from collections import namedtuple
import streamlit as st
from pyngrok import ngrok
import base64
import os
import time
import re 

# 設定預設參數
TEMPERATURE = 0.2

# 從環境變數中讀取 API 金鑰
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
LLAMA_CLOUD_API_KEY = os.getenv('LLAMA_CLOUD_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)

# 初始化 LlamaParse 解析器
parser = LlamaParse(
    api_key=LLAMA_CLOUD_API_KEY,
    result_type="markdown"
)

def summarize_with_gemini(text, instructions, model_name, temperature=TEMPERATURE):
    """使用 Gemini API 生成摘要"""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        f"""
          {instructions}

          Article content:
          \n\n
          {text}
          """,
        generation_config=genai.types.GenerationConfig(temperature=temperature)
    )
    return response.text

# 定義問題列表
Question = namedtuple("Question", ["number", "text"])
questions_to_ask = [
    Question(1, "What problem does this paper aim to explore, and why is this problem worth investigating?"),
    Question(2, "What are the main findings and contributions of this research, and what is their significance?"),
    Question(3, "What methods and techniques did the researchers use to conduct this study, and what data or samples were used?"),
    Question(4, "What is the reliability and statistical significance of the research findings?"),
    Question(5, "What are the key theoretical foundations of this research?"),
    Question(6, "What challenges were encountered during the research process, and how were they overcome?"),
    Question(7, "How can the research findings be applied in practice or impact related fields?"),
    Question(8, "What are the limitations of the research, and what are the directions for future research?")
]

# 最近的輸出文件列表
recent_summaries = []

# 加載已生成的文件列表
def load_generated_files():
    if os.path.exists("generated_files.txt"):
        with open("generated_files.txt", "r") as f:
            return [line.strip() for line in f]
    return []

generated_files = load_generated_files()

# 保存生成的文件名
def save_generated_file(filename):
    generated_files.append(filename)
    with open("generated_files.txt", "a") as f:
        f.write(f"{filename}\n")

def sanitize_filename(filename):
    """去除文件名中的emoji和标点符号"""
    filename = re.sub(r'[^\w\s-]', '', filename).strip()
    filename = re.sub(r'[-\s]+', '-', filename).strip('-_')
    return filename

# Streamlit 應用介面
st.title("😴 It's time to go to bed")

# 增加說明文字
st.markdown("""
### 🤵🏻 大小姐，是時候該睡覺了，又在看論文嗎？
""")

# --- 主頁面選項卡 ---
main_tabs = st.tabs(["分析文獻", "歷史紀錄"]) 

# --- 側邊欄選項 ---
with st.sidebar:
    st.title("設定")

# --- 分析文獻選項卡 ---
with main_tabs[0]:
    st.markdown("""請在側邊攔上傳 PDF 格式的文獻，系統將自動分析文獻內容並生成相關資訊。過程需要幾分鐘，請耐心等候。完成後，您可以在「歷史紀錄」分頁找到生成的摘要（最多保留十筆）。點擊文件名即可展開或下載摘要內容。另外，AI 可能出錯，請務必閱讀原文確認內容。""")
    st.warning("⚠️ API 呼叫次數有限，若出現錯誤請稍後再試。")
    # **移除模型選擇選項，直接使用 gemini-1.5-flash**
    model_name_option = 'gemini-1.5-flash'

    uploaded_file = st.sidebar.file_uploader("上傳 PDF 文件", type=["pdf"])
    if uploaded_file:
        # 獲取上傳的文件名稱
        original_filename = uploaded_file.name
        
        # 獲取當前時間並格式化
        timestamp = time.strftime("%Y%m%d_%H%M%S") 

        # 儲存上傳的文件
        with open(original_filename, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # 解析 PDF 文件
        with st.spinner('解析 PDF 文件中...'):
            documents = parser.load_data(original_filename)
            content = documents[0].get_content()

        #  一次詢問所有問題
        final_summary = "" # 使用字符串存储结果
        with st.spinner('🕺🏻 呼叫 Gemini API 中...'):
            instructions = """
            Analyze the following article and answer the following 10 questions in fluent and natural-sounding Traditional Chinese that reflects common language use in Taiwan. Base your answers on the provided article and use evidence from the text to support your points. You will generate two additional questions based on the article content. 

            **Please format your response as follows:**

            **❓ 問題 1：** [問題內容] \n
            **🤖：** [答案內容] \n
            **📝： 這段內容主要參考了文章的 [概括文章相關部分] 部分。** \n\n

            **❓ 問題 2：** [問題內容] \n
            **🤖：** [答案內容] \n
            **📝： 這段內容主要參考了文章的 [概括文章相關部分] 部分。** \n\n
            ...

            **❓ 問題 9：** [AI generated question based on the article content]\n
            **🤖：** [答案內容] \n
            **📝： 這段內容主要參考了文章的 [概括文章相關部分] 部分。** \n\n

            **❓ 問題 10：** [AI generated question based on the article content]\n
            **🤖：** [答案內容] \n
            **📝： 這段內容主要參考了文章的 [概括文章相關部分] 部分。** \n\n

            **Do not include any other sections or headings.**

            **Provided Questions:**

            """
            for i in range(len(questions_to_ask)): # 使用循环生成问题编号
                instructions += f"{i+1}. **{questions_to_ask[i].text}**\n"

            final_summary = summarize_with_gemini(content, instructions, model_name_option) # 直接将结果存储到 final_summary

        # 呼叫 Gemini API 做最後摘要
        with st.spinner('🤵🏻 呀勒呀勒，看不完的臭論文'):
            instructions_refined_summary = """
            Please condense the following content, which is a Q&A format summary of a research article, into a concise abstract in fluent and natural-sounding Traditional Chinese, reflecting common language use in Taiwan. Please also include a relevant emoji at the beginning of the abstract title.

            **Please format your response as follows:**

            ## [Title]\n

            [Summary]

            **Do not include any other sections or headings.**
            
            **Constraints:**

            * Only use information provided in the Q&A summary.  Do not introduce any external information or knowledge.
            * The abstract should be less than 500 words.
            * Use Markdown format.
            """
            refined_summary = summarize_with_gemini(final_summary, instructions_refined_summary, model_name_option)

        # 從 refined_summary 中提取標題並清理
        title = refined_summary.split('\n')[0].replace('##', '').strip()
        cleaned_title = sanitize_filename(title)

        # 使用清理後的標題和時間戳生成文件名
        summary_filename = f"{timestamp}_{cleaned_title}.md"

        # 保存摘要到摘要文件
        with open(summary_filename, "w", encoding="utf-8") as f:
            f.write(f"{refined_summary}\n\n---\n\n{final_summary}")

        # 將文件名稱和內容加入最近的摘要列表
        recent_summaries.append((summary_filename, refined_summary, final_summary))
        save_generated_file(summary_filename)
        if len(recent_summaries) > 5:
            recent_summaries.pop(0)

        # 顯示摘要並提供下載連結
        st.markdown(f"{refined_summary}\n\n---\n\n{final_summary}")

        # 提供下載超連結
        with open(summary_filename, "rb") as f:
            bytes_data = f.read()
            b64 = base64.b64encode(bytes_data).decode()
            href = f'<a href="data:file/markdown;base64,{b64}" download="{summary_filename}">點擊此處下載摘要文件 ({summary_filename})</a>'
            st.markdown(href, unsafe_allow_html=True)

# --- 歷史紀錄選項卡 ---
with main_tabs[1]: 
    st.header("歷史紀錄")

    if generated_files:
        for file in generated_files[-10:][::-1]:  # 只顯示最近十筆，最新的在上面
            with st.expander(file):
                with open(file, "r", encoding="utf-8") as f:
                    file_content = f.read()
                st.markdown(file_content)
                # 提供下載連結
                with open(file, "rb") as f:
                    bytes_data = f.read()
                    b64 = base64.b64encode(bytes_data).decode()
                    href = f'<a href="data:file/markdown;base64,{b64}" download="{file}">點擊此處下載摘要文件 ({file})</a>'
                    st.markdown(href, unsafe_allow_html=True)
    else:
        st.info("目前沒有歷史紀錄。")
