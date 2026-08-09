"""
房产助理 - 数据库模块
Coco（可可）的底层数据存储
"""
import os
import json
import re
from datetime import datetime, timedelta
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

# ==================== 数据模型 ====================

class Customer(Base):
    """客户表"""
    __tablename__ = 're_customers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    wechat = Column(String(100))
    feishu_id = Column(String(100))
    tier = Column(String(1), default='C')
    budget_min = Column(Integer)
    budget_max = Column(Integer)
    area_pref = Column(String(50))
    layout_pref = Column(String(50))
    location = Column(String(200))
    renovation = Column(String(50))
    notes = Column(Text)
    tags = Column(Text)
    source = Column(String(100))
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    followups = relationship("Followup", back_populates="customer")
    
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
            'source': self.source, 'status': self.status,
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
    price = Column(Integer, nullable=False)
    unit_price = Column(Integer)
    area = Column(Float, nullable=False)
    rooms = Column(Integer)
    halls = Column(Integer)
    bathrooms = Column(Integer)
    floor = Column(String(50))
    orientation = Column(String(50))
    renovation = Column(String(50))
    year_built = Column(Integer)
    has_elevator = Column(Integer, default=1)
    parking = Column(Integer, default=0)
    tags = Column(Text)
    images = Column(Text)
    status = Column(String(20), default='available')
    agent_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    followups = relationship("Followup", back_populates="property")
    
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
            'price': self.price, 'unit_price': self.unit_price,
            'area': self.area, 'rooms': self.rooms, 'halls': self.halls,
            'bathrooms': self.bathrooms, 'floor': self.floor,
            'orientation': self.orientation, 'renovation': self.renovation,
            'year_built': self.year_built, 'has_elevator': self.has_elevator,
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
                if hasattr(c, k): setattr(c, k, v)
            s.commit(); s.refresh(c)
            return c.to_dict()
    
    def get_customer(self, cid):
        with self.get_session() as s:
            c = s.query(Customer).get(cid)
            return c.to_dict() if c else None
    
    def list_customers(self, tier=None, status=None, limit=50):
        with self.get_session() as s:
            q = s.query(Customer)
            if tier: q = q.filter(Customer.tier == tier)
            if status: q = q.filter(Customer.status == status)
            return [c.to_dict() for c in q.limit(limit).all()]
    
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
    
    def search_properties(self, **filters):
        with self.get_session() as s:
            q = s.query(Property).filter(Property.status == 'available')
            if 'min_price' in filters: q = q.filter(Property.price >= filters['min_price'])
            if 'max_price' in filters: q = q.filter(Property.price <= filters['max_price'])
            if 'min_area' in filters: q = q.filter(Property.area >= filters['min_area'])
            if 'max_area' in filters: q = q.filter(Property.area <= filters['max_area'])
            if 'rooms' in filters: q = q.filter(Property.rooms == filters['rooms'])
            if 'district' in filters: q = q.filter(Property.district.contains(filters['district']))
            if 'renovation' in filters: q = q.filter(Property.renovation == filters['renovation'])
            return [p.to_dict() for p in q.limit(50).all()]
    
    def match_property(self, customer_id, top_n=5):
        customer = self.get_customer(customer_id)
        if not customer: return []
        
        properties = self.search_properties()
        if not properties: return []
        
        min_area, max_area = self._parse_area(customer.get('area_pref'))
        budget_min = customer.get('budget_min') or 0
        budget_max = customer.get('budget_max') or 999999
        
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


# ==================== 全局实例 ====================

_db_instance = None

def init_real_estate_db(database_url: str = None) -> RealEstateDB:
    global _db_instance
    if database_url is None:
        database_url = os.getenv('DATABASE_URL', 'sqlite:///real_estate.db')
    _db_instance = RealEstateDB(database_url)
    return _db_instance

def get_real_estate_db() -> RealEstateDB:
    if _db_instance is None:
        raise RuntimeError("Real estate DB not initialized. Call init_real_estate_db() first.")
    return _db_instance
