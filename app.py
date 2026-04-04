import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
import requests

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'BG4JTS/what')
GITHUB_API = 'https://api.github.com'
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')

ADMIN_THRESHOLD = 5
INITIAL_ADMIN = os.environ.get('INITIAL_ADMIN', 'BG4JTS')

IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    DATA_DIR = '/tmp/data'
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

PROGRAMS_FILE = os.path.join(DATA_DIR, 'programs.json')
PENDING_FILE = os.path.join(DATA_DIR, 'pending.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

oauth = OAuth(app)
oauth.register(
    name='github',
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

class User(UserMixin):
    def __init__(self, user_dict):
        self.id = str(user_dict['id'])
        self.username = user_dict['login']
        self.avatar_url = user_dict.get('avatar_url', '')
        self.email = user_dict.get('email', '')
        self.is_admin = user_dict.get('is_admin', False)
        self.approved_count = user_dict.get('approved_count', 0)

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    for u in users:
        if str(u['id']) == user_id:
            return User(u)
    return None

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('users', [])
    return []

def save_users(users):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users}, f, ensure_ascii=False, indent=2)

def get_user_by_id(user_id):
    users = load_users()
    for u in users:
        if str(u['id']) == str(user_id):
            return u
    return None

def update_user(user_data):
    users = load_users()
    for i, u in enumerate(users):
        if str(u['id']) == str(user_data['id']):
            users[i] = user_data
            break
    save_users(users)

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

def get_pr(pr_number):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}'
    resp = requests.get(url, headers=github_headers())
    if resp.status_code == 200:
        return resp.json()
    return None

def get_pr_list(state='open'):
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls'
    params = {'state': state, 'base': 'main'}
    resp = requests.get(url, headers=github_headers(), params=params)
    if resp.status_code == 200:
        return resp.json()
    return []

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

def update_admin_status():
    programs_data = get_programs()
    programs = programs_data.get('programs', [])
    users = load_users()
    updated = False
    
    author_counts = {}
    for p in programs:
        author = p.get('author')
        if author:
            author_counts[author] = author_counts.get(author, 0) + 1
    
    for user in users:
        count = author_counts.get(user['login'], 0)
        if user.get('approved_count') != count:
            user['approved_count'] = count
            updated = True
        
        if count >= ADMIN_THRESHOLD and not user.get('is_admin'):
            user['is_admin'] = True
            updated = True
        
        if user['login'] == INITIAL_ADMIN and not user.get('is_admin'):
            user['is_admin'] = True
            updated = True
    
    if updated:
        save_users(users)
    
    return updated

def sync_from_github():
    if not GITHUB_TOKEN:
        return False, "未配置GITHUB_TOKEN"
    
    try:
        programs_data = get_file_content('data/programs.json', 'main')
        save_programs_local(programs_data)
        
        pending_data = load_pending_local()
        pr_list = get_pr_list('open')
        open_pr_ids = set()
        for pr in pr_list:
            if pr['title'].startswith('[待审核]'):
                for p in pending_data['programs']:
                    if p.get('pr_number') == pr['number']:
                        open_pr_ids.add(p['id'])
        
        pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] in open_pr_ids or not p.get('pr_number')]
        save_pending_local(pending_data)
        
        update_admin_status()
        
        return True, f"同步成功！共{len(programs_data.get('programs', []))}个节目"
    except Exception as e:
        return False, f"同步失败: {str(e)}"

@app.route('/')
def index():
    data = get_programs()
    programs = data.get('programs', [])
    return render_template('index.html', programs=programs)

@app.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login/github')
def login_github():
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        flash('GitHub OAuth未配置', 'error')
        return redirect(url_for('login'))
    redirect_uri = url_for('authorize', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get('user', token=token)
    user_info = resp.json()
    
    users = load_users()
    user_exists = False
    for u in users:
        if u['id'] == user_info['id']:
            u['login'] = user_info['login']
            u['avatar_url'] = user_info.get('avatar_url', '')
            u['email'] = user_info.get('email', '')
            user_exists = True
            break
    
    if not user_exists:
        users.append({
            'id': user_info['id'],
            'login': user_info['login'],
            'avatar_url': user_info.get('avatar_url', ''),
            'email': user_info.get('email', ''),
            'created_at': datetime.now().isoformat(),
            'is_admin': False,
            'approved_count': 0
        })
    
    save_users(users)
    
    update_admin_status()
    
    user = User(get_user_by_id(user_info['id']))
    login_user(user)
    
    if user.is_admin:
        flash(f'欢迎回来, 管理员 {user.username}!', 'success')
    else:
        flash(f'欢迎, {user.username}! 已通过 {user.approved_count}/{ADMIN_THRESHOLD} 个节目', 'success')
    
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/sync')
@login_required
def sync():
    if not current_user.is_admin:
        flash('只有管理员才能同步数据', 'error')
        return redirect(url_for('index'))
    
    success, message = sync_from_github()
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
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
            'created_at': datetime.now().isoformat(),
            'author': current_user.username
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
                    f'**节目信息**\n- 编号: {program["id"]}\n- 标题: {program["title"]}\n- 日期: {program["date"]}\n- 描述: {program["description"]}\n- 链接: {program["link"]}\n- 提交者: {program["author"]}'
                )
                
                if pr:
                    program['pr_number'] = pr['number']
                    program['branch'] = branch_name
                    program['pr_url'] = pr['html_url']
                    
                    pending_local = load_pending_local()
                    pending_local['programs'].append(program)
                    save_pending_local(pending_local)
                    
                    flash(f'节目已提交！请在GitHub合并PR: #{pr["number"]}', 'success')
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
@login_required
def approve_program(program_id):
    if not current_user.is_admin:
        flash('只有管理员才能审核节目', 'error')
        return redirect(url_for('list_pending'))
    
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
    program['approved_by'] = current_user.username
    
    if GITHUB_TOKEN and program.get('pr_number'):
        try:
            programs_data = get_file_content('data/programs.json', 'main')
            if not programs_data.get('programs'):
                programs_data = {"programs": []}
            programs_data['programs'].append(program)
            
            update_file('data/programs.json', programs_data, f'审核通过: {program["title"]}')
            
            merge_pr(program['pr_number'], f'审核通过: {program["title"]} (审核者: {current_user.username})')
            
            save_programs_local(programs_data)
            
            pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
            save_pending_local(pending_data)
            
            update_admin_status()
            
            flash(f'节目 "{program["title"]}" 已审核通过！', 'success')
        except Exception as e:
            flash(f'审核失败: {str(e)}', 'error')
    else:
        programs_data = load_programs_local()
        programs_data['programs'].append(program)
        save_programs_local(programs_data)
        
        pending_data['programs'] = [p for p in pending_data['programs'] if p['id'] != program_id]
        save_pending_local(pending_data)
        
        flash(f'节目 "{program["title"]}" 已审核通过！', 'success')
    
    return redirect(url_for('list_pending'))

@app.route('/reject/<program_id>')
@login_required
def reject_program(program_id):
    if not current_user.is_admin:
        flash('只有管理员才能审核节目', 'error')
        return redirect(url_for('list_pending'))
    
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
    
    flash(f'节目 "{program["title"]}" 已被拒绝！', 'info')
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
    if not os.path.exists(USERS_FILE):
        save_users([])

init_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
