from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request, redirect, url_for, flash, session
import re
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime

# Убираем импорт check_password_hash, так как хэширование отключено
# from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12345@localhost/shop_db'
app.secret_key = 'your_secret_key'  # Для работы с сессиями и flash-сообщениями
db = SQLAlchemy(app)


class Product(db.Model):
    __tablename__ = 'products'
    product_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    description = db.Column(db.String)
    image_url = db.Column(db.String)

    price_histories = db.relationship('PriceHistory', backref='product_ref', lazy=True)


class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    price_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.product_id'), nullable=False)
    price = db.Column(db.Float)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date, nullable=True)


# Модель для клиента
class Customer(db.Model):
    __tablename__ = 'customers'
    customer_id = db.Column(db.Integer, primary_key=True)  # Автоинкремент
    fname = db.Column(db.String)
    sname = db.Column(db.String)
    phone = db.Column(db.String)
    email = db.Column(db.String, unique=True)


class UserCredentials(db.Model):
    __tablename__ = 'user_credentials'
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.customer_id'), primary_key=True)
    password = db.Column(db.String)


@app.route('/')
def index():
    products_with_prices = db.session.query(Product).outerjoin(PriceHistory).filter(PriceHistory.end_date == None).all()
    return render_template('index.html', products=products_with_prices)

# ???
# @app.route('/about')
# def about():
#     return render_template('about.html')


@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash('Сначала войдите в систему для доступа к корзине.', 'danger')
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Получаем товары из корзины с актуальными ценами
    cart_items = db.session.execute(
        text("""
            SELECT p.title, p.product_id, ph.price 
            FROM cart AS ct 
            JOIN customers AS c ON ct.customer_id = c.customer_id 
            JOIN products AS p ON ct.product_id = p.product_id 
            LEFT JOIN price_history AS ph ON p.product_id = ph.product_id 
            WHERE c.customer_id = :customer_id AND ph.end_date IS NULL
        """),
        {'customer_id': user_id}
    ).fetchall()

    # Преобразуем данные в список словарей и рассчитываем итоговую стоимость
    cart_items_list = []
    total_price = Decimal(0)  # Инициализируем как Decimal
    for title, product_id, price in cart_items:
        cart_items_list.append({
            'title': title,
            'product_id': product_id,  # Добавляем product_id
            'price': price
        })
        total_price += price if price is not None else Decimal(0)  # Суммируем с проверкой на None

    return render_template('cart.html', cart_items=cart_items_list, total_price=total_price)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    current_price = db.session.query(PriceHistory.price).filter(
        PriceHistory.product_id == product_id,
        PriceHistory.end_date == None
    ).scalar()

    return render_template('product.html', product=product, current_price=current_price)


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    customer_id = request.form['customer_id']
    password = request.form['password']

    # Ищем пользователя по customer_id
    user = Customer.query.filter_by(customer_id=customer_id).first()

    if user:
        # Проверяем пароль из таблицы UserCredentials
        credentials = UserCredentials.query.filter_by(customer_id=customer_id).first()
        if credentials and credentials.password == password:  # временно отключено хэширование
            # Сохранение customer_id в сессии
            session['user_id'] = user.customer_id
            flash('Успешный вход! Вы будете перенаправлены на страницу профиля через 3 секунды.', 'success')
            return redirect(url_for('login_page', success=True))  # Переходим с параметром для отображения успешного входа

    flash('Неверный ID или пароль', 'danger')
    return redirect(url_for('login_page'))  # При неудаче возвращаемся на страницу входа


@app.route('/registration', methods=['GET', 'POST'])
def registration_page():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']

        errors = []

        if not re.match(r"^[А-ЯЁ][а-яё]*$", first_name):
            errors.append("Имя должно содержать только буквы и начинаться с заглавной буквы.")
        if not re.match(r"^[А-ЯЁ][а-яё]*$", last_name):
            errors.append("Фамилия должна содержать только буквы и начинаться с заглавной буквы.")
        if not re.match(r"^8 \(\d{3}\) \d{3}-\d{2}-\d{2}$", phone):
            errors.append("Телефон должен быть в формате 8 (926) 791-48-54.")
        if Customer.query.filter_by(email=email).first():
            errors.append("Пользователь с таким email уже существует.")

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('registration.html', first_name=first_name, last_name=last_name, phone=phone, email=email)

        # Создание нового пользователя
        new_user = Customer(
            fname=first_name,
            sname=last_name,
            phone=phone,
            email=email
        )
        db.session.add(new_user)
        db.session.commit()

        # Добавление учетных данных
        new_credentials = UserCredentials(
            customer_id=new_user.customer_id,
            password=password
        )
        db.session.add(new_credentials)
        db.session.commit()

        flash(f'Регистрация успешна! Ваш ID: {new_user.customer_id}. Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('registration.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Удаляем user_id из сессии
    flash('Вы вышли из системы.', 'success')
    return redirect(url_for('login_page'))


@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Сначала войдите в систему, чтобы добавить товар в корзину.', 'warning')
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Проверяем, существует ли уже товар в корзине пользователя
    existing_item = db.session.execute(
        text("SELECT * FROM cart WHERE customer_id = :customer_id AND product_id = :product_id"),
        {'customer_id': user_id, 'product_id': product_id}
    ).fetchone()

    if existing_item:
        flash('Этот товар уже добавлен в вашу корзину. Вы не можете добавить товар повторно!', 'danger')
    else:
        # Добавляем товар в корзину
        db.session.execute(
            text("INSERT INTO cart (customer_id, product_id) VALUES (:customer_id, :product_id)"),
            {'customer_id': user_id, 'product_id': product_id}
        )
        db.session.commit()
        flash('Товар успешно добавлен в корзину!', 'success')

    return redirect(url_for('product_detail', product_id=product_id))  # Исправленный маршрут


@app.route('/add_to_cart_inline/<int:product_id>', methods=['POST'])
def add_to_cart_inline(product_id):
    if 'user_id' not in session:
        flash('Сначала войдите в систему, чтобы добавить товар в корзину.', 'warning')
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    existing_item = db.session.execute(
        text("SELECT * FROM cart WHERE customer_id = :customer_id AND product_id = :product_id"),
        {'customer_id': user_id, 'product_id': product_id}
    ).fetchone()

    if existing_item:
        flash('Этот товар уже добавлен в вашу корзину! Вы не можете добавить товар повторно!', 'danger')
    else:
        db.session.execute(
            text("INSERT INTO cart (customer_id, product_id) VALUES (:customer_id, :product_id)"),
            {'customer_id': user_id, 'product_id': product_id}
        )
        db.session.commit()
        flash('Товар успешно добавлен в корзину!', 'success')

    return redirect(url_for('index'))  # Остаемся на странице каталога


@app.route('/remove_from_cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'user_id' not in session:
        flash('Сначала войдите в систему, чтобы удалить товар из корзины.', 'warning')
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Удаляем товар из корзины
    db.session.execute(
        text("DELETE FROM cart WHERE customer_id = :customer_id AND product_id = :product_id"),
        {'customer_id': user_id, 'product_id': product_id}
    )
    db.session.commit()

    flash('Товар успешно удалён из корзины!', 'success')
    return redirect(url_for('cart'))  # Перенаправляем на страницу корзины


@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        flash('Сначала войдите в систему, чтобы оформить заказ.', 'danger')
        return redirect(url_for('login_page'))

    user_id = session['user_id']

    # Получаем товары из корзины с актуальными ценами
    cart_items = db.session.execute(
        text("""
            SELECT p.product_id, ph.price 
            FROM cart AS ct 
            JOIN products AS p ON ct.product_id = p.product_id 
            LEFT JOIN price_history AS ph ON p.product_id = ph.product_id 
            WHERE ct.customer_id = :customer_id AND ph.end_date IS NULL
        """),
        {'customer_id': user_id}
    ).fetchall()

    # Рассчитываем итоговую стоимость
    total_price = sum(item.price for item in cart_items if item.price)

    # Создаем новую запись в таблице orders
    new_order = db.session.execute(
        text("""
            INSERT INTO orders (customer_id, order_date, total_price)
            VALUES (:customer_id, :order_date, :total_price)
            RETURNING order_id
        """),
        {'customer_id': user_id, 'order_date': datetime.utcnow(), 'total_price': total_price}
    ).fetchone()
    order_id = new_order.order_id

    # Добавляем записи в таблицу order_product для каждого товара
    for item in cart_items:
        db.session.execute(
            text("""
                INSERT INTO order_product (order_id, product_id, unit_price)
                VALUES (:order_id, :product_id, :unit_price)
            """),
            {'order_id': order_id, 'product_id': item.product_id, 'unit_price': item.price}
        )

    # Очищаем корзину после оформления заказа
    db.session.execute(
        text("DELETE FROM cart WHERE customer_id = :customer_id"),
        {'customer_id': user_id}
    )

    db.session.commit()
    flash('Заказ успешно оформлен! Данные заказа можете посмотреть в Личном кабинете.', 'success')
    return redirect(url_for('cart'))


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Сначала войдите в систему.', 'warning')
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    orders = db.session.execute(
        text("""
            SELECT order_id, order_date, total_price 
            FROM orders 
            WHERE customer_id = :customer_id
            ORDER BY order_date DESC
        """),
        {'customer_id': user_id}
    ).fetchall()

    return render_template('profile.html', orders=orders)


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
