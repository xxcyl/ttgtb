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
import re  # 引入 re 模組用於正則表達式處理

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

# 定義問題列表
Question = namedtuple("Question", ["number", "text"])

all_questions = [
    Question(1, "What problem does this paper aim to explore?"),
    Question(2, "Why is this problem worth investigating?"),
    Question(3, "What are the main findings and contributions of this research?"),
    Question(4, "What methods and techniques did the researchers use to conduct this study?"),
    Question(5, "What are the key theoretical foundations of this research?"),
    Question(6, "What data or samples were used in the study, and what are their characteristics?"),
    Question(7, "What is the reliability and statistical significance of the research findings?"),
    Question(8, "What challenges were encountered during the research process, and how were they overcome?"),
    Question(9, "How can the research findings be applied in practice or impact related fields?"),
    Question(10, "What are the limitations of the research, and what are the directions for future research?")
]

# 用于统一排版的指令
format_instructions = """
Please ensure the following text follows a consistent Markdown format:

**Format Requirements:**
1. Each question should start with "**❓ 問題 [Number]：**", followed by the question content.
2. Each answer should start with "**🤖 回答：**", followed by the answer content.
3. After the detailed answer, provide a quote from the article. Quotes should start with "[原文出處]" and use Markdown's blockquote syntax with a single "> ".

**Example Format:**

❓ 問題 1： What problem does this paper aim to explore?
🤖 回答： [Detailed Answer]  
> [Quote from the article]

❓ 問題 2： Why is this problem worth investigating?
🤖 回答： [Detailed Answer]
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
main_tabs = st.tabs(["分析文獻", "歷史紀錄"]) # 移除 "關於" 選項卡

# --- 分析文獻選項卡 ---
with main_tabs[0]:
    st.markdown("""請在側邊攔上傳 PDF 格式的文獻，系統將自動分析文獻內容並生成相關資訊。過程需要幾分鐘，請耐心等候。完成後，您可以在「歷史紀錄」分頁找到生成的摘要（最多保留十筆）。  點擊文件名即可展開或下載摘要內容。""")
    st.warning("""
    ⚠️ **注意：**
    * 因為 API 呼叫次數有限，若出現錯誤表示超過使用限制，請過幾分鐘後再試。
    * AI 可能出錯，請務必閱讀原文確認內容。
    """)
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
        st.text("🕺🏻 解析 PDF 文件中...")
        try:
            with st.spinner('解析 PDF 文件中...'):
                documents = parser.load_data(original_filename)
                content = documents[0].get_content()
        except Exception as e:
            st.error(f"解析 PDF 文件時發生錯誤: {e}")
            st.stop()

        # 分批詢問問題並合併結果
        all_answers = []
        question_groups = [all_questions[i:i + 5] for i in range(0, len(all_questions), 5)]
        total_groups = len(question_groups)
        progress_bar = st.progress(0)
        api_limit_reached = False
        for idx, question_group in enumerate(question_groups):
            if api_limit_reached:
                break
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

            **1.** What problem does this paper aim to explore?
              **🤖 回答：**  
              [Detailed Answer]
              [Quote from the article]

            **2.** Why is this problem worth investigating?
              **🤖 回答：**  
              [Detailed Answer]
              [Quote from the article]
            """

            answers = summarize_with_gemini(content, instructions, model_name_option)
            
            if "API 呼叫次數已達上限" in answers:
                st.error(answers)
                api_limit_reached = True
                break
            elif "使用 Gemini API 生成摘要時發生錯誤" in answers:
                st.error(answers)
                break
            all_answers.append(answers)

            # 更新進度條
            progress_bar.progress((idx + 1) / total_groups)

        if not api_limit_reached:
            # 合併所有答案
            st.text("🕺🏻 合併所有答案中...")
            final_summary = "\n\n".join(all_answers)

            # 统一最终答案的排版
            st.text("🕺🏻 統一排版中...")
            formatted_final_summary = summarize_with_gemini(final_summary, format_instructions, model_name_option, temperature=0.0)

            # 呼叫 Gemini API 做最後摘要
            st.text("🤵🏻 呀勒呀勒，看不完的臭論文")
            instructions_refined_summary = """
            Please condense the following content, which is a Q&A format summary of a research article, into a concise abstract in fluent and natural-sounding Traditional Chinese, reflecting common language use in Taiwan. Please also include a relevant emoji at the beginning of the abstract title.

            **Output Format:**

            ## [Title]\n

            [Summary]

            **Constraints:**

            * Only use information provided in the Q&A summary.  Do not introduce any external information or knowledge.
            * The abstract should be less than 500 words.
            * Use Markdown format.
            """
            refined_summary = summarize_with_gemini(formatted_final_summary, instructions_refined_summary, model_name_option)

            # 從 refined_summary 中提取標題並清理
            title = refined_summary.split('\n')[0].replace('##', '').strip()
            cleaned_title = sanitize_filename(title)

            # 使用清理後的標題和時間戳生成文件名
            summary_filename = f"{timestamp}_{cleaned_title}.md"

            # 保存摘要到摘要文件
            with open(summary_filename, "w", encoding="utf-8") as f:
                f.write(f"{refined_summary}\n\n---\n\n{formatted_final_summary}")

            # 將文件名稱和內容加入最近的摘要列表
            recent_summaries.append((summary_filename, refined_summary, formatted_final_summary))
            save_generated_file(summary_filename)
            if len(recent_summaries) > 5:
                recent_summaries.pop(0)

            # 顯示摘要並提供下載連結
            st.header("文獻分析")
            st.markdown(f"{refined_summary}\n\n---\n\n{formatted_final_summary}")

            st.success(f"Gemini 整理後的重點已保存到：{summary_filename}")

            # 提供下載超連結
            with open(summary_filename, "rb") as f:
                bytes_data = f.read()
                b64 = base64.b64encode(bytes_data).decode()
                href = f'<a href="data:file/markdown;base64,{b64}" download="{summary_filename}">點擊此處下載摘要文件 ({summary_filename})</a>'
                st.markdown(href, unsafe_allow_html=True)

# --- 歷史紀錄選項卡 ---
with main_tabs[1]:  # 注意索引更改為 1
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
