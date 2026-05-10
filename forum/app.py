from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    reputation = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship('Question', backref='author', lazy=True)
    answers = db.relationship('Answer', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Question(db.Model):
    __tablename__ = 'question'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=False)
    votes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    answers_count = db.Column(db.Integer, default=0)
    tags = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    answers = db.relationship('Answer', backref='question', lazy='dynamic',
                              cascade='all, delete-orphan')


class Answer(db.Model):
    __tablename__ = 'answer'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    votes = db.Column(db.Integer, default=0)
    is_accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)


class Vote(db.Model):
    __tablename__ = 'vote'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    answer_id = db.Column(db.Integer, db.ForeignKey('answer.id'))
    vote_type = db.Column(db.String(10))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    sort = request.args.get('sort', 'newest')
    search = request.args.get('q', '')
    tag_filter = request.args.get('tag', '')

    questions_query = Question.query

    if search:
        questions_query = questions_query.filter(
            db.or_(
                Question.title.contains(search),
                Question.body.contains(search)
            )
        )

    if tag_filter:
        questions_query = questions_query.filter(
            Question.tags.contains(tag_filter)
        )

    if sort == 'votes':
        questions_query = questions_query.order_by(Question.votes.desc())
    elif sort == 'views':
        questions_query = questions_query.order_by(Question.views.desc())
    elif sort == 'unanswered':
        questions_query = questions_query.filter(Question.answers_count == 0) \
            .order_by(Question.created_at.desc())
    else:
        questions_query = questions_query.order_by(Question.created_at.desc())

    questions = questions_query.all()

    stats = {
        'questions': Question.query.count(),
        'answers': Answer.query.count(),
        'users': User.query.count()
    }

    all_tags = {}
    for q in Question.query.all():
        if q.tags:
            for tag in q.tags.split(','):
                tag = tag.strip().lower()
                if tag:
                    all_tags[tag] = all_tags.get(tag, 0) + 1

    popular_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template('index.html',
                           questions=questions,
                           stats=stats,
                           popular_tags=popular_tags,
                           sort=sort,
                           search=search)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('Все поля обязательны для заполнения', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль должен быть минимум 6 символов', 'error')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email уже используется', 'error')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash('Регистрация успешна! Теперь войдите в систему.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'Добро пожаловать, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))

        flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/ask', methods=['GET', 'POST'])
@login_required
def ask():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        tags = request.form.get('tags', '').strip()

        if not title or not body:
            flash('Заголовок и описание обязательны', 'error')
            return render_template('ask.html')

        if len(title) < 10:
            flash('Заголовок должен быть минимум 10 символов', 'error')
            return render_template('ask.html')

        if tags:
            tags_list = [t.strip().lower() for t in tags.split(',') if t.strip()]
            tags = ','.join(tags_list[:5])

        question = Question(
            title=title,
            body=body,
            tags=tags,
            user_id=current_user.id
        )

        current_user.reputation += 2

        db.session.add(question)
        db.session.commit()

        flash('Вопрос успешно опубликован!', 'success')
        return redirect(url_for('question', question_id=question.id))

    return render_template('ask.html')


@app.route('/question/<int:question_id>')
def question(question_id):
    question = Question.query.get_or_404(question_id)

    question.views += 1
    db.session.commit()

    answers = Answer.query.filter_by(question_id=question.id) \
        .order_by(Answer.is_accepted.desc(), Answer.votes.desc()) \
        .all()

    user_votes = {}
    if current_user.is_authenticated:
        vote = Vote.query.filter_by(
            user_id=current_user.id,
            question_id=question.id
        ).first()
        if vote:
            user_votes[f'q{question.id}'] = vote.vote_type

        for answer in answers:
            vote = Vote.query.filter_by(
                user_id=current_user.id,
                answer_id=answer.id
            ).first()
            if vote:
                user_votes[f'a{answer.id}'] = vote.vote_type

    return render_template('question.html',
                           question=question,
                           answers=answers,
                           user_votes=user_votes)


@app.route('/question/<int:question_id>/answer', methods=['POST'])
@login_required
def answer(question_id):
    question = Question.query.get_or_404(question_id)
    body = request.form.get('body', '').strip()

    if not body:
        flash('Ответ не может быть пустым', 'error')
        return redirect(url_for('question', question_id=question_id))

    answer = Answer(
        body=body,
        user_id=current_user.id,
        question_id=question_id
    )

    question.answers_count += 1
    current_user.reputation += 1

    db.session.add(answer)
    db.session.commit()

    flash('Ответ успешно опубликован!', 'success')
    return redirect(url_for('question', question_id=question_id))


@app.route('/vote/question/<int:question_id>/<vote_type>')
@login_required
def vote_question(question_id, vote_type):
    if vote_type not in ['up', 'down']:
        flash('Неверный тип голоса', 'error')
        return redirect(url_for('index'))

    question = Question.query.get_or_404(question_id)

    if question.user_id == current_user.id:
        flash('Нельзя голосовать за свой вопрос', 'warning')
        return redirect(url_for('question', question_id=question_id))

    existing_vote = Vote.query.filter_by(
        user_id=current_user.id,
        question_id=question_id
    ).first()

    if existing_vote:
        if existing_vote.vote_type == vote_type:
            db.session.delete(existing_vote)
            if vote_type == 'up':
                question.votes -= 1
                question.author.reputation -= 10
            else:
                question.votes += 1
                question.author.reputation += 2
        else:
            existing_vote.vote_type = vote_type
            if vote_type == 'up':
                question.votes += 2
                question.author.reputation += 12
            else:
                question.votes -= 2
                question.author.reputation -= 12
    else:
        vote = Vote(
            user_id=current_user.id,
            question_id=question_id,
            vote_type=vote_type
        )
        db.session.add(vote)
        if vote_type == 'up':
            question.votes += 1
            question.author.reputation += 10
        else:
            question.votes -= 1
            question.author.reputation -= 2

    db.session.commit()
    return redirect(url_for('question', question_id=question_id))


@app.route('/vote/answer/<int:answer_id>/<vote_type>')
@login_required
def vote_answer(answer_id, vote_type):
    if vote_type not in ['up', 'down']:
        flash('Неверный тип голоса', 'error')
        return redirect(url_for('index'))

    answer = Answer.query.get_or_404(answer_id)

    if answer.user_id == current_user.id:
        flash('Нельзя голосовать за свой ответ', 'warning')
        return redirect(url_for('question', question_id=answer.question_id))

    existing_vote = Vote.query.filter_by(
        user_id=current_user.id,
        answer_id=answer_id
    ).first()

    if existing_vote:
        if existing_vote.vote_type == vote_type:
            db.session.delete(existing_vote)
            if vote_type == 'up':
                answer.votes -= 1
                answer.author.reputation -= 10
            else:
                answer.votes += 1
                answer.author.reputation += 2
        else:
            existing_vote.vote_type = vote_type
            if vote_type == 'up':
                answer.votes += 2
                answer.author.reputation += 12
            else:
                answer.votes -= 2
                answer.author.reputation -= 12
    else:
        vote = Vote(
            user_id=current_user.id,
            answer_id=answer_id,
            vote_type=vote_type
        )
        db.session.add(vote)
        if vote_type == 'up':
            answer.votes += 1
            answer.author.reputation += 10
        else:
            answer.votes -= 1
            answer.author.reputation -= 2

    db.session.commit()
    return redirect(url_for('question', question_id=answer.question_id))


@app.route('/accept/<int:answer_id>')
@login_required
def accept(answer_id):
    answer = Answer.query.get_or_404(answer_id)
    question = Question.query.get(answer.question_id)

    if question.user_id != current_user.id:
        flash('Только автор вопроса может принять ответ', 'error')
        return redirect(url_for('question', question_id=question.id))

    old_accepted = Answer.query.filter_by(
        question_id=question.id,
        is_accepted=True
    ).first()
    if old_accepted:
        old_accepted.is_accepted = False

    answer.is_accepted = True
    answer.author.reputation += 15

    db.session.commit()
    flash('Ответ принят!', 'success')
    return redirect(url_for('question', question_id=question.id))


@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))

    questions = Question.query.filter_by(user_id=user.id) \
        .order_by(Question.created_at.desc()).all()

    answers = Answer.query.filter_by(user_id=user.id) \
        .order_by(Answer.created_at.desc()).all()

    return render_template('user.html',
                           user=user,
                           questions=questions,
                           answers=answers,
                           questions_count=len(questions),
                           answers_count=len(answers))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)