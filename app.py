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
    try:
        with tqdm(total=1, desc="Gemini API 處理中") as pbar:
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
            pbar.update(1)
            return response.text
    except Exception as e:
        return f"使用 Gemini API 生成摘要時發生錯誤: {e}"

# 定義問題列表
Question = namedtuple("Question", ["number", "text"])

# 將八個問題合併成一個列表
questions = [
    Question(1, "What problem does this paper aim to explore, and why is this problem worth investigating?"),
    Question(2, "What are the main findings and contributions of this research, and what is their significance?"),
    Question(3, "What methods and techniques did the researchers use to conduct this study, and what data or samples were used?"),
    Question(4, "What is the reliability and statistical significance of the research findings?"),
    Question(5, "What are the key theoretical foundations of this research?"),
    Question(6, "What challenges were encountered during the research process, and how were they overcome?"),
    Question(7, "How can the research findings be applied in practice or impact related fields?"),
    Question(8, "What are the limitations of the research, and what are the directions for future research?")
]

# 用于统一排版的指令
format_instructions = """
Please ensure the following text follows a consistent Markdown format:

**Format Requirements:**
1. Each question should start with "**❓ 問題 [Number]：**", followed by the question content.
2. Each answer should start with "**🤖 回答：**", followed by the answer content.
3. After the detailed answer, provide a quote from the article. Quotes should start with "[原文出處]" and use Markdown's blockquote syntax with a single "> ".

**Example Format:**

**❓ 問題 1：** What problem does this paper aim to explore, and why is this problem worth investigating?
**🤖 回答：** [Detailed Answer]  
> [Quote from the article]

**❓ 問題 2：** What are the main findings and contributions of this research, and what is their significance?
**🤖 回答：** [Detailed Answer]
> [Quote from the article]

**Notes:**
- Ensure the Markdown format is consistent throughout the text.
- If encountering formatting errors or other issues, please review and adjust the format accordingly.

Please reformat the text for consistency:
"""

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
    num_requests = st.radio("選擇 API 呼叫次數：", (1, 2), index=1, help="可自行嘗試效果差異。")

# --- 分析文獻選項卡 ---
with main_tabs[0]:
    st.markdown("""請在側邊攔上傳 PDF 格式的文獻，系統將自動分析文獻內容並生成相關資訊。過程需要幾分鐘，請耐心等候。完成後，您可以在「歷史紀錄」分頁找到生成的摘要（最多保留十筆）。  點擊文件名即可展開或下載摘要內容。""")
    st.warning("""
    ⚠️ **注意：**
    * 因為 API 呼叫次數有限，若出現錯誤表示超過使用限制，請過幾分鐘後再試。
    * AI 可能出錯，請務必閱讀原文確認內容。
    """)
    # 移除模型選擇選項，直接使用 gemini-1.5-flash
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
        st.text("🕺🏻 解析 PDF 文件中...")
        try:
            with st.spinner('解析 PDF 文件中...'):
                documents = parser.load_data(original_filename)
                content = documents[0].get_content()
        except Exception as e:
            st.error(f"解析 PDF 文件時發生錯誤: {e}")
            st.stop()

        # 根據選擇的 API 呼叫次數調整問題列表
        if num_requests == 1:
            questions_to_ask = [Question(1, " ".join([q.text for q in questions]))]
        else:
            questions_to_ask = [questions[:4], questions[4:]]

        # 分批詢問問題並合併結果
        all_answers = []
        total_groups = len(questions_to_ask)
        progress_bar = st.progress(0)
        api_limit_reached = False
        for idx, question_group in enumerate(questions_to_ask):
            if api_limit_reached:
                break

            if num_requests == 1:
                st.text(f"🕺🏻 呼叫 Gemini API 中...")
                instructions = """
                Analyze the following article and answer the questions in fluent and natural-sounding Traditional Chinese that reflects common language use in Taiwan. Make sure to directly quote relevant parts from the article to support your answers. Do not translate or paraphrase the quotes.

                **Questions:**

                """
                instructions += f"{question_group.number}. **{question_group.text}**\n"
                answers = summarize_with_gemini(content, instructions, model_name_option)
            else:
                st.text(f"🕺🏻 呼叫 Gemini API 中... （第 {idx + 1} 組問題，共 {total_groups} 組）")
                instructions = """
                Analyze the following article and answer the questions in fluent and natural-sounding Traditional Chinese that reflects common language use in Taiwan. Make sure to directly quote relevant parts from the article to support your answers. Do not translate or paraphrase the quotes.

                **Questions:**

                """
                for question in question_group:
                    instructions += f"{question.number}. **{question.text}**\n"

                # 为每一组问题都加入输出格式示例
                instructions += """
                **Output Format Example:**

                ## 研究問答

                **❓ 問題 1：** What problem does this paper aim to explore, and why is this problem worth investigating?
                **🤖 回答：** [Detailed Answer]  
                > [Quote from the article]

                **❓ 問題 2：** What are the main findings and contributions of this research, and what is their significance?
                **🤖 回答：** [Detailed Answer]  
                > [Quote from the article]
                """

                # 呼叫 summarize_with_gemini 函數
                answers = summarize_with_gemini(content, instructions, model_name_option)

                if "超過使用限制" in answers:
                    st.warning("超過 API 使用限制，請稍後再試。")
                    api_limit_reached = True
                    break
            
            all_answers.append(answers)
            progress_bar.progress((idx + 1) / total_groups)
        
        if not api_limit_reached:
            # 合併所有回答
            merged_answers = "\n\n".join(all_answers)

            # 生成輸出文件名
            sanitized_filename = sanitize_filename(original_filename)
            output_filename = f"output_{sanitized_filename}_{timestamp}.md"
            with open(output_filename, "w", encoding='utf-8') as f:
                f.write(merged_answers)

            # 添加到歷史記錄中
            save_generated_file(output_filename)

            # 顯示結果
            st.success("🎉 生成摘要成功！")
            st.markdown("### 生成的摘要")
            st.markdown(merged_answers)

            # 提供下載連結
            with open(output_filename, "rb") as file:
                file_bytes = file.read()
                b64 = base64.b64encode(file_bytes).decode()
                href = f'<a href="data:text/markdown;base64,{b64}" download="{output_filename}">下載摘要文件</a>'
                st.markdown(href, unsafe_allow_html=True)

# --- 歷史紀錄選項卡 ---
with main_tabs[1]:
    st.markdown("""
    ## 歷史紀錄

    在這裡你可以查看和下載之前生成的摘要文件。
    """)

    if generated_files:
        for filename in generated_files[-10:]:
            with open(filename, "r", encoding='utf-8') as f:
                content = f.read()
                st.markdown(f"### {filename}")
                st.markdown(content)
                with open(filename, "rb") as file:
                    file_bytes = file.read()
                    b64 = base64.b64encode(file_bytes).decode()
                    href = f'<a href="data:text/markdown;base64,{b64}" download="{filename}">下載摘要文件</a>'
                    st.markdown(href, unsafe_allow_html=True)
    else:
        st.markdown("目前沒有歷史紀錄。")
