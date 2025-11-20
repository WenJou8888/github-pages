# -*- coding: utf-8 -*-
import pandas as pd
import os
import subprocess
import datetime
import json
from flask import Flask, request, jsonify, render_template_string

# --- 這是給 PythonAnywhere 用的 Flask 程式碼 ---

# !!! 重要：請修改成您在 PythonAnywhere 上的路徑 !!!
# 您可以在 PythonAnywhere 的 Bash 中輸入 `pwd` 查看路徑
# 通常是 /home/您的使用者名稱/資料夾名稱
REPO_PATH = "/home/TIT65mate/repo" 

DATA_FILENAME = "lineinput.csv"
COMMIT_MESSAGE_PREFIX = "排程更新"
HTML_TITLE = "排程協作表 (點擊輸入)"

# 定義順序
DAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
NAMES = ["小明", "小益", "小美", "小強", "小麗"]

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'

# --- Git 功能 ---
def run_git_command(command, cwd):
    try:
        # 確保目錄安全 (解決 dubious ownership)
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", cwd], check=False)
        
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace'
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def push_to_github(repo_path, filename):
    """拉取 -> 加入 -> 提交 -> 推送"""
    # 1. Pull (避免衝突)
    run_git_command(["git", "pull"], repo_path)
    
    # 2. Add
    ok, out, err = run_git_command(["git", "add", filename], repo_path)
    if not ok: return False, f"Add失敗: {err}"

    # 3. Commit
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"{COMMIT_MESSAGE_PREFIX} {timestamp}"
    run_git_command(["git", "commit", "-m", msg], repo_path)
    # Commit 即使沒變更回傳非0也不算失敗，所以這裡不嚴格檢查

    # 4. Push
    ok, out, err = run_git_command(["git", "push"], repo_path)
    if not ok: return False, f"Push失敗 (請檢查SSH key或密碼): {err}"
    
    return True, "成功更新"

# --- 資料讀寫 ---
def load_csv(filepath):
    if not os.path.exists(filepath): return {}
    try:
        df = pd.read_csv(filepath, index_col=0)
        df.fillna("", inplace=True)
        return df.to_dict(orient='index')
    except: return {}

def save_csv(data, filepath):
    try:
        df = pd.DataFrame.from_dict(data, orient='index')
        df = df.reindex(index=DAYS, columns=NAMES)
        df.fillna("", inplace=True)
        df.to_csv(filepath, encoding='utf-8-sig')
        return True
    except: return False

# --- 網頁內容 (HTML + CSS + JS) ---
def get_html(current_data):
    # 預先填入資料
    rows_html = ""
    for day in DAYS:
        cells = f"<td class='day'>{day}</td>"
        for name in NAMES:
            val = current_data.get(day, {}).get(name, "")
            # 設定樣式與顯示文字
            cls = "cell"
            txt = "&nbsp;"
            if val == "O": cls += " is-o"; txt = "O"
            elif val == "X": cls += " is-x"; txt = "X"
            else: cls += " is-blank"
            
            cells += f"<td class='{cls}' data-d='{day}' data-n='{name}'>{txt}</td>"
        rows_html += f"<tr>{cells}</tr>"

    names_html = "".join([f"<th>{n}</th>" for n in NAMES])
    
    return f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{HTML_TITLE}</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #333; text-align: center; padding: 0; height: 40px; }}
            th {{ background: #eee; padding: 5px; }}
            .day {{ background: #f9f9f9; font-weight: bold; }}
            
            /* 點擊格樣式 */
            .cell {{ cursor: pointer; font-size: 20px; font-weight: bold; user-select: none; }}
            .cell:hover {{ background: #f0f0f0; }}
            .is-o {{ color: green; background: #eaffea; }}
            .is-x {{ color: red; background: #ffeaea; }}
            .is-blank {{ }}

            button {{ width: 100%; padding: 15px; background: #28a745; color: white; border: none; font-size: 18px; cursor: pointer; border-radius: 5px; }}
            button:hover {{ background: #218838; }}
            button:disabled {{ background: #ccc; }}
            #msg {{ margin-top: 10px; text-align: center; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2 style="text-align:center">{HTML_TITLE}</h2>
        <p style="text-align:center; font-size:0.9rem; color:#666">點擊格子切換 O / X / 空白，完成後請按儲存</p>
        
        <table>
            <thead><tr><th></th>{names_html}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        
        <button id="btn" onclick="save()">儲存並上傳 GitHub</button>
        <div id="msg"></div>

        <script>
            // 點擊切換邏輯
            document.querySelectorAll('.cell').forEach(td => {{
                td.addEventListener('click', () => {{
                    let t = td.innerText;
                    if (t === 'O') {{ td.innerText = 'X'; td.className = 'cell is-x'; }}
                    else if (t === 'X') {{ td.innerText = '\\u00A0'; td.className = 'cell is-blank'; }}
                    else {{ td.innerText = 'O'; td.className = 'cell is-o'; }}
                }});
            }});

            async function save() {{
                let btn = document.getElementById('btn');
                let msg = document.getElementById('msg');
                btn.disabled = true; btn.innerText = "處理中..."; msg.innerText = "";

                // 收集資料
                let data = {{}};
                let days = {json.dumps(DAYS)};
                let names = {json.dumps(NAMES)};
                days.forEach(d => {{ data[d] = {{}}; names.forEach(n => data[d][n] = ""); }});

                document.querySelectorAll('.cell').forEach(td => {{
                    let val = td.innerText.trim();
                    if(val) data[td.dataset.d][td.dataset.n] = val;
                }});

                // 發送
                try {{
                    let res = await fetch('/save', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(data)
                    }});
                    let ret = await res.json();
                    if(ret.ok) {{
                        msg.style.color = "green"; msg.innerText = "✅ " + ret.msg;
                    }} else {{
                        msg.style.color = "red"; msg.innerText = "❌ " + ret.msg;
                    }}
                }} catch(e) {{
                    msg.style.color = "red"; msg.innerText = "連線錯誤";
                }}
                btn.disabled = false; btn.innerText = "儲存並上傳 GitHub";
            }}
        </script>
    </body>
    </html>
    """

# --- 路由設定 ---
@app.route('/')
def home():
    # 每次載入網頁時，先去 GitHub 拉最新資料
    run_git_command(["git", "pull"], REPO_PATH)
    
    csv_path = os.path.join(REPO_PATH, DATA_FILENAME)
    current_data = load_csv(csv_path)
    return render_template_string(get_html(current_data))

@app.route('/save', methods=['POST'])
def save():
    data = request.json
    csv_path = os.path.join(REPO_PATH, DATA_FILENAME)
    
    if save_csv(data, csv_path):
        ok, msg = push_to_github(REPO_PATH, DATA_FILENAME)
        if ok: return jsonify({"ok": True, "msg": "成功儲存並推送到 GitHub！"})
        else: return jsonify({"ok": False, "msg": f"存檔成功但推送失敗: {msg}"})
    else:
        return jsonify({"ok": False, "msg": "存檔失敗"})

# 本地測試用 (PythonAnywhere 不會執行這段)
if __name__ == '__main__':
    app.run(debug=True)
