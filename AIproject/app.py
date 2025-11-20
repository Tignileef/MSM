import os
import re
import pandas as pd
from flask import Flask, render_template, request, session, redirect, url_for
import google.generativeai as genai
from dotenv import load_dotenv
from markupsafe import Markup
import markdown

# --- 1. 기본 설정 ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Excel 파일 경로 (절대 경로로 변경하여 안정성 확보)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE_PATH = os.path.join(BASE_DIR, "점심메뉴추천.xlsx")
print(f"--- [정보] 메뉴 파일 경로: {EXCEL_FILE_PATH} ---")

# Gemini API 설정
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')
    is_api_ready = True
except Exception as e:
    print(f"API 키 설정에 실패했습니다: {e}")
    is_api_ready = False

# --- 2. 헬퍼 함수 (값 정제 / 추가 / 삭제 / 수정) ---

def clean_value(s):
    """
    문자열에서 '원', 'kcal', '약' 등을 제거합니다.
    - "4900원" -> "4900"
    - "약 850kcal" -> "850"
    - "7000~9000원" -> "7000~9000" (범위 문자열 유지)
    """
    if isinstance(s, (int, float)):
        return str(int(s))  # 숫자인 경우 문자열로 반환
    
    s = str(s).strip()
    
    # '원', 'kcal', '약', 공백, 쉼표(,) 제거
    s = re.sub(r'[원,kcal약\s]', '', s)
    
    # ~ 또는 ～가 포함된 범위(예: "7000~9000")인지 먼저 확인
    if '~' in s or '～' in s:
        s = s.replace(',', '') 
        return s # "7000~9000" 문자열 자체를 반환
    
    # 숫자로만 구성되어 있는지 확인
    if s.isdigit():
        return s # "4900" 문자열 반환
        
    return "0"  # 변환 실패 시 "0" 문자열 반환

# (1) 추가 함수 (변경 없음)
def add_menu_item(restaurant, day, menu, price, calories, food_type, taste):
    """Excel 파일에 새 메뉴 항목(7개 열)을 추가합니다."""
    try:
        try:
            df = pd.read_excel(EXCEL_FILE_PATH)
        except: # FileNotFoundError 등 모든 파일 읽기 오류 포함
            df = pd.DataFrame(columns=['식당 이름', '요일', '메뉴', '가격', '칼로리', '음식의 종류', '맛'])

        price_val = clean_value(price)
        cal_val = clean_value(calories)

        new_row_data = {
            '식당 이름': restaurant, '요일': day, '메뉴': menu,
            '가격': price_val, '칼로리': cal_val,
            '음식의 종류': food_type, '맛': taste
        }
        df.loc[len(df)] = new_row_data
        
        df.to_excel(EXCEL_FILE_PATH, index=False)
        return True, f"✅ '{menu}' 메뉴가 성공적으로 추가되었습니다."
    
    except Exception as e:
        print(f"파일 저장 중 오류 발생 (add_menu_item): {e}")
        return False, f"❌ 메뉴 추가 중 오류가 발생했습니다: {e}"

# [수정] (2) 삭제 함수 - 식당 이름과 메뉴 이름을 모두 받도록 변경
def delete_menu_item(restaurant_name, menu_name):
    """Excel 파일에서 '식당 이름'과 '메뉴' 이름이 모두 일치하는 행을 삭제합니다."""
    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        
        original_rows = len(df)
        
        # [수정] '식당 이름'과 '메뉴'가 모두 일치하는 행의 index를 찾습니다.
        target_index = df[(df['식당 이름'] == restaurant_name) & (df['메뉴'] == menu_name)].index
        
        if len(target_index) == 0:
            return False, f"❌ '{restaurant_name}' 식당의 '{menu_name}' 메뉴를 찾을 수 없습니다."

        # 해당 index의 행을 삭제합니다.
        df = df.drop(target_index)
        
        # 변경사항 저장
        df.to_excel(EXCEL_FILE_PATH, index=False)
        return True, f"✅ '{restaurant_name}' 식당의 '{menu_name}' 메뉴가 삭제되었습니다."

    except FileNotFoundError:
        return False, "❌ 메뉴 파일을 찾을 수 없습니다."
    except Exception as e:
        print(f"파일 삭제 중 오류 발생 (delete_menu_item): {e}")
        return False, f"❌ 메뉴 삭제 중 오류가 발생했습니다: {e}"

# [수정] (3) 수정 함수 - 식당 이름과 메뉴 이름을 모두 받도록 변경
def modify_menu_item(restaurant_name, menu_name, column_to_edit, new_value):
    """Excel 파일에서 '식당 이름'과 '메뉴'가 일치하는 행의 특정 열 값을 수정합니다."""
    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        
        # [수정] '식당 이름'과 '메뉴'가 모두 일치하는 행의 index를 찾습니다.
        target_index = df[(df['식당 이름'] == restaurant_name) & (df['메뉴'] == menu_name)].index
        
        if len(target_index) == 0:
            return False, f"❌ '{restaurant_name}' 식당의 '{menu_name}' 메뉴를 찾을 수 없습니다."

        # DataFrame의 열 이름 목록과 일치하는지 확인
        valid_columns = ['식당 이름', '요일', '메뉴', '가격', '칼로리', '음식의 종류', '맛']
        if column_to_edit not in valid_columns:
            return False, f"❌ '{column_to_edit}'은(는) 유효한 항목(열 이름)이 아닙니다. {valid_columns} 중에서 선택해야 합니다."

        # 가격이나 칼로리를 수정하는 경우, 값 정제
        if column_to_edit in ['가격', '칼로리']:
            new_value = clean_value(new_value)

        # df.loc[index, column] = new_value 로 값 수정
        df.loc[target_index, column_to_edit] = new_value
        
        # 변경사항 저장
        df.to_excel(EXCEL_FILE_PATH, index=False)
        return True, f"✅ '{restaurant_name}' 식당 '{menu_name}' 메뉴의 '{column_to_edit}' 항목이 '{new_value}'(으)로 수정되었습니다."

    except FileNotFoundError:
        return False, "❌ 메뉴 파일을 찾을 수 없습니다."
    except Exception as e:
        print(f"파일 수정 중 오류 발생 (modify_menu_item): {e}")
        return False, f"❌ 메뉴 수정 중 오류가 발생했습니다: {e}"


# get_system_prompt 함수 (변경 없음)
def get_system_prompt():
    """최신 메뉴 데이터를 기반으로 시스템 프롬프트를 생성합니다."""
    menu_data = ""
    try:
        df = pd.read_excel(EXCEL_FILE_PATH)
        
        if '가격' in df.columns:
            df['가격'] = df['가격'].apply(clean_value).astype(str)
        if '칼로리' in df.columns:
            df['칼로리'] = df['칼로리'].apply(clean_value).astype(str)
            
        menu_data = df.to_markdown(index=False)
        
    except FileNotFoundError:
        menu_data = "데이터 없음 (아직 추가된 메뉴가 없습니다)"
    except Exception as e: 
        print(f"--- !!! 파일 로드 오류 발생 (get_system_prompt) !!! ---")
        print(f"{e}")
        print(f"---------------------------------------------------")
        menu_data = "데이터 로드 중 오류 발생"

    # LLM에게 전달할 최종 지시문
    return f"""
당신은 사용자의 상황(요일, 예산, 칼로리, 맛 선호)을 종합적으로 고려하는 최고의 점심 메뉴 추천 AI입니다.

[핵심 지침]
1.  아래 '메뉴 리스트'의 모든 열을 종합적으로 참고하여 추천합니다.
2.  **[중요] 대화 기록을 분석하여... (이하 동일)**
3.  '가격' 열에 "7000~9000"처럼 범위가 있다면... (이하 동일)
4.  '요일' 열을 참고하여... (이하 동일)
5.  리스트에 없는 메뉴는 없다고 솔직하게 말하세요.
6.  **[수정] '!추가', '!삭제', '!수정' 명령어가 들어오면, Python 함수가 이미 처리를 완료했으므로 "명령이 처리되었습니다." 또는 "오류가 발생했습니다."와 같이 Python이 반환한 결과 메시지를 그대로 전달하거나, 짧게 확인 응답만 하세요.**

--- 메뉴 리스트 ---
{menu_data}
--------------------
"""

# --- 3. Flask 라우트 (웹페이지 로직) ---

@app.route('/', methods=['GET', 'POST'])
def chat():
    # 1. 세션 초기화 (처음 방문 시)
    if 'chat_history' not in session:
        # [수정] Tip 메시지에 변경된 명령어 형식 안내
        session['chat_history'] = [
            {'role': 'model', 'content': '안녕하세요! 점심 메뉴 추천 챗봇입니다.<br><br>'
             '<b>[명령어 Tip]</b><br>'
             '<code>!추가 식당/요일/메뉴/가격/칼로리/종류/맛</code><br>'
             '<code>!삭제 식당이름 / 메뉴이름</code><br>'
             '<code>!수정 식당이름 / 메뉴이름 / 변경할항목 / 새값</code><br>'
             '(예: <code>!수정 학식 / 김치볶음밥 / 가격 / 5500</code>)'
            }
        ]

    # 2. 메시지 전송 (POST 요청)
    if request.method == 'POST':
        query = request.form.get('query')
        if not query or not is_api_ready:
            return redirect(url_for('chat'))

        # 사용자 메시지 기록
        session['chat_history'].append({'role': 'user', 'content': query})
        
        query_lower = query.strip().lower() # 명령어 감지를 위해 소문자로
        query_strip = query.strip()

        # 3. 명령어 감지 로직 (if/elif/else)
        
        # (1) '!추가' 명령어 (변경 없음)
        if query_lower.startswith('!추가'):
            parts = query_strip[3:].split('/')
            if len(parts) >= 7:
                _, msg = add_menu_item(
                    parts[0].strip(), parts[1].strip(), parts[2].strip(),
                    parts[3].strip(), parts[4].strip(), parts[5].strip(),
                    parts[6].strip()
                )
                session['chat_history'].append({'role': 'model', 'content': msg})
            else:
                msg = "<b>❌ 형식 오류:</b> <code>!추가 식당/요일/메뉴/가격/칼로리/종류/맛</code>"
                session['chat_history'].append({'role': 'model', 'content': msg})

        # [수정] (2) '!삭제' 명령어
        elif query_lower.startswith('!삭제'):
            parts = query_strip[3:].split('/')
            if len(parts) >= 2:
                restaurant_name = parts[0].strip()
                menu_name = parts[1].strip()
                _, msg = delete_menu_item(restaurant_name, menu_name)
                session['chat_history'].append({'role': 'model', 'content': msg})
            else:
                msg = "<b>❌ 형식 오류:</b> <code>!삭제 식당이름 / 메뉴이름</code>"
                session['chat_history'].append({'role': 'model', 'content': msg})

        # [수정] (3) '!수정' 명령어
        elif query_lower.startswith('!수정'):
            parts = query_strip[3:].split('/')
            if len(parts) >= 4: # 식당/메뉴/항목/값 = 4개
                restaurant_name = parts[0].strip()
                menu_name = parts[1].strip()
                column_to_edit = parts[2].strip()
                new_value = parts[3].strip()
                
                # '가격' 열을 '가격'으로, '식당 이름'을 '식당 이름'으로 정확히 매핑
                # 사용자가 띄어쓰기를 잊어도 보정
                if column_to_edit == "식당이름": column_to_edit = "식당 이름"
                if column_to_edit == "음식의종류": column_to_edit = "음식의 종류"
                
                _, msg = modify_menu_item(restaurant_name, menu_name, column_to_edit, new_value)
                session['chat_history'].append({'role': 'model', 'content': msg})
            else:
                msg = "<b>❌ 형식 오류:</b> <code>!수정 식당이름 / 메뉴이름 / 변경할항목 / 새값</code>"
                session['chat_history'].append({'role': 'model', 'content': msg})

        # (4) 일반 채팅 처리 (LLM API 호출)
        else:
            try:
                conversation_history = [{'role': msg['role'], 'parts': [msg['content']]} for msg in session['chat_history'][:-1]]
                chat_session = model.start_chat(history=conversation_history)
                current_system_prompt = get_system_prompt()
                
                response = chat_session.send_message(current_system_prompt + "\n사용자 질문: " + query)
                
                html_content = markdown.markdown(response.text, extensions=['nl2br'])
                session['chat_history'].append({'role': 'model', 'content': html_content})
            
            except Exception as e:
                print(f"Gemini API 오류: {e}")
                session['chat_history'].append({'role': 'model', 'content': f"죄송합니다. 챗봇 응답 중 오류가 발생했습니다: {e}"})

        session.modified = True
        return redirect(url_for('chat'))

    # 5. 페이지 로드 (GET 요청)
    return render_template('index.html', chat_history=session.get('chat_history', []), is_ready=is_api_ready)

@app.route('/clear', methods=['POST'])
def clear_chat():
    """대화 기록 삭제"""
    session.pop('chat_history', None)
    return redirect(url_for('chat'))

# --- 4. 앱 실행 ---
if __name__ == '__main__':
    # 앱 시작 시 파일이 없으면 7개 열을 가진 새 파일 생성
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"--- '{EXCEL_FILE_PATH}' 파일이 없어 새로 생성합니다. ---")
        df = pd.DataFrame(columns=['식당 이름', '요일', '메뉴', '가격', '칼로리', '음식의 종류', '맛'])
        df.to_excel(EXCEL_FILE_PATH, index=False)
        
    app.run(debug=True, port=5001) # 포트 충돌 방지를 위해 5001번 포트 사용