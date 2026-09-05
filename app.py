import os
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_cmms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ----------------------------------------------------
# DATABASE MODELS
# ----------------------------------------------------

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    manufacturer = db.Column(db.String(100), default="N/A")
    model_number = db.Column(db.String(100), default="N/A")
    serial_number = db.Column(db.String(100), default="N/A")
    location_facility = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), default="General")
    installation_date = db.Column(db.String(20), default="N/A")
    purchase_cost = db.Column(db.Float, default=0.0)
    warranty_expiration = db.Column(db.String(20), default="N/A")
    operational_status = db.Column(db.String(50), default="Operational")
    criticality = db.Column(db.String(20), default="Medium")
    power_rating = db.Column(db.String(50), default="N/A")
    operating_voltage = db.Column(db.String(50), default="N/A")
    maintenance_interval_days = db.Column(db.Integer, default=30)
    last_maintenance_date = db.Column(db.String(20), default="N/A")
    supplier_contact = db.Column(db.String(100), default="N/A")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SparePart(db.Model):
    __tablename__ = 'spare_parts'
    id = db.Column(db.Integer, primary_key=True)
    part_number = db.Column(db.String(50), unique=True, nullable=False)
    part_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="General")
    manufacturer = db.Column(db.String(100), default="N/A")
    model_compatibility = db.Column(db.String(100), default="Universal")
    quantity = db.Column(db.Integer, default=0)
    reorder_threshold = db.Column(db.Integer, default=5)
    reorder_quantity = db.Column(db.Integer, default=10)
    unit_cost = db.Column(db.Float, default=0.0)
    storage_bin_location = db.Column(db.String(50), default="A-01")
    unit_of_measure = db.Column(db.String(20), default="PCS")
    supplier_name = db.Column(db.String(100), default="N/A")
    supplier_part_no = db.Column(db.String(50), default="N/A")
    lead_time_days = db.Column(db.Integer, default=7)
    criticality_rating = db.Column(db.String(20), default="Medium")
    last_restock_date = db.Column(db.String(20), default="N/A")

    def to_dict(self):
        res = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        res["low_stock"] = (self.quantity or 0) <= (self.reorder_threshold or 0)
        return res


class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    technician = db.Column(db.String(100), default="Unassigned")
    status = db.Column(db.String(50), default="Pending")

    asset = db.relationship('Asset', backref='work_orders')
    parts_used = db.relationship('WorkOrderPart', backref='work_order', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "asset_id": self.asset_id,
            "asset_name": self.asset.name if self.asset else "Unknown",
            "technician": self.technician,
            "status": self.status,
            "parts_used": [
                {"part_id": p.part_id, "part_name": p.part.part_name if p.part else "Unknown", "quantity_used": p.quantity_used}
                for p in self.parts_used
            ]
        }


class WorkOrderPart(db.Model):
    __tablename__ = 'work_order_parts'
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False)
    quantity_used = db.Column(db.Integer, default=1)

    part = db.relationship('SparePart')

# ----------------------------------------------------
# ROUTES & REST API ENDPOINTS
# ----------------------------------------------------

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/assets', methods=['GET', 'POST'])
def handle_assets():
    if request.method == 'POST':
        try:
            data = request.json or {}
            # Clean numeric and integer fields to prevent string/type casting errors
            if 'purchase_cost' in data and data['purchase_cost']:
                data['purchase_cost'] = float(data['purchase_cost'])
            if 'maintenance_interval_days' in data and data['maintenance_interval_days']:
                data['maintenance_interval_days'] = int(data['maintenance_interval_days'])

            asset = Asset(**data)
            db.session.add(asset)
            db.session.commit()
            return jsonify(asset.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    assets = db.session.scalars(db.select(Asset)).all()
    return jsonify([a.to_dict() for a in assets])

@app.route('/api/parts', methods=['GET', 'POST'])
def handle_parts():
    if request.method == 'POST':
        try:
            data = request.json or {}
            # Cast numeric types safely
            for field in ['quantity', 'reorder_threshold', 'reorder_quantity', 'lead_time_days']:
                if field in data and data[field] != '':
                    data[field] = int(data[field])
            if 'unit_cost' in data and data['unit_cost'] != '':
                data['unit_cost'] = float(data['unit_cost'])

            part = SparePart(**data)
            db.session.add(part)
            db.session.commit()
            return jsonify(part.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    parts = db.session.scalars(db.select(SparePart)).all()
    return jsonify([p.to_dict() for p in parts])

@app.route('/api/work_orders', methods=['GET', 'POST'])
def handle_work_orders():
    if request.method == 'POST':
        try:
            data = request.json or {}
            order = WorkOrder(
                title=data['title'], 
                asset_id=int(data['asset_id']), 
                technician=data.get('technician', 'Unassigned'), 
                status="In Progress"
            )
            db.session.add(order)
            db.session.commit()
            return jsonify(order.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    orders = db.session.scalars(db.select(WorkOrder)).all()
    return jsonify([o.to_dict() for o in orders])

@app.route('/api/work_orders/<int:order_id>/complete', methods=['POST'])
def complete_work_order(order_id):
    order = db.session.get(WorkOrder, order_id)
    if not order or order.status == 'Completed':
        return jsonify({"error": "Invalid order status"}), 400

    try:
        for item in order.parts_used:
            if item.part and item.part.quantity < item.quantity_used:
                return jsonify({"error": f"Insufficient stock for '{item.part.part_name}'"}), 400

        for item in order.parts_used:
            if item.part:
                item.part.quantity -= item.quantity_used

        order.status = 'Completed'
        db.session.commit()
        return jsonify(order.to_dict())
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "details": str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)