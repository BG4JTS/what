import os
import json
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth

IS_VERCEL = os.environ.get('VERCEL') == '1'

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'BG4JTS/what')
GITHUB_API = 'https://api.github.com'
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')

ADMIN_THRESHOLD = 2
INITIAL_ADMIN = os.environ.get('INITIAL_ADMIN', 'BG4JTS')

if IS_VERCEL:
    # Vercel 环境使用内存存储
    MEMORY_STORAGE = {
        'tags': [],
        'hosts': [],
        'users': [],
        'references': []
    }
else:
    # 本地环境使用文件存储
    MEMORY_STORAGE = None
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    PROGRAMS_FILE = os.path.join(DATA_DIR, 'programs.json')
    PENDING_FILE = os.path.join(DATA_DIR, 'pending.json')
    USERS_FILE = os.path.join(DATA_DIR, 'users.json')
    REFERENCES_FILE = os.path.join(DATA_DIR, 'references.json')
    TAGS_FILE = os.path.join(DATA_DIR, 'tags.json')
    HOSTS_FILE = os.path.join(DATA_DIR, 'hosts.json')

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

def get_repo():
    if IS_VERCEL:
        return None
    return git.Repo(os.path.dirname(os.path.abspath(__file__)))

def init_branches():
    if IS_VERCEL:
        return
    repo = get_repo()
    branches = [b.name for b in repo.branches]
    
    if BRANCH_PENDING not in branches:
        repo.git.branch(BRANCH_PENDING)
    if BRANCH_APPROVED not in branches:
        repo.git.branch(BRANCH_APPROVED)

def load_programs_local():
    if IS_VERCEL:
        return {"programs": []}
    if os.path.exists(PROGRAMS_FILE):
        with open(PROGRAMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_programs_local(data):
    if IS_VERCEL:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROGRAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_pending_local():
    if IS_VERCEL:
        return {"programs": []}
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": []}

def save_pending_local(data):
    if IS_VERCEL:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_users():
    if IS_VERCEL:
        return MEMORY_STORAGE.get('users', [])
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_users(users):
    if IS_VERCEL:
        MEMORY_STORAGE['users'] = users
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_references():
    if IS_VERCEL:
        return {"references": MEMORY_STORAGE.get('references', [])}
    if os.path.exists(REFERENCES_FILE):
        with open(REFERENCES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"references": []}

def save_references(data):
    if IS_VERCEL:
        MEMORY_STORAGE['references'] = data.get('references', [])
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REFERENCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_tags():
    if IS_VERCEL:
        return MEMORY_STORAGE.get('tags', [])
    if os.path.exists(TAGS_FILE):
        with open(TAGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('tags', [])
    return []

def save_tags(tags):
    if IS_VERCEL:
        MEMORY_STORAGE['tags'] = tags
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'tags': tags}, f, ensure_ascii=False, indent=2)

def add_tag(tag_name, author):
    tags = load_tags()
    tag_lower = tag_name.strip().lower()
    for t in tags:
        if t.get('name', '').lower() == tag_lower:
            return t
    new_tag = {
        'id': str(uuid.uuid4())[:8],
        'name': tag_name.strip(),
        'created_at': datetime.now().isoformat(),
        'created_by': author
    }
    tags.append(new_tag)
    save_tags(tags)
    return new_tag

def get_tag_by_id(tag_id):
    tags = load_tags()
    for t in tags:
        if t['id'] == tag_id:
            return t
    return None

def load_hosts():
    if IS_VERCEL:
        return MEMORY_STORAGE.get('hosts', [])
    if os.path.exists(HOSTS_FILE):
        with open(HOSTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('hosts', [])
    return []

def save_hosts(hosts):
    if IS_VERCEL:
        MEMORY_STORAGE['hosts'] = hosts
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HOSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'hosts': hosts}, f, ensure_ascii=False, indent=2)

def add_host(host_name, author):
    hosts = load_hosts()
    host_lower = host_name.strip().lower()
    for h in hosts:
        if h.get('name', '').lower() == host_lower:
            return h
    new_host = {
        'id': str(uuid.uuid4())[:8],
        'name': host_name.strip(),
        'created_at': datetime.now().isoformat(),
        'created_by': author
    }
    hosts.append(new_host)
    save_hosts(hosts)
    return new_host

def get_host_by_id(host_id):
    hosts = load_hosts()
    for h in hosts:
        if h['id'] == host_id:
            return h
    return None

def get_file_content(path, branch='main'):
    import base64
    if not GITHUB_TOKEN:
        return None
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        response = requests.get(url, headers=headers, params={'ref': branch})
        if response.status_code == 200:
            content = response.json()
            return base64.b64decode(content['content']).decode('utf-8')
        return None
    except:
        return None

def update_file(path, content, message, branch='main'):
    import base64
    if not GITHUB_TOKEN:
        return False
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        response = requests.get(url, headers=headers, params={'ref': branch})
        if response.status_code == 200:
            sha = response.json()['sha']
        else:
            sha = None
        
        data = {
            'message': message,
            'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            'branch': branch
        }
        if sha:
            data['sha'] = sha
        
        response = requests.put(url, headers=headers, json=data)
        return response.status_code in [200, 201]
    except:
        return False

def create_branch(branch_name):
    if not GITHUB_TOKEN:
        return False
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/git/refs'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        response = requests.get(url, headers=headers, params={'ref': 'heads/main'})
        if response.status_code == 200:
            main_ref = response.json()[0]
            sha = main_ref['object']['sha']
            
            data = {
                'ref': f'refs/heads/{branch_name}',
                'sha': sha
            }
            response = requests.post(url, headers=headers, json=data)
            return response.status_code == 201
    except:
        pass
    return False

def create_pr(title, body, head, base='main'):
    if not GITHUB_TOKEN:
        return None
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        data = {
            'title': title,
            'body': body,
            'head': head,
            'base': base
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            return response.json()
    except:
        pass
    return None

def merge_pr(pr_number):
    if not GITHUB_TOKEN:
        return False
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}/merge'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        data = {
            'commit_title': f'Merge PR #{pr_number}',
            'commit_message': 'Merged via API',
            'squash': True
        }
        response = requests.put(url, headers=headers, json=data)
        return response.status_code == 200
    except:
        pass
    return False

def close_pr(pr_number):
    if not GITHUB_TOKEN:
        return False
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/pulls/{pr_number}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    import requests
    try:
        data = {
            'state': 'closed'
        }
        response = requests.patch(url, headers=headers, json=data)
        return response.status_code == 200
    except:
        pass
    return False

def get_programs():
    content = get_file_content('data/programs.json')
    if content:
        try:
            return json.loads(content)
        except:
            pass
    return load_programs_local()

def get_pending():
    content = get_file_content('data/pending.json')
    if content:
        try:
            return json.loads(content)
        except:
            pass
    return load_pending_local()

def save_programs(data):
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if update_file('data/programs.json', content, 'Update programs'):
        return True
    save_programs_local(data)
    return False

def save_pending(data):
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if update_file('data/pending.json', content, 'Update pending programs'):
        return True
    save_pending_local(data)
    return False

def add_reference(target_code, target_title, source_program_id, source_program_title, author):
    refs = load_references()
    refs['references'].append({
        'target_code': target_code,
        'target_title': target_title,
        'source_program_id': source_program_id,
        'source_program_title': source_program_title,
        'author': author,
        'created_at': datetime.now().isoformat(),
        'notified': False
    })
    save_references(refs)

def check_and_notify_references(program_code, program_title, program_id):
    refs = load_references()
    notifications = []
    
    for ref in refs['references']:
        if not ref.get('notified'):
            target = ref.get('target_code', '').strip().lower()
            target_title = ref.get('target_title', '').strip().lower()
            
            if (target and target == program_code.lower().strip()) or \
               (target_title and target_title in program_title.lower()):
                notifications.append(ref)
                ref['notified'] = True
                ref['matched_program_id'] = program_id
                ref['matched_at'] = datetime.now().isoformat()
    
    if notifications:
        save_references(refs)
    
    return notifications

def update_user_approved_count(username):
    users = load_users()
    for user in users:
        if user.get('login') == username:
            user['approved_count'] = user.get('approved_count', 0) + 1
            if user['approved_count'] >= ADMIN_THRESHOLD:
                user['is_admin'] = True
            save_users(users)
            return True
    return False

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get('user')
    user_info = resp.json()
    
    users = load_users()
    existing_user = None
    for u in users:
        if u['id'] == user_info['id']:
            existing_user = u
            break
    
    if existing_user:
        existing_user['login'] = user_info['login']
        existing_user['avatar_url'] = user_info.get('avatar_url', '')
        existing_user['email'] = user_info.get('email', '')
        if existing_user['login'] == INITIAL_ADMIN:
            existing_user['is_admin'] = True
        save_users(users)
    else:
        new_user = {
            'id': user_info['id'],
            'login': user_info['login'],
            'avatar_url': user_info.get('avatar_url', ''),
            'email': user_info.get('email', ''),
            'is_admin': user_info['login'] == INITIAL_ADMIN,
            'approved_count': 0
        }
        users.append(new_user)
        save_users(users)
    
    user = User(existing_user if existing_user else new_user)
    login_user(user)
    flash('登录成功！', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    data = get_programs()
    programs = data.get('programs', [])
    refs = load_references()
    pending_refs = [r for r in refs.get('references', []) if not r.get('notified')]
    
    tags = load_tags()
    hosts = load_hosts()
    
    for program in programs:
        program_tags = []
        for tag_id in program.get('tags', []):
            for t in tags:
                if t['id'] == tag_id:
                    program_tags.append(t)
                    break
            else:
                program_tags.append({'id': tag_id, 'name': tag_id})
        program['tags'] = program_tags
        
        program_hosts = []
        for host_id in program.get('hosts', []):
            for h in hosts:
                if h['id'] == host_id:
                    program_hosts.append(h)
                    break
            else:
                program_hosts.append({'id': host_id, 'name': host_id})
        program['hosts'] = program_hosts
    
    return render_template('index.html', programs=programs, pending_refs=pending_refs)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_program():
    programs = get_programs()
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if not code:
            flash('请输入番号！', 'error')
            return redirect(url_for('add_program'))
        
        pending_data = get_pending()
        existing_codes = {p.get('code', '').lower() for p in pending_data.get('programs', [])}
        programs_data = get_programs()
        existing_codes.update({p.get('code', '').lower() for p in programs_data.get('programs', [])})
        
        if code.lower() in existing_codes:
            flash('番号已存在，请使用其他番号！', 'error')
            return redirect(url_for('add_program'))
        
        related_ids = request.form.getlist('related')
        tag_ids = request.form.getlist('tags')
        host_ids = request.form.getlist('hosts')
        
        future_ref_code = request.form.get('future_ref_code', '').strip()
        future_ref_title = request.form.get('future_ref_title', '').strip()
        
        program = {
            'id': str(uuid.uuid4())[:8],
            'code': code,
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'date': request.form.get('date'),
            'link': request.form.get('link'),
            'related': related_ids,
            'tags': tag_ids,
            'hosts': host_ids,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'author': current_user.username
        }
        
        pending = get_pending()
        pending['programs'].append(program)
        
        if GITHUB_TOKEN:
            branch_name = f'program-{program["id"]}'
            if create_branch(branch_name):
                if update_file('data/pending.json', json.dumps(pending, ensure_ascii=False, indent=2), f'Add program {program["title"]}', branch_name):
                    pr = create_pr(
                        f'[待审核] {program["title"]}',
                        f'节目信息：\n- 番号：{program["code"]}\n- 标题：{program["title"]}\n- 发布日期：{program["date"]}\n- 提交者：{current_user.username}\n\n请审核并合并。',
                        branch_name
                    )
                    if pr:
                        program['pr_number'] = pr['number']
                        program['branch'] = branch_name
                        pending['programs'][-1] = program
                        save_pending(pending)
        else:
            save_pending(pending)
        
        if future_ref_code or future_ref_title:
            add_reference(future_ref_code, future_ref_title, program['id'], program['title'], current_user.username)
        
        flash('节目添加成功，已提交审核！', 'success')
        return redirect(url_for('index'))
    
    return render_template('add.html', programs=programs.get('programs', []))

@app.route('/pending')
def pending_programs():
    pending = get_pending()
    programs = pending.get('programs', [])
    return render_template('pending.html', programs=programs)

@app.route('/approve/<program_id>')
@login_required
def approve_program(program_id):
    if not current_user.is_admin:
        flash('只有管理员可以审核节目！', 'error')
        return redirect(url_for('pending_programs'))
    
    pending = get_pending()
    program = None
    for p in pending['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('pending_programs'))
    
    programs = get_programs()
    program['status'] = 'approved'
    program['approved_at'] = datetime.now().isoformat()
    program['approved_by'] = current_user.username
    programs['programs'].append(program)
    
    pending['programs'] = [p for p in pending['programs'] if p['id'] != program_id]
    
    save_programs(programs)
    save_pending(pending)
    
    if GITHUB_TOKEN and program.get('pr_number'):
        merge_pr(program['pr_number'])
    
    update_user_approved_count(program.get('author', ''))
    
    notifications = check_and_notify_references(program['code'], program['title'], program['id'])
    if notifications:
        flash(f'节目审核通过，有 {len(notifications)} 个引用被匹配！', 'success')
    else:
        flash('节目审核通过！', 'success')
    
    return redirect(url_for('pending_programs'))

@app.route('/reject/<program_id>')
@login_required
def reject_program(program_id):
    if not current_user.is_admin:
        flash('只有管理员可以审核节目！', 'error')
        return redirect(url_for('pending_programs'))
    
    pending = get_pending()
    program = None
    for p in pending['programs']:
        if p['id'] == program_id:
            program = p
            break
    
    if not program:
        flash('节目不存在！', 'error')
        return redirect(url_for('pending_programs'))
    
    pending['programs'] = [p for p in pending['programs'] if p['id'] != program_id]
    save_pending(pending)
    
    if GITHUB_TOKEN and program.get('pr_number'):
        close_pr(program['pr_number'])
    
    flash('节目已拒绝！', 'info')
    return redirect(url_for('pending_programs'))

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
            if p['id'] == rel_id:
                related_programs.append(p)
                break
    
    tags = load_tags()
    hosts = load_hosts()
    
    program_tags = []
    for tag_id in program.get('tags', []):
        for t in tags:
            if t['id'] == tag_id:
                program_tags.append(t)
                break
        else:
            program_tags.append({'id': tag_id, 'name': tag_id})
    
    program_hosts = []
    for host_id in program.get('hosts', []):
        for h in hosts:
            if h['id'] == host_id:
                program_hosts.append(h)
                break
        else:
            program_hosts.append({'id': host_id, 'name': host_id})
    
    program['tags'] = program_tags
    program['hosts'] = program_hosts
    
    refs = load_references()
    referenced_by = [r for r in refs.get('references', []) if r.get('matched_program_id') == program_id]
    
    return render_template('detail.html', program=program, related_programs=related_programs, referenced_by=referenced_by)

@app.route('/references')
def list_references():
    refs = load_references()
    return render_template('references.html', references=refs.get('references', []))

@app.route('/sync')
@login_required
def sync_data():
    if not current_user.is_admin:
        flash('只有管理员可以同步数据！', 'error')
        return redirect(url_for('index'))
    
    try:
        programs = get_programs()
        pending = get_pending()
        refs = load_references()
        
        for program in programs['programs']:
            check_and_notify_references(program.get('code', ''), program.get('title', ''), program.get('id', ''))
        
        flash('数据同步成功！', 'success')
    except Exception as e:
        flash(f'同步失败: {e}', 'error')
    
    return redirect(url_for('index'))

@app.route('/api/tags')
def api_get_tags():
    tags = load_tags()
    return jsonify({'tags': tags})

@app.route('/api/tags/add', methods=['POST'])
@login_required
def api_add_tag():
    name = request.json.get('name', '').strip()
    if not name:
        return jsonify({'error': '名称不能为空'}), 400
    
    tag = add_tag(name, current_user.username)
    return jsonify({'tag': tag})

@app.route('/api/hosts')
def api_get_hosts():
    hosts = load_hosts()
    return jsonify({'hosts': hosts})

@app.route('/api/hosts/add', methods=['POST'])
@login_required
def api_add_host():
    name = request.json.get('name', '').strip()
    if not name:
        return jsonify({'error': '名称不能为空'}), 400
    
    host = add_host(name, current_user.username)
    return jsonify({'host': host})

def init_data():
    if not IS_VERCEL:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(PROGRAMS_FILE):
            save_programs_local({"programs": []})
        if not os.path.exists(PENDING_FILE):
            save_pending_local({"programs": []})
        if not os.path.exists(USERS_FILE):
            save_users([])
        if not os.path.exists(REFERENCES_FILE):
            save_references({"references": []})
        if not os.path.exists(TAGS_FILE):
            save_tags([])
        if not os.path.exists(HOSTS_FILE):
            save_hosts([])

init_data()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
