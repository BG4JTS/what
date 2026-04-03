import os
import json
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import git

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PROGRAMS_FILE = os.path.join(DATA_DIR, 'programs.json')
PENDING_FILE = os.path.join(DATA_DIR, 'pending.json')

BRANCH_PENDING = 'pending-review'
BRANCH_APPROVED = 'approved'

def get_repo():
    return git.Repo(BASE_DIR)

def init_branches():
    repo = get_repo()
    branches = [b.name for b in repo.branches]
    
    if BRANCH_PENDING not in branches:
        repo.git.branch(BRANCH_PENDING)
    if BRANCH_APPROVED not in branches:
        repo.git.branch(BRANCH_APPROVED)

def load_programs():
    if os.path.exists(PROGRAMS_FILE):
        with open(PROGRAMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_programs(data):
    with open(PROGRAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_pending(data):
    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def git_commit(branch, message):
    repo = get_repo()
    current_branch = repo.active_branch.name
    
    repo.git.add(A=True)
    
    if repo.is_dirty():
        repo.git.stash()
    
    repo.git.checkout(branch)
    repo.git.add(A=True)
    
    if repo.is_dirty():
        repo.index.commit(message)
    
    repo.git.checkout(current_branch)
    
    if repo.git.stash('list'):
        repo.git.stash('pop')

@app.route('/')
def index():
    data = load_programs()
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
        
        pending_data = load_pending()
        pending_data['programs'].append(program)
        save_pending(pending_data)
        
        try:
            git_commit(BRANCH_PENDING, f'添加待审核节目: {program["title"]} (ID: {program["id"]})')
            flash('节目已提交，等待审核！', 'success')
        except Exception as e:
            flash(f'提交成功，但Git操作失败: {str(e)}', 'warning')
        
        return redirect(url_for('index'))
    
    programs_data = load_programs()
    all_programs = programs_data.get('programs', [])
    return render_template('add.html', programs=all_programs)

@app.route('/pending')
def list_pending():
    pending_data = load_pending()
    programs = pending_data.get('programs', [])
    return render_template('pending.html', programs=programs)

@app.route('/approve/<program_id>')
def approve_program(program_id):
    pending_data = load_pending()
    programs_data = load_programs()
    
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
    
    programs_data['programs'].append(program)
    save_programs(programs_data)
    
    pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
    save_pending(pending_data)
    
    try:
        git_commit(BRANCH_APPROVED, f'审核通过节目: {program["title"]} (ID: {program["id"]})')
        flash('节目已审核通过！', 'success')
    except Exception as e:
        flash(f'审核成功，但Git操作失败: {str(e)}', 'warning')
    
    return redirect(url_for('list_pending'))

@app.route('/reject/<program_id>')
def reject_program(program_id):
    pending_data = load_pending()
    
    program = None
    for p in pending_data['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('list_pending'))
    
    pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
    save_pending(pending_data)
    
    flash(f'节目 {program["title"]} 已被拒绝！', 'info')
    return redirect(url_for('list_pending'))

@app.route('/program/<program_id>')
def program_detail(program_id):
    programs_data = load_programs()
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

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PROGRAMS_FILE):
        save_programs({"programs": []})
    if not os.path.exists(PENDING_FILE):
        save_pending({"programs": []})
    
    try:
        init_branches()
    except Exception as e:
        print(f'初始化分支失败: {e}')
    
    app.run(debug=True, host='0.0.0.0', port=5000)
