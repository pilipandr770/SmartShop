"""
Моделі складу та логістики
"""
from datetime import datetime
from enum import Enum
from extensions import db


class ShipmentStatus(str, Enum):
    """Статуси відправки."""
    PENDING = "pending"              # Очікує обробки
    PROCESSING = "processing"        # В обробці (комплектування)
    PACKED = "packed"                # Запаковано
    READY = "ready"                  # Готово до відправки
    SHIPPED = "shipped"              # Відправлено
    IN_TRANSIT = "in_transit"        # В дорозі
    DELIVERED = "delivered"          # Доставлено
    RETURNED = "returned"            # Повернено
    CANCELLED = "cancelled"          # Скасовано


class ReplenishmentStatus(str, Enum):
    """Статуси поповнення."""
    DRAFT = "draft"                  # Чернетка
    PENDING = "pending"              # Очікує підтвердження
    APPROVED = "approved"            # Підтверджено
    ORDERED = "ordered"              # Замовлено у постачальника
    SHIPPED = "shipped"              # Відправлено постачальником
    RECEIVED = "received"            # Отримано
    CANCELLED = "cancelled"          # Скасовано


class ExpenseCategory(str, Enum):
    """Категорії витрат."""
    SHIPPING = "shipping"            # Доставка
    PACKAGING = "packaging"          # Пакування
    WAREHOUSE = "warehouse"          # Складські витрати
    RETURN = "return"                # Повернення
    OTHER = "other"                  # Інше


class WarehouseTask(db.Model):
    """Завдання для складу (на відправку посилки)."""
    __tablename__ = "warehouse_tasks"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    # Зв'язок з замовленням
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    
    # Номер завдання
    task_number = db.Column(db.String(50), unique=True, nullable=True)  # WH-2025-0001
    
    # Статус
    status = db.Column(db.String(20), default=ShipmentStatus.PENDING.value)
    
    # Пріоритет (1-5, 1 = найвищий)
    priority = db.Column(db.Integer, default=3)
    
    # Інформація про клієнта (копія з замовлення)
    customer_name = db.Column(db.String(200), nullable=True)
    customer_phone = db.Column(db.String(50), nullable=True)
    customer_email = db.Column(db.String(200), nullable=True)
    shipping_address = db.Column(db.Text, nullable=True)
    shipping_method = db.Column(db.String(100), nullable=True)
    is_b2b = db.Column(db.Boolean, default=False)
    
    # Коментарі
    notes = db.Column(db.Text, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    
    # Призначення
    assigned_to = db.Column(db.String(100), nullable=True)  # Працівник складу
    
    # Трекінг
    tracking_number = db.Column(db.String(100), nullable=True)
    carrier = db.Column(db.String(50), nullable=True)  # nova_poshta, ukrposhta, etc.
    label_url = db.Column(db.String(1000), nullable=True)  # посилання на лейбл (DHL/UPS API)
    
    # Вага та розміри
    weight_kg = db.Column(db.Float, nullable=True)
    dimensions = db.Column(db.String(50), nullable=True)  # 30x20x15 см
    
    # Вартість доставки
    shipping_cost = db.Column(db.Float, default=0.0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    packed_at = db.Column(db.DateTime, nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    
    # Зв'язки
    order = db.relationship("Order", backref="warehouse_task", uselist=False)
    
    def __repr__(self):
        return f"<WarehouseTask #{self.id} for Order #{self.order_id}>"
    
    @property
    def status_display(self):
        """Людський статус."""
        statuses = {
            "pending": "⏳ Очікує обробки",
            "processing": "🔄 Комплектування",
            "packed": "📦 Запаковано",
            "ready": "✅ Готово до відправки",
            "shipped": "🚚 Відправлено",
            "in_transit": "🛤️ В дорозі",
            "delivered": "✔️ Доставлено",
            "returned": "↩️ Повернено",
            "cancelled": "❌ Скасовано",
        }
        return statuses.get(self.status, self.status)
    
    @property
    def priority_display(self):
        """Пріоритет текстом."""
        priorities = {
            1: "🔴 Терміново",
            2: "🟠 Високий",
            3: "🟡 Звичайний",
            4: "🟢 Низький",
            5: "⚪ Найнижчий",
        }
        return priorities.get(self.priority, "🟡 Звичайний")
    
    def generate_task_number(self):
        """Генерує номер завдання."""
        year = datetime.utcnow().year
        self.task_number = f"WH-{year}-{self.id:05d}"
        db.session.commit()
    
    def mark_packed(self, weight_kg=None, dimensions=None):
        """Позначити як запаковано."""
        self.status = ShipmentStatus.PACKED.value
        self.packed_at = datetime.utcnow()
        if weight_kg:
            self.weight_kg = weight_kg
        if dimensions:
            self.dimensions = dimensions
        db.session.commit()
    
    def mark_shipped(self, tracking_number=None, carrier=None):
        """Позначити як відправлено."""
        self.status = ShipmentStatus.SHIPPED.value
        self.shipped_at = datetime.utcnow()
        if tracking_number:
            self.tracking_number = tracking_number
        if carrier:
            self.carrier = carrier
        
        # Оновлюємо замовлення
        if self.order:
            self.order.status = "shipped"
            self.order.shipped_at = datetime.utcnow()
            self.order.tracking_number = tracking_number
        
        db.session.commit()
    
    def mark_delivered(self):
        """Позначити як доставлено."""
        self.status = ShipmentStatus.DELIVERED.value
        self.delivered_at = datetime.utcnow()
        
        if self.order:
            self.order.status = "delivered"
            self.order.delivered_at = datetime.utcnow()
        
        db.session.commit()
    
    @staticmethod
    def create_from_order(order_id, priority=3, notes=None):
        """Створює завдання для замовлення. store_id береться із самого замовлення."""
        from models.order import Order

        order = Order.query.get(order_id)
        if not order:
            raise ValueError(f"Order #{order_id} not found")

        task = WarehouseTask(
            store_id=order.store_id,
            order_id=order_id,
            priority=priority,
            notes=notes,
            # Копіюємо дані з замовлення
            customer_name=getattr(order, 'customer_name', None) or getattr(order, 'name', None),
            customer_phone=getattr(order, 'customer_phone', None) or getattr(order, 'phone', None),
            customer_email=getattr(order, 'customer_email', None) or getattr(order, 'email', None),
            shipping_address=getattr(order, 'shipping_address', None) or getattr(order, 'address', None),
            shipping_method=getattr(order, 'shipping_method', None),
            is_b2b=getattr(order, 'is_b2b', False),
        )
        db.session.add(task)
        db.session.flush()
        task.generate_task_number()
        db.session.commit()
        return task


class StockMovement(db.Model):
    """Рух товарів на складі."""
    __tablename__ = "stock_movements"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    # Товар
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    
    # Тип руху
    movement_type = db.Column(db.String(20), nullable=False)  # in, out, adjustment, return
    
    # Кількість (додатня для надходження, від'ємна для витрати)
    quantity = db.Column(db.Integer, nullable=False)
    
    # Залишок після операції
    stock_after = db.Column(db.Integer, nullable=False)
    
    # Причина/джерело
    reason = db.Column(db.String(100), nullable=True)  # order, replenishment, adjustment, return
    reference_id = db.Column(db.Integer, nullable=True)  # ID замовлення, поповнення тощо
    
    # Коментар
    notes = db.Column(db.Text, nullable=True)
    
    # Хто виконав
    performed_by = db.Column(db.String(100), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    product = db.relationship("Product", backref="stock_movements")
    
    def __repr__(self):
        return f"<StockMovement {self.movement_type} {self.quantity} for Product #{self.product_id}>"
    
    @staticmethod
    def record_movement(product_id, quantity, movement_type, reason=None, reference_id=None,
                         notes=None, performed_by=None, store_id=None):
        """
        Записує рух товару. store_id на новому записі береться з товару.
        Якщо store_id переданий явно - товар шукається ТІЛЬКИ в межах цього
        магазину (захист від зміни залишків чужого товару за підібраним ID).
        """
        from models.product import Product
        if store_id is not None:
            product = Product.query.filter_by(id=product_id, store_id=store_id).first()
        else:
            product = Product.query.get(product_id)
        if not product:
            raise ValueError(f"Product #{product_id} not found")

        # Оновлюємо залишок
        new_stock = product.stock + quantity
        if new_stock < 0:
            raise ValueError(f"Недостатньо товару на складі. Залишок: {product.stock}, потрібно: {abs(quantity)}")

        product.stock = new_stock

        # Записуємо рух
        movement = StockMovement(
            store_id=product.store_id,
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            stock_after=new_stock,
            reason=reason,
            reference_id=reference_id,
            notes=notes,
            performed_by=performed_by,
        )
        db.session.add(movement)
        db.session.commit()
        return movement


class ReplenishmentOrder(db.Model):
    """Замовлення на поповнення складу."""
    __tablename__ = "replenishment_orders"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    # Номер замовлення
    order_number = db.Column(db.String(50), unique=True, nullable=True)  # REP-2025-0001
    
    # Постачальник
    supplier_name = db.Column(db.String(255), nullable=True)
    supplier_contact = db.Column(db.String(255), nullable=True)
    
    # Статус
    status = db.Column(db.String(20), default=ReplenishmentStatus.DRAFT.value)
    
    # Суми
    subtotal = db.Column(db.Float, default=0.0)
    shipping_cost = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(8), default="UAH")
    
    # Оплата
    is_paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    
    # Нотатки
    notes = db.Column(db.Text, nullable=True)
    
    # Хто створив
    created_by = db.Column(db.String(100), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ordered_at = db.Column(db.DateTime, nullable=True)
    expected_at = db.Column(db.DateTime, nullable=True)  # Очікувана дата доставки
    received_at = db.Column(db.DateTime, nullable=True)
    
    # Зв'язки
    items = db.relationship("ReplenishmentItem", backref="replenishment_order", lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ReplenishmentOrder #{self.id}>"
    
    @property
    def status_display(self):
        """Людський статус."""
        statuses = {
            "draft": "📝 Чернетка",
            "pending": "⏳ Очікує підтвердження",
            "approved": "✅ Підтверджено",
            "ordered": "📤 Замовлено",
            "shipped": "🚚 Відправлено",
            "received": "✔️ Отримано",
            "cancelled": "❌ Скасовано",
        }
        return statuses.get(self.status, self.status)
    
    def generate_order_number(self):
        """Генерує номер замовлення."""
        year = datetime.utcnow().year
        self.order_number = f"REP-{year}-{self.id:05d}"
        db.session.commit()
    
    def calculate_totals(self):
        """Перераховує суми."""
        self.subtotal = sum(item.total for item in self.items)
        self.total = self.subtotal + self.shipping_cost
        db.session.commit()
    
    def mark_received(self):
        """Позначає як отримано та оновлює залишки."""
        self.status = ReplenishmentStatus.RECEIVED.value
        self.received_at = datetime.utcnow()
        
        # Оновлюємо залишки товарів
        for item in self.items:
            StockMovement.record_movement(
                product_id=item.product_id,
                quantity=item.quantity,
                movement_type="in",
                reason="replenishment",
                reference_id=self.id,
                notes=f"Поповнення #{self.order_number}",
                store_id=self.store_id,
            )
        
        db.session.commit()


class ReplenishmentItem(db.Model):
    """Позиція замовлення на поповнення."""
    __tablename__ = "replenishment_items"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    replenishment_id = db.Column(db.Integer, db.ForeignKey("replenishment_orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    
    # Дані товару на момент замовлення
    product_name = db.Column(db.String(200), nullable=False)
    product_sku = db.Column(db.String(64), nullable=True)
    
    # Кількість та ціни
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)  # Закупівельна ціна
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    product = db.relationship("Product")
    
    def __repr__(self):
        return f"<ReplenishmentItem {self.product_name} x{self.quantity}>"
    
    @property
    def total(self):
        """Сума позиції."""
        return self.unit_price * self.quantity


class WarehouseExpense(db.Model):
    """Витрати складу."""
    __tablename__ = "warehouse_expenses"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    # Категорія
    category = db.Column(db.String(50), nullable=False, default=ExpenseCategory.OTHER.value)
    
    # Опис
    description = db.Column(db.String(255), nullable=False)
    
    # Сума
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), default="UAH")
    
    # Зв'язки з іншими сутностями
    warehouse_task_id = db.Column(db.Integer, db.ForeignKey("warehouse_tasks.id"), nullable=True)
    replenishment_id = db.Column(db.Integer, db.ForeignKey("replenishment_orders.id"), nullable=True)
    
    # Документ/чек
    receipt_number = db.Column(db.String(100), nullable=True)
    receipt_url = db.Column(db.String(500), nullable=True)
    
    # Хто додав
    created_by = db.Column(db.String(100), nullable=True)
    
    # Дата витрати
    expense_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<WarehouseExpense {self.category}: {self.amount} {self.currency}>"
    
    @property
    def category_display(self):
        """Категорія текстом."""
        categories = {
            "shipping": "🚚 Доставка",
            "packaging": "📦 Пакування",
            "warehouse": "🏭 Складські",
            "return": "↩️ Повернення",
            "other": "📋 Інше",
        }
        return categories.get(self.category, self.category)


class LowStockAlert(db.Model):
    """Алерти про низький залишок товарів."""
    __tablename__ = "low_stock_alerts"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    
    # Залишок на момент алерту
    current_stock = db.Column(db.Integer, nullable=False)
    min_stock = db.Column(db.Integer, nullable=False)
    
    # Статус
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.String(100), nullable=True)
    
    # Зв'язок з поповненням
    replenishment_id = db.Column(db.Integer, db.ForeignKey("replenishment_orders.id"), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    product = db.relationship("Product", backref="low_stock_alerts")
    
    def __repr__(self):
        return f"<LowStockAlert Product #{self.product_id}: {self.current_stock}/{self.min_stock}>"
    
    @staticmethod
    def check_and_create_alerts(store_id=None):
        """Перевіряє товари (в межах магазину, якщо задано) та створює алерти для низьких залишків."""
        from models.product import Product

        alerts_created = 0
        query = Product.query.filter(
            Product.stock <= Product.min_stock,
            Product.min_stock > 0,
            Product.is_active == True
        )
        if store_id is not None:
            query = query.filter(Product.store_id == store_id)
        products = query.all()

        for product in products:
            # Перевіряємо чи немає активного алерту
            existing = LowStockAlert.query.filter_by(
                product_id=product.id,
                is_resolved=False
            ).first()

            if not existing:
                alert = LowStockAlert(
                    store_id=product.store_id,
                    product_id=product.id,
                    current_stock=product.stock,
                    min_stock=product.min_stock,
                )
                db.session.add(alert)
                alerts_created += 1

        db.session.commit()
        return alerts_created
    
    def resolve(self, resolved_by=None, replenishment_id=None):
        """Закриває алерт."""
        self.is_resolved = True
        self.resolved_at = datetime.utcnow()
        self.resolved_by = resolved_by
        self.replenishment_id = replenishment_id
        db.session.commit()
