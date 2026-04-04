import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
import requests

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'BG4JTS/what')
GITHUB_API = 'https://api.github.com'

IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    DATA_DIR = '/tmp/data'
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

PROGRAMS_FILE = os.path.join(DATA_DIR, 'programs.json')
PENDING_FILE = os.path.join(DATA_DIR, 'pending.json')

def github_headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

def get_file_sha(path, branch='main'):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    params = {'ref': branch}
    resp = requests.get(url, headers=github_headers(), params=params)
    if resp.status_code == 200:
        return resp.json().get('sha')
    return None

def get_file_content(path, branch='main'):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    params = {'ref': branch}
    resp = requests.get(url, headers=github_headers(), params=params)
    if resp.status_code == 200:
        content = resp.json().get('content', '')
        if content:
            return json.loads(base64.b64decode(content).decode('utf-8'))
    return {"programs": []}

def update_file(path, content, message, branch='main', sha=None):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    if sha is None:
        sha = get_file_sha(path, branch)
    data = {
        'message': message,
        'content': base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8'),
        'branch': branch,
        'sha': sha
    }
    resp = requests.put(url, headers=github_headers(), json=data)
    return resp.status_code in [200, 201]

def create_branch(branch_name, base_branch='main'):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/git/refs/heads/{base_branch}'
    resp = requests.get(url, headers=github_headers())
    if resp.status_code != 200:
        return False
    sha = resp.json()['object']['sha']
    
    create_url = f'{GITHUB_API}/repos/{GITHUB_REPO}/git/refs'
    data = {
        'ref': f'refs/heads/{branch_name}',
        'sha': sha
    }
    resp = requests.post(create_url, headers=github_headers(), json=data)
    return resp.status_code == 201

def create_pr(title, head_branch, base_branch='main', body=''):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls'
    data = {
        'title': title,
        'head': head_branch,
        'base': base_branch,
        'body': body
    }
    resp = requests.post(url, headers=github_headers(), json=data)
    if resp.status_code == 201:
        return resp.json()
    return None

def merge_pr(pr_number, commit_message=''):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}/merge'
    data = {
        'commit_message': commit_message,
        'merge_method': 'squash'
    }
    resp = requests.put(url, headers=github_headers(), json=data)
    return resp.status_code == 200

def close_pr(pr_number):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}'
    data = {'state': 'closed'}
    resp = requests.patch(url, headers=github_headers(), json=data)
    return resp.status_code == 200

def get_pr_list(state='open'):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls'
    params = {'state': state, 'base': 'main'}
    resp = requests.get(url, headers=github_headers(), params=params)
    if resp.status_code == 200:
        return resp.json()
    return []

def load_programs_local():
    if os.path.exists(PROGRAMS_FILE):
        with open(PROGRAMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_programs_local(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROGRAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_pending_local():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_pending_local(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_programs():
    if GITHUB_TOKEN:
        try:
            data = get_file_content('data/programs.json', 'main')
            if data.get('programs'):
                save_programs_local(data)
                return data
        except:
            pass
    return load_programs_local()

@app.route('/')
def index():
    data = get_programs()
    programs = data.get('programs', [])
    return render_template('index.html', programs=programs)

@app.route('/add', methods=['GET', 'POST'])
def add_program():
    if request.method == 'POST':
        program = {
            'id': str(uuid.uuid4())[:8],
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'date': request.form.get('date'),
            'link': request.form.get('link'),
            'related': request.form.get('related', '').split(',') if request.form.get('related') else [],
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        
        if GITHUB_TOKEN:
            try:
                branch_name = f'program-{program["id"]}'
                create_branch(branch_name)
                
                pending_data = get_file_content('data/pending.json', branch_name)
                if not pending_data.get('programs'):
                    pending_data = {"programs": []}
                pending_data['programs'].append(program)
                
                update_file('data/pending.json', pending_data, 
                           f'添加待审核节目: {program["title"]}', branch_name)
                
                pr = create_pr(
                    f'[待审核] {program["title"]}',
                    branch_name,
                    'main',
                    f'**节目信息**\n- 编号: {program["id"]}\n- 标题: {program["title"]}\n- 日期: {program["date"]}\n- 描述: {program["description"]}\n- 链接: {program["link"]}'
                )
                
                if pr:
                    program['pr_number'] = pr['number']
                    program['branch'] = branch_name
                    
                    pending_local = load_pending_local()
                    pending_local['programs'].append(program)
                    save_pending_local(pending_local)
                    
                    flash(f'节目已提交！PR #{pr["number"]}', 'success')
                else:
                    flash('创建PR失败', 'error')
            except Exception as e:
                flash(f'提交失败: {str(e)}', 'error')
        else:
            pending_data = load_pending_local()
            pending_data['programs'].append(program)
            save_pending_local(pending_data)
            flash('节目已提交（本地模式）', 'success')
        
        return redirect(url_for('index'))
    
    programs_data = get_programs()
    all_programs = programs_data.get('programs', [])
    return render_template('add.html', programs=all_programs)

@app.route('/pending')
def list_pending():
    pending_data = load_pending_local()
    programs = pending_data.get('programs', [])
    return render_template('pending.html', programs=programs)

@app.route('/approve/<program_id>')
def approve_program(program_id):
    pending_data = load_pending_local()
    
    program = None
    for p in pending_data['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('list_pending'))
    
    program['status'] = 'approved'
    program['approved_at'] = datetime.now().isoformat()
    
    if GITHUB_TOKEN:
        try:
            programs_data = get_file_content('data/programs.json', 'main')
            if not programs_data.get('programs'):
                programs_data = {"programs": []}
            programs_data['programs'].append(program)
            update_file('data/programs.json', programs_data, f'审核通过: {program["title"]}')
            
            if program.get('pr_number'):
                merge_pr(program['pr_number'], f'审核通过: {program["title"]}')
            
            save_programs_local(programs_data)
            
            pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
            save_pending_local(pending_data)
            
            flash('节目已审核通过！', 'success')
        except Exception as e:
            flash(f'审核失败: {str(e)}', 'error')
    else:
        programs_data = load_programs_local()
        programs_data['programs'].append(program)
        save_programs_local(programs_data)
        
        pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
        save_pending_local(pending_data)
        
        flash('节目已审核通过！', 'success')
    
    return redirect(url_for('list_pending'))

@app.route('/reject/<program_id>')
def reject_program(program_id):
    pending_data = load_pending_local()
    
    program = None
    for p in pending_data['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('list_pending'))
    
    if GITHUB_TOKEN and program.get('pr_number'):
        try:
            close_pr(program['pr_number'])
        except:
            pass
    
    pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
    save_pending_local(pending_data)
    
    flash(f'节目 {program["title"]} 已被拒绝！', 'info')
    return redirect(url_for('list_pending'))

@app.route('/program/<program_id>')
def program_detail(program_id):
    programs_data = get_programs()
    program = None
    for p in programs_data['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('index'))
    
    related_programs = []
    for rel_id in program.get('related', []):
        for p in programs_data['programs']:
            if p['id'] == rel_id.strip():
                related_programs.append(p)
                break
    
    return render_template('detail.html', program=program, related_programs=related_programs)

def init_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PROGRAMS_FILE):
        save_programs_local({"programs": []})
    if not os.path.exists(PENDING_FILE):
        save_pending_local({"programs": []})

init_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
