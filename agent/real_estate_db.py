"""
房产助理 - 数据库模块
Coco（可可）的底层数据存储
"""
import os
import json
import re
from datetime import datetime, timedelta
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Numeric, BigInteger,
    DateTime, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.types import TypeDecorator
from cryptography.fernet import Fernet

Base = declarative_base()

# ==================== 敏感字段加密 ====================

def _get_cipher():
    """获取 Fernet 加密器；未配置 COCO_ENC_KEY 时返回 None（明文模式，兼容旧数据）"""
    key = os.getenv('COCO_ENC_KEY', '')
    if not key:
        return None
    try:
        return Fernet(key.encode('utf-8'))
    except Exception:
        return None


class EncryptedString(TypeDecorator):
    """加密字符串类型：配置密钥时自动加密存储，读取时自动解密
    
    无密钥时以明文存取（兼容未加密的旧数据）；解密失败时返回原值（兼容历史明文）。
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        cipher = _get_cipher()
        if cipher is None:
            return value
        return cipher.encrypt(value.encode('utf-8')).decode('utf-8')

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        cipher = _get_cipher()
        if cipher is None:
            return value
        try:
            return cipher.decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value  # 旧明文数据原样返回

    def _coerce_compared_value(self, op, value):
        return Text()

# ==================== 数据模型 ====================

class Customer(Base):
    """客户表"""
    __tablename__ = 're_customers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone = Column(EncryptedString)
    wechat = Column(EncryptedString)
    feishu_id = Column(String(100))
    tier = Column(String(1), default='C')
    budget_min = Column(Integer)  # 预算下限（元，如 300万=3000000）
    budget_max = Column(Integer)  # 预算上限（元）
    area_pref = Column(String(50))
    layout_pref = Column(String(50))
    location = Column(String(200))
    renovation = Column(String(50))
    notes = Column(Text)
    tags = Column(Text)
    source = Column(String(100))
    customer_type = Column(String(20), default="buy")  # buy_new/buy_second_hand/rent
    birthday = Column(String(10))  # YYYY-MM-DD
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    followups = relationship("Followup", back_populates="customer")
    viewings = relationship("Viewing", back_populates="customer")
    deals = relationship("Deal", back_populates="customer")
    changes = relationship("CustomerChange", back_populates="customer")
    
    __table_args__ = (
        CheckConstraint("tier IN ('S', 'A', 'B', 'C')", name='re_check_tier'),
        Index('re_idx_customer_tier', 'tier'),
        Index('re_idx_customer_status', 'status'),
    )
    
    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'phone': self.phone,
            'wechat': self.wechat, 'feishu_id': self.feishu_id,
            'tier': self.tier, 'budget_min': self.budget_min,
            'budget_max': self.budget_max, 'area_pref': self.area_pref,
            'layout_pref': self.layout_pref, 'location': self.location,
            'renovation': self.renovation, 'notes': self.notes, 'tags': self.tags,
            'source': self.source, 'customer_type': self.customer_type, 'status': self.status,
            'birthday': self.birthday,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Property(Base):
    """房源表"""
    __tablename__ = 're_properties'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    community = Column(String(100))
    district = Column(String(100))
    address = Column(String(300))
    price = Column(BigInteger, nullable=False)  # 元（二手房总价如 4000000，出租月租如 1000）
    unit_price = Column(Integer)  # 元/㎡ = price/area
    area = Column(Float, nullable=False)
    rooms = Column(Integer)
    halls = Column(Integer)
    bathrooms = Column(Integer)
    floor = Column(String(50))
    orientation = Column(String(50))
    renovation = Column(String(50))
    year_built = Column(Integer)
    has_elevator = Column(Integer, default=1)
    property_type = Column(String(20), default="second_hand")  # new/second_hand/rental
    parking = Column(Integer, default=0)
    tags = Column(Text)
    images = Column(Text)
    status = Column(String(20), default='available')
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    followups = relationship("Followup", back_populates="property")
    viewings = relationship("Viewing", back_populates="property")
    deals = relationship("Deal", back_populates="property")
    
    __table_args__ = (
        CheckConstraint("status IN ('available', 'sold', 'rented')", name='re_check_prop_status'),
        Index('re_idx_prop_status', 'status'),
        Index('re_idx_prop_price', 'price'),
        Index('re_idx_prop_district', 'district'),
    )
    
    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'community': self.community,
            'district': self.district, 'address': self.address,
            # price 列是 Numeric(12,2)，读出为 Decimal，必须转 float 否则 json.dumps 崩溃
            'price': float(self.price) if self.price is not None else None,
            'unit_price': self.unit_price,
            'area': self.area, 'rooms': self.rooms, 'halls': self.halls,
            'bathrooms': self.bathrooms, 'floor': self.floor,
            'orientation': self.orientation, 'renovation': self.renovation,
            'year_built': self.year_built, 'has_elevator': self.has_elevator, 'property_type': self.property_type,
            'parking': self.parking, 'tags': self.tags, 'images': self.images,
            'status': self.status, 'agent_id': self.agent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Followup(Base):
    """跟进记录表"""
    __tablename__ = 're_followups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('re_customers.id'))
    property_id = Column(Integer, ForeignKey('re_properties.id'))
    type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    next_date = Column(DateTime)
    next_time = Column(String(10))
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    customer = relationship("Customer", back_populates="followups")
    property = relationship("Property", back_populates="followups")
    
    __table_args__ = (
        Index('re_idx_followup_customer', 'customer_id'),
        Index('re_idx_followup_next_date', 'next_date'),
    )
    
    def to_dict(self):
        return {
            'id': self.id, 'customer_id': self.customer_id,
            'property_id': self.property_id, 'type': self.type,
            'content': self.content,
            'next_date': self.next_date.isoformat() if self.next_date else None,
            'next_time': self.next_time, 'agent_id': self.agent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Reminder(Base):
    """提醒任务表"""
    __tablename__ = 're_reminders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    cron_expr = Column(String(100))
    target_chat = Column(String(100))
    content = Column(Text)
    enabled = Column(Integer, default=1)
    last_run = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('re_idx_reminder_type', 'type'),
        Index('re_idx_reminder_enabled', 'enabled'),
    )


class Viewing(Base):
    """带看记录表"""
    __tablename__ = 're_viewings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('re_customers.id'), nullable=False)
    property_id = Column(Integer, ForeignKey('re_properties.id'), nullable=False)
    viewing_time = Column(DateTime, nullable=False)       # 带看时间
    status = Column(String(20), default='scheduled')      # scheduled/done/cancelled
    feedback = Column(Text)                               # 客户反馈
    result = Column(String(20))                           # interested/not_interested/pending
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    customer = relationship("Customer", back_populates="viewings")
    property = relationship("Property", back_populates="viewings")
    
    __table_args__ = (
        Index('re_idx_viewing_customer', 'customer_id'),
        Index('re_idx_viewing_property', 'property_id'),
        Index('re_idx_viewing_time', 'viewing_time'),
    )
    
    def to_dict(self):
        return {
            'id': self.id, 'customer_id': self.customer_id,
            'property_id': self.property_id,
            'viewing_time': self.viewing_time.isoformat() if self.viewing_time else None,
            'status': self.status, 'feedback': self.feedback,
            'result': self.result, 'agent_id': self.agent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'customer_name': self.customer.name if self.customer else None,
            'property_title': self.property.title if self.property else None,
        }


class Deal(Base):
    """成交/交易状态表"""
    __tablename__ = 're_deals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('re_customers.id'), nullable=False)
    property_id = Column(Integer, ForeignKey('re_properties.id'), nullable=False)
    stage = Column(String(20), default='deposit')  # deposit/signing/loan/transfer/finalized
    price = Column(Integer)                         # 成交价（元，如 400万=4000000）
    deposit_amount = Column(Integer)                # 定金（元）
    deposit_date = Column(DateTime)                 # 定金日期
    signing_date = Column(DateTime)                 # 签约日期
    loan_date = Column(DateTime)                    # 贷款审批日期
    transfer_date = Column(DateTime)                # 过户日期
    finalize_date = Column(DateTime)                # 交房日期
    notes = Column(Text)
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    customer = relationship("Customer", back_populates="deals")
    property = relationship("Property", back_populates="deals")
    
    __table_args__ = (
        CheckConstraint("stage IN ('deposit', 'signing', 'loan', 'transfer', 'finalized')", name='re_check_deal_stage'),
        Index('re_idx_deal_customer', 'customer_id'),
        Index('re_idx_deal_stage', 'stage'),
    )
    
    def to_dict(self):
        return {
            'id': self.id, 'customer_id': self.customer_id,
            'property_id': self.property_id, 'stage': self.stage,
            'price': self.price, 'deposit_amount': self.deposit_amount,
            'deposit_date': self.deposit_date.isoformat() if self.deposit_date else None,
            'signing_date': self.signing_date.isoformat() if self.signing_date else None,
            'loan_date': self.loan_date.isoformat() if self.loan_date else None,
            'transfer_date': self.transfer_date.isoformat() if self.transfer_date else None,
            'finalize_date': self.finalize_date.isoformat() if self.finalize_date else None,
            'notes': self.notes, 'agent_id': self.agent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'customer_name': self.customer.name if self.customer else None,
            'property_title': self.property.title if self.property else None,
        }


class Script(Base):
    """自定义话术表"""
    __tablename__ = 're_scripts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)       # 话术名称
    scenario = Column(String(50), default='custom')  # greeting/objection_handling/closing/follow_up/custom
    content = Column(Text, nullable=False)           # 话术内容
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('re_idx_script_scenario', 'scenario'),
        Index('re_idx_script_name', 'name'),
    )


class CustomerChange(Base):
    """客户需求变更历史表（预算/区域/户型等字段变更留痕）"""
    __tablename__ = 're_customer_changes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey('re_customers.id'), nullable=False)
    field = Column(String(50), nullable=False)   # 变更字段：budget_min/budget_max/location/tier...
    old_value = Column(String(200))
    new_value = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)

    customer = relationship("Customer", back_populates="changes")

    __table_args__ = (
        Index('re_idx_change_customer', 'customer_id'),
    )

    def to_dict(self):
        return {
            'id': self.id, 'customer_id': self.customer_id,
            'field': self.field, 'old_value': self.old_value,
            'new_value': self.new_value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== 数据库管理 ====================

class RealEstateDB:
    """Coco 的数据库"""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        return self.SessionLocal()
    
    # ---------- 客户 ----------
    def add_customer(self, **kwargs):
        with self.get_session() as s:
            c = Customer(**kwargs)
            s.add(c); s.commit(); s.refresh(c)
            return c.to_dict()
    
    def update_customer(self, cid, **kwargs):
        with self.get_session() as s:
            c = s.query(Customer).get(cid)
            if not c: return None
            for k, v in kwargs.items():
                if hasattr(c, k):
                    old = getattr(c, k)
                    if old != v:
                        s.add(CustomerChange(
                            customer_id=cid, field=k,
                            old_value=str(old) if old is not None else None,
                            new_value=str(v) if v is not None else None,
                        ))
                    setattr(c, k, v)
            s.commit(); s.refresh(c)
            return c.to_dict()
    
    def get_customer_changes(self, customer_id, limit=20):
        """查询客户需求变更历史（预算/区域/户型等）"""
        with self.get_session() as s:
            return [ch.to_dict() for ch in s.query(CustomerChange)
                .filter(CustomerChange.customer_id == customer_id)
                .order_by(CustomerChange.created_at.desc(), CustomerChange.id.desc())
                .limit(limit).all()]
    
    def get_customer(self, cid):
        with self.get_session() as s:
            c = s.query(Customer).get(cid)
            return c.to_dict() if c else None
    
    def list_customers(self, tier=None, status=None, customer_type=None, limit=50):
        with self.get_session() as s:
            q = s.query(Customer)
            if tier: q = q.filter(Customer.tier == tier)
            if status: q = q.filter(Customer.status == status)
            if customer_type: q = q.filter(Customer.customer_type == customer_type)
            return [c.to_dict() for c in q.limit(limit).all()]

    def get_birthday_customers(self, month=None, day=None):
        """查询指定月/日过生日的客户（用于生日提醒）"""
        with self.get_session() as s:
            q = s.query(Customer).filter(Customer.birthday.isnot(None), Customer.status == 'active')
            customers = [c.to_dict() for c in q.all()]
            if month is None and day is None:
                return customers
            result = []
            for c in customers:
                b = c.get('birthday') or ''
                parts = b.split('-')
                if len(parts) == 3:
                    try:
                        if month is None or int(parts[1]) == month:
                            if day is None or int(parts[2]) == day:
                                result.append(c)
                    except ValueError:
                        continue
            return result
    
    # ---------- 房源 ----------
    def add_property(self, **kwargs):
        with self.get_session() as s:
            p = Property(**kwargs)
            s.add(p); s.commit(); s.refresh(p)
            return p.to_dict()

    def update_property(self, pid, **kwargs):
        with self.get_session() as s:
            p = s.query(Property).get(pid)
            if not p: return None
            for k, v in kwargs.items():
                if hasattr(p, k): setattr(p, k, v)
            s.commit(); s.refresh(p)
            return p.to_dict()

    def find_duplicate_properties(self):
        """按 标题+面积+价格 找重复房源组（含Excel批量导入产生的完全重复项）
        
        返回 [[keep_id, dup_id, ...], ...]，每组按 id 升序，第一个为保留项。
        """
        with self.get_session() as s:
            props = s.query(Property).all()
            groups = {}
            for p in props:
                key = (p.title or '', round(p.area or 0, 2), float(p.price or 0))
                groups.setdefault(key, []).append(p.id)
            return [sorted(v) for v in groups.values() if len(v) > 1]

    def remove_duplicate_properties(self, dry_run=True):
        """去重：每组保留最早 id，删除其余（有关联记录则跳过，保守处理）
        
        dry_run=True 只统计不删除；返回 removable 列表供确认。
        """
        dups = self.find_duplicate_properties()
        removed, skipped = [], []
        with self.get_session() as s:
            for group in dups:
                keep_id = group[0]
                for dup_id in group[1:]:
                    rel = (s.query(Deal).filter(Deal.property_id == dup_id).count()
                           + s.query(Followup).filter(Followup.property_id == dup_id).count()
                           + s.query(Viewing).filter(Viewing.property_id == dup_id).count())
                    if rel > 0:
                        skipped.append({'id': dup_id, 'reason': '有关联带看/成交/跟进记录'})
                        continue
                    if not dry_run:
                        p = s.query(Property).get(dup_id)
                        if p: s.delete(p)
                    removed.append(dup_id)
            if not dry_run:
                s.commit()
        return {
            'duplicate_groups': len(dups),
            'duplicate_total': sum(len(g) - 1 for g in dups),
            'removable': removed, 'skipped': skipped,
            'dry_run': dry_run,
        }

    def match_customers_for_property(self, property_id, top_n=5):
        """房源反匹配：新房源 → 扫描 S/A 级客户，按需求匹配推荐

        返回命中客户列表（按匹配度排序），用于 add_property 后主动推送。
        """
        with self.get_session() as s:
            prop = s.query(Property).get(property_id)
            if not prop:
                return []
            # 只匹配在售房源
            if prop.status != 'available':
                return []
            candidates = s.query(Customer).filter(
                Customer.status == 'active',
                Customer.tier.in_(['S', 'A']),
            ).all()
            if not candidates:
                return []
            # 排除已有交易记录的客户（进行中或已完成，不再推新房源）
            candidates = [c for c in candidates if not c.deals]
            if not candidates:
                return []

            results = []
            for c in candidates:
                # 户型硬性要求：客户明确 N 室/N 厅而房源不满足 → 跳过
                #（与 match_property 对称，防止"2 室房源推给要 3 室的客户"）
                if c.layout_pref and not self._match_layout(c.layout_pref, prop.rooms, prop.halls):
                    continue
                score = 0
                reasons = []

                # 预算匹配（权重 30）
                budget_min = c.budget_min or 0
                budget_max = c.budget_max or 999999999  # 无预算上限（元制）
                if budget_min <= prop.price <= budget_max:
                    score += 30
                    reasons.append("预算匹配")
                elif prop.price < budget_min:
                    score += 15
                    reasons.append("略低于预算")
                elif prop.price > budget_max:
                    score += 5
                    reasons.append("略超预算")

                # 户型匹配（权重 25）
                pref = c.layout_pref or ""
                import re as _re
                m_room = _re.search(r'(\d+)室', pref)
                if m_room and prop.rooms == int(m_room.group(1)):
                    score += 25
                    reasons.append("户型匹配")

                # 面积匹配（权重 20）
                if c.area_pref:
                    lo, hi = self._parse_area(c.area_pref)
                    if lo <= prop.area <= hi:
                        score += 20
                        reasons.append("面积匹配")

                # 区域匹配（权重 15）
                if c.location and prop.district and c.location in prop.district:
                    score += 15
                    reasons.append("区域匹配")
                elif c.location and prop.community and c.location in prop.community:
                    score += 15
                    reasons.append("小区匹配")

                # 装修匹配（权重 10）
                if c.renovation and prop.renovation and c.renovation == prop.renovation:
                    score += 10
                    reasons.append("装修匹配")

                if score >= 40:
                    results.append({
                        'customer_id': c.id, 'customer_name': c.name,
                        'tier': c.tier, 'score': score, 'match_reasons': reasons,
                        'budget': [budget_min, budget_max],
                        'area_pref': c.area_pref, 'layout_pref': c.layout_pref,
                        'location': c.location,
                    })

            results.sort(key=lambda x: x['score'], reverse=True)
            return results[:top_n]

    def search_properties(self, **filters):
        with self.get_session() as s:
            q = s.query(Property).filter(Property.status == 'available')
            limit = filters.pop('limit', 50)
            if 'min_price' in filters: q = q.filter(Property.price >= filters['min_price'])
            if 'max_price' in filters: q = q.filter(Property.price <= filters['max_price'])
            if 'min_area' in filters: q = q.filter(Property.area >= filters['min_area'])
            if 'max_area' in filters: q = q.filter(Property.area <= filters['max_area'])
            if 'rooms' in filters: q = q.filter(Property.rooms == filters['rooms'])
            if 'district' in filters: q = q.filter(Property.district.contains(filters['district']))
            if 'renovation' in filters: q = q.filter(Property.renovation == filters['renovation'])
            if 'property_type' in filters: q = q.filter(Property.property_type == filters['property_type'])
            return [p.to_dict() for p in q.limit(limit).all()]
    
    def customer_has_deal(self, customer_id) -> bool:
        """客户是否已有交易记录（进行中或已完成）"""
        with self.get_session() as s:
            return s.query(Deal).filter(Deal.customer_id == customer_id).first() is not None

    def match_property(self, customer_id, top_n=5):
        customer = self.get_customer(customer_id)
        if not customer: return []
        # 已有交易记录（进行中或已完成）的客户不再推送房源
        # （真实案例 2026-08-11：客户过户完成仍被推荐房源）
        if self.customer_has_deal(customer_id):
            return []
        
        properties = self.search_properties()
        if not properties: return []
        
        min_area, max_area = self._parse_area(customer.get('area_pref'))
        budget_min = customer.get('budget_min') or 0
        budget_max = customer.get('budget_max') or 999999999  # 无预算上限（元制）
        
        scores = []
        for prop in properties:
            score = 0; reasons = []
            
            price = prop.get('price', 0)
            if budget_min <= price <= budget_max:
                score += 30; reasons.append("价格匹配")
            elif price < budget_min * 1.1:
                score += 15; reasons.append("价格略高")
            
            area = prop.get('area', 0)
            if min_area <= area <= max_area:
                score += 20; reasons.append("面积匹配")
            
            # 户型硬性要求：客户明确 N 室/N 厅而房源不满足 → 直接排除
            #（真实案例 2026-08-11：客户要 3 室却被推 2 室房源并标"匹配度较高"）
            if customer.get('layout_pref') and not self._match_layout(customer.get('layout_pref'), prop.get('rooms'), prop.get('halls')):
                continue
            
            if self._match_layout(customer.get('layout_pref'), prop.get('rooms'), prop.get('halls')):
                score += 25; reasons.append("户型匹配")
            
            loc = customer.get('location')
            if loc and (loc in prop.get('district', '') or loc in prop.get('community', '')):
                score += 15; reasons.append("区域匹配")
            
            if customer.get('renovation') and customer.get('renovation') == prop.get('renovation'):
                score += 10; reasons.append("装修匹配")
            
            if score > 0:
                scores.append({**prop, 'score': score, 'match_reasons': reasons})
        
        scores.sort(key=lambda x: x['score'], reverse=True)
        return scores[:top_n]
    
    def _parse_area(self, area_pref):
        if not area_pref: return (0, 999999)
        m = re.search(r'(\d+)[\-\~到](\d+)', area_pref)
        if m: return (float(m.group(1)), float(m.group(2)))
        m = re.search(r'(\d+)', area_pref)
        if m:
            v = float(m.group(1))
            return (v * 0.9, v * 1.1)
        return (0, 999999)
    
    def _match_layout(self, layout_pref, rooms, halls):
        if not layout_pref: return True
        rm = re.search(r'(\d+)室', layout_pref)
        hm = re.search(r'(\d+)厅', layout_pref)
        if rm and rooms is not None and rooms != int(rm.group(1)): return False
        if hm and halls is not None and halls != int(hm.group(1)): return False
        return True
    
    # ---------- 跟进 ----------
    def add_followup(self, **kwargs):
        with self.get_session() as s:
            f = Followup(**kwargs)
            s.add(f); s.commit(); s.refresh(f)
            return f.to_dict()
    
    def get_followups(self, customer_id, limit=20):
        with self.get_session() as s:
            return [f.to_dict() for f in s.query(Followup)
                .filter(Followup.customer_id == customer_id)
                .order_by(Followup.created_at.desc()).limit(limit).all()]
    
    def get_overdue(self):
        with self.get_session() as s:
            return [f.to_dict() for f in s.query(Followup)
                .filter(Followup.next_date < datetime.now())
                .filter(Followup.next_date.isnot(None))
                .order_by(Followup.next_date).all()]
    
    def get_stale_customers(self):
        """流失预警：按最后互动时间计算超期客户
        
        S级>5天 / A级>10天 / B级>30天 / C级>60天 无互动 → 预警。
        最后互动时间 = 最后一条跟进记录时间；无跟进则取客户创建时间。
        """
        with self.get_session() as s:
            now = datetime.now()
            result = []
            for c in s.query(Customer).filter(Customer.status == 'active').all():
                last_fu = s.query(Followup).filter(Followup.customer_id == c.id) \
                    .order_by(Followup.created_at.desc()).first()
                last_time = last_fu.created_at if (last_fu and last_fu.created_at) else c.created_at
                if not last_time:
                    continue
                days = (now - last_time).days
                threshold = {'S': 5, 'A': 10, 'B': 30}.get(c.tier, 60)
                if days > threshold:
                    result.append({
                        'customer_id': c.id, 'name': c.name, 'tier': c.tier,
                        'days_inactive': days, 'threshold': threshold,
                        'last_contact': last_time.isoformat() if last_time else None,
                    })
            return result
    
    def auto_downgrade_stale_customers(self):
        """流失自动降级：S级超5天→A，A级超10天→B，B级超30天→C
        
        降级同时写入变更历史。返回降级明细和仍超期的客户数。
        """
        stale = self.get_stale_customers()
        downgrades = []
        with self.get_session() as s:
            for item in stale:
                c = s.query(Customer).get(item['customer_id'])
                if not c:
                    continue
                mapping = {'S': 'A', 'A': 'B', 'B': 'C'}
                new_tier = mapping.get(c.tier)
                if new_tier and c.tier != new_tier:
                    old = c.tier
                    c.tier = new_tier
                    s.add(CustomerChange(customer_id=c.id, field='tier',
                                         old_value=old, new_value=new_tier))
                    downgrades.append({
                        'customer_id': c.id, 'name': c.name,
                        'from': old, 'to': new_tier, 'days_inactive': item['days_inactive'],
                    })
            s.commit()
        return {'downgrades': downgrades, 'still_stale': len(stale) - len(downgrades)}
    
    # ---------- 统计 ----------
    def get_stats(self):
        with self.get_session() as s:
            total = s.query(Customer).count()
            tiers = {t: s.query(Customer).filter(Customer.tier == t).count() for t in ['S','A','B','C']}
            props = s.query(Property).filter(Property.status == 'available').count()
            overdue = len(self.get_overdue())
            return {
                'total_customers': total, 'tier_counts': tiers,
                'available_properties': props, 'overdue_followups': overdue,
            }
    
    def get_channel_stats(self):
        """渠道线索统计：按客户来源分组统计客户数、分级、成交数、成交率"""
        with self.get_session() as s:
            channels = {}
            for c in s.query(Customer).all():
                src = (c.source or '').strip() or '未填写'
                ch = channels.setdefault(src, {
                    'source': src, 'customers': 0,
                    'tiers': {'S': 0, 'A': 0, 'B': 0, 'C': 0}, 'deals': 0,
                })
                ch['customers'] += 1
                tier = c.tier or 'C'
                ch['tiers'][tier] = ch['tiers'].get(tier, 0) + 1
                if s.query(Deal).filter(Deal.customer_id == c.id).first():
                    ch['deals'] += 1
            result = sorted(channels.values(), key=lambda x: -x['customers'])
            for ch in result:
                ch['conversion_rate'] = round(ch['deals'] / ch['customers'] * 100, 1) if ch['customers'] else 0
            return result
    
    def daily_report(self):
        stats = self.get_stats()
        overdue = self.get_overdue()
        today = datetime.now().date()
        with self.get_session() as s:
            today_fu = s.query(Followup).join(Customer).filter(
                Followup.next_date >= datetime.combine(today, datetime.min.time()),
                Followup.next_date < datetime.combine(today + timedelta(days=1), datetime.min.time()),
            ).all()
        return {
            'date': today.isoformat(),
            'customer_stats': stats.get('tier_counts', {}),
            'total_customers': stats.get('total_customers', 0),
            'available_properties': stats.get('available_properties', 0),
            'overdue_count': len(overdue),
            'today_followups': len(today_fu),
            'today_tasks': [
                {'customer': f.customer.name if f.customer else '未知', 'time': f.next_time, 'content': f.content}
                for f in today_fu[:10]
            ],
        }
    
    def midday_check(self):
        stats = self.get_stats()
        overdue = self.get_overdue()
        return {
            'overdue_count': len(overdue),
            'overdue_customers': [
                {'customer_id': f.customer_id, 'content': f.content, 'next_date': f.next_date.isoformat() if f.next_date else None}
                for f in overdue[:5]
            ],
            'total_customers': stats.get('total_customers', 0),
            'available_properties': stats.get('available_properties', 0),
        }

    # ---------- 带看 ----------
    def add_viewing(self, customer_id, property_id, viewing_time, **kwargs):
        with self.get_session() as s:
            v = Viewing(customer_id=customer_id, property_id=property_id,
                        viewing_time=viewing_time, **kwargs)
            s.add(v); s.commit(); s.refresh(v)
            return v.to_dict()

    def update_viewing(self, vid, **kwargs):
        with self.get_session() as s:
            v = s.query(Viewing).get(vid)
            if not v: return None
            for k, val in kwargs.items():
                if hasattr(v, k): setattr(v, k, val)
            s.commit(); s.refresh(v)
            return v.to_dict()

    def get_viewing(self, vid):
        with self.get_session() as s:
            v = s.query(Viewing).get(vid)
            return v.to_dict() if v else None

    def list_viewings(self, customer_id=None, property_id=None, status=None, limit=50):
        with self.get_session() as s:
            q = s.query(Viewing)
            if customer_id: q = q.filter(Viewing.customer_id == customer_id)
            if property_id: q = q.filter(Viewing.property_id == property_id)
            if status: q = q.filter(Viewing.status == status)
            return [v.to_dict() for v in q.order_by(Viewing.viewing_time.desc()).limit(limit).all()]

    def viewing_stats(self, period='month'):
        """带看统计：总数、已看、取消、感兴趣客户"""
        with self.get_session() as s:
            total = s.query(Viewing).count()
            done = s.query(Viewing).filter(Viewing.status == 'done').count()
            scheduled = s.query(Viewing).filter(Viewing.status == 'scheduled').count()
            cancelled = s.query(Viewing).filter(Viewing.status == 'cancelled').count()
            interested = s.query(Viewing).filter(Viewing.status == 'done', Viewing.result == 'interested').count()
            return {
                'total_viewings': total, 'done': done, 'scheduled': scheduled,
                'cancelled': cancelled, 'interested': interested,
                'interest_rate': round(interested / done * 100, 1) if done else 0,
            }

    # ---------- 成交 ----------
    def add_deal(self, customer_id, property_id, **kwargs):
        with self.get_session() as s:
            d = Deal(customer_id=customer_id, property_id=property_id, **kwargs)
            s.add(d)
            # 成交后房源不再对外在售：二手房/新房 → sold，出租 → rented
            # （真实案例 2026-08-11：阳光花园过户完成仍显示在售 21 套）
            p = s.query(Property).get(property_id)
            if p and p.status == 'available':
                p.status = 'rented' if p.property_type == 'rental' else 'sold'
            s.commit(); s.refresh(d)
            return d.to_dict()

    def update_deal(self, did, **kwargs):
        with self.get_session() as s:
            d = s.query(Deal).get(did)
            if not d: return None
            for k, val in kwargs.items():
                if hasattr(d, k): setattr(d, k, val)
            s.commit(); s.refresh(d)
            return d.to_dict()

    def get_deal(self, did):
        with self.get_session() as s:
            d = s.query(Deal).get(did)
            return d.to_dict() if d else None

    def list_deals(self, stage=None, customer_id=None, limit=50):
        with self.get_session() as s:
            q = s.query(Deal)
            if stage: q = q.filter(Deal.stage == stage)
            if customer_id: q = q.filter(Deal.customer_id == customer_id)
            return [d.to_dict() for d in q.order_by(Deal.created_at.desc()).limit(limit).all()]

    def deal_stats(self):
        """成交统计：各阶段数量"""
        with self.get_session() as s:
            stages = {st: s.query(Deal).filter(Deal.stage == st).count()
                      for st in ['deposit', 'signing', 'loan', 'transfer', 'finalized']}
            return {
                'total_deals': sum(stages.values()),
                'stages': stages,
                'finalized': stages.get('finalized', 0),
            }

    # ---------- 竞品对比 ----------
    def compare_properties(self, property_id, limit=5):
        """同小区/同区域竞品对比：返回指定房源及周边在售房源对比"""
        with self.get_session() as s:
            target = s.query(Property).get(property_id)
            if not target:
                return None
            target_dict = target.to_dict()
            q = s.query(Property).filter(Property.status == 'available')
            if target.community:
                q = q.filter(Property.community == target.community, Property.id != property_id)
                same_community = [p.to_dict() for p in q.limit(limit).all()]
            else:
                same_community = []
            # 若同小区不足，补同区域
            if len(same_community) < 3 and target.district:
                q2 = s.query(Property).filter(
                    Property.status == 'available',
                    Property.district == target.district,
                    Property.id != property_id,
                )
                existing_ids = {p['id'] for p in same_community}
                for p in q2.limit(limit).all():
                    if p.id not in existing_ids:
                        same_community.append(p.to_dict())
                        existing_ids.add(p.id)
            # 计算均价
            all_available = [p.to_dict() for p in s.query(Property).filter(Property.status == 'available').all()]
            prices = [p['price'] for p in all_available if p.get('price')]
            avg_price = round(sum(prices) / len(prices)) if prices else None
            return {
                'target': target_dict,
                'competitors': same_community[:limit],
                'district_avg_price': avg_price,
                'target_unit_price': target_dict.get('unit_price'),
            }

    # ---------- 客户意向度评分 ----------
    def customer_intent_score(self, customer_id):
        """客户意向度评分（0-100）：
        - 等级基础分：S=40, A=25, B=15, C=5
        - 带看次数加分：每次 +15（上限 30）
        - 跟进活跃度加分：近 7 天有跟进 +15
        - 预算明确加分：预算上下限都有 +10
        """
        with self.get_session() as s:
            c = s.query(Customer).get(customer_id)
            if not c:
                return None
            score = {'S': 40, 'A': 25, 'B': 15, 'C': 5}.get(c.tier, 5)
            reasons = [f"等级{c.tier}基础分"]

            # 带看次数
            viewing_count = s.query(Viewing).filter(
                Viewing.customer_id == customer_id,
                Viewing.status == 'done',
            ).count()
            viewing_score = min(viewing_count * 15, 30)
            if viewing_score:
                score += viewing_score
                reasons.append(f"带看{viewing_count}次 +{viewing_score}")

            # 近 7 天跟进
            week_ago = datetime.now() - timedelta(days=7)
            recent_fu = s.query(Followup).filter(
                Followup.customer_id == customer_id,
                Followup.created_at >= week_ago,
            ).count()
            if recent_fu > 0:
                score += 15
                reasons.append(f"近7天跟进{recent_fu}次 +15")

            # 预算明确
            if c.budget_min and c.budget_max:
                score += 10
                reasons.append("预算明确 +10")

            # 是否有成交
            deal_count = s.query(Deal).filter(Deal.customer_id == customer_id).count()
            if deal_count > 0:
                score = 100
                reasons = ["已成交 100分"]

            score = min(score, 100)
            return {
                'customer_id': c.id, 'customer_name': c.name,
                'tier': c.tier, 'score': score, 'breakdown': reasons,
                'viewing_count': viewing_count, 'recent_followups': recent_fu,
                'budget': [c.budget_min, c.budget_max],
            }

    # ---------- 话术库 ----------
    def add_script(self, name, content, scenario='custom'):
        with self.get_session() as s:
            sc = Script(name=name, content=content, scenario=scenario)
            s.add(sc); s.commit(); s.refresh(sc)
            return {'id': sc.id, 'name': sc.name, 'scenario': sc.scenario,
                    'content': sc.content, 'created_at': sc.created_at.isoformat() if sc.created_at else None}

    def list_scripts(self, scenario=None, limit=100):
        with self.get_session() as s:
            q = s.query(Script)
            if scenario:
                q = q.filter(Script.scenario == scenario)
            return [{'id': sc.id, 'name': sc.name, 'scenario': sc.scenario,
                     'content': sc.content,
                     'created_at': sc.created_at.isoformat() if sc.created_at else None}
                    for sc in q.order_by(Script.created_at.desc()).limit(limit).all()]

    def get_script_by_name(self, name):
        with self.get_session() as s:
            sc = s.query(Script).filter(Script.name == name).first()
            if sc:
                return {'id': sc.id, 'name': sc.name, 'scenario': sc.scenario,
                        'content': sc.content,
                        'created_at': sc.created_at.isoformat() if sc.created_at else None}
            return None

    def delete_script(self, sid):
        with self.get_session() as s:
            sc = s.query(Script).get(sid)
            if not sc:
                return False
            s.delete(sc); s.commit()
            return True


# ==================== 全局实例 ====================

_db_instance = None

def init_real_estate_db(database_url: str = None) -> RealEstateDB:
    global _db_instance
    if database_url is None:
        database_url = os.getenv('DATABASE_URL', 'sqlite:///real_estate.db')
    _db_instance = RealEstateDB(database_url)
    return _db_instance

def get_real_estate_db() -> RealEstateDB:
    global _db_instance
    if _db_instance is None:
        # 惰性初始化：gateway 启动不走 init_agent（CLI 专用），首次工具调用
        # 时自动建表，避免重装后新库无表（2026-08-11 真实事故）
        init_real_estate_db()
    return _db_instance
